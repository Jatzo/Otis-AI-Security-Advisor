"""Runs the retrieval ladder on the dev questions, as fixed in docs/retrieval-plan.md.

Dev only: the questions are filtered to the dev split as they are read, and the run refuses to
start unless everything frozen under eval/ still matches the freeze tag. Results go to
eval/results/, which is outside the freeze.

Usage (after `uv sync --group ml`):
    python scripts/retrieval_ladder.py --max-spend 1
"""

import argparse
import importlib.util
import json
import os
import sqlite3
import statistics
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.retrieval import decompose, ladder  # noqa: E402
from advisor.retrieval.dense import SentenceTransformerEmbedder  # noqa: E402
from advisor.retrieval.pipeline import Pipeline, Spec  # noqa: E402
from advisor.retrieval.query import Hints  # noqa: E402
from advisor.retrieval.rerank import CrossEncoderScorer  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402

RESULTS = ROOT / "eval" / "results"
QUESTION_PREFIX = (
    "Instruct: Given a question about a software vulnerability, "
    "retrieve the advisory record that answers it\nQuery: "
)
MODELS = {
    "a": ("Qwen/Qwen3-Embedding-0.6B", QUESTION_PREFIX, 2048, "left"),
    "b": (
        "BAAI/bge-small-en-v1.5",
        "Represent this sentence for searching relevant passages: ",
        512,
        None,
    ),
}
RERANKER = "BAAI/bge-reranker-v2-m3"


def guard_freeze() -> None:
    spec = importlib.util.spec_from_file_location(
        "check_eval_frozen", ROOT / "scripts" / "check_eval_frozen.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    problems = module.check(ROOT)
    if problems:
        raise SystemExit("Frozen files differ from the freeze tag:\n" + "\n".join(problems))


def model_revisions(repos: list[str]) -> dict[str, dict]:
    """Each model's current commit and licence, saved the first time so later runs use the same
    commit. A saved file wins over the hub."""
    path = RESULTS / "model_revisions.json"
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    from huggingface_hub import HfApi  # noqa: PLC0415

    for repo in repos:
        if repo not in known:
            info = HfApi().model_info(repo)
            known[repo] = {
                "revision": info.sha,
                "license": getattr(info.card_data, "license", None),
            }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(known, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return known


class MemoScorer:
    """Remembers scores, so R6 does not read again what R5 already read."""

    def __init__(self, scorer) -> None:
        self.scorer, self.cache_key, self.memo = scorer, scorer.cache_key, {}

    def score(self, query: str, texts: list[str]) -> list[float]:
        missing = [t for t in texts if (query, t) not in self.memo]
        if missing:
            for text, value in zip(missing, self.scorer.score(query, missing), strict=True):
                self.memo[(query, text)] = value
        return [self.memo[(query, t)] for t in texts]


def run_rung(pipeline: Pipeline, spec: Spec, items: list[ladder.Item], run: int = 1) -> dict:
    """Ranks every dev question. Index building is timed apart from the queries."""
    started = time.monotonic()
    for kind in (spec.bm25, spec.dense):
        if kind:
            pipeline.index(kind, spec.split)
    build = time.monotonic() - started
    rows, seconds = [], []
    for item in items:
        started = time.monotonic()
        ranked = pipeline.rank(spec, item.query, run)
        seconds.append(time.monotonic() - started)
        rows.append({**ladder.score_ranking(item, ranked), "top20": ranked[:20]})
    ordered = sorted(seconds)
    return {
        "spec": spec.__dict__,
        "rows": rows,
        "summary": ladder.summarise(rows),
        "build_seconds": round(build, 2),
        "latency_p50": round(statistics.median(seconds), 3),
        "latency_p95": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 3),
    }


def hits(result: dict) -> list[bool]:
    return [r[f"all@{ladder.PRIMARY_K}"] for r in result["rows"]]


def baselines(hints: Hints, items: list[ladder.Item]) -> dict:
    whole = [hints.whole_packages(i.query) for i in items]
    exact = [hints.exact_matches(i.query) for i in items]
    return {
        "B0": {
            "all_in_whole_package": sum(
                i.needed <= set(w) for i, w in zip(items, whole, strict=True)
            ),
            "median_list_length": statistics.median(len(w) for w in whole),
            "questions": len(items),
        },
        "B1": {
            "coverage": sum(bool(e) for e in exact),
            "all_in_exact_matches": sum(
                i.needed <= set(e) for i, e in zip(items, exact, strict=True)
            ),
            "questions": len(items),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "advisor.db"))
    parser.add_argument("--cache", default=str(ROOT / "data" / "embeddings"))
    parser.add_argument("--max-spend", type=float, required=True, help="dollars for R8 only")
    parser.add_argument("--runs", type=int, default=3, help="repeats of R8")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--skip-r8", action="store_true")
    args = parser.parse_args()

    guard_freeze()
    items, left_out = ladder.load_dev_items(
        ROOT / "eval" / "questions.jsonl", ROOT / "eval" / "gold.jsonl"
    )

    import torch  # noqa: PLC0415

    torch.set_num_threads(args.threads)
    revisions = model_revisions([m[0] for m in MODELS.values()] + [RERANKER])
    embedders = {
        key: SentenceTransformerEmbedder(repo, revisions[repo]["revision"], prefix, length, side)
        for key, (repo, prefix, length, side) in MODELS.items()
    }
    scorer = MemoScorer(CrossEncoderScorer(RERANKER, revisions[RERANKER]["revision"]))

    db = sqlite3.connect(args.db)
    units = build_units(db)
    spent = [0.0]
    cache_path = RESULTS / "decompositions.json"

    client = None

    def decomposer(question: str, run: int) -> list[str]:
        nonlocal client
        if spent[0] >= args.max_spend:
            raise SystemExit(f"Spend cap ${args.max_spend:.2f} reached.")
        if client is None:
            import anthropic  # noqa: PLC0415

            client = anthropic.Anthropic(api_key=read_key(), max_retries=2)
        queries, cost = decompose.decompose(question, run, client, cache_path)
        spent[0] += cost
        return queries

    pipeline = Pipeline(units, embedders, scorer, decomposer, Path(args.cache))
    results: dict[str, dict] = {"baselines": baselines(pipeline.hints, items)}
    decisions: list[dict] = []
    specs = {
        "R0": Spec("R0", bm25="body"),
        "R1": Spec("R1", bm25="header"),
        "R2": Spec("R2", dense="a"),
        "R3": Spec("R3", dense="b"),
    }
    for name in ("R0", "R1", "R2", "R3"):
        results[name] = run_rung(pipeline, specs[name], items)
        print(name, results[name]["summary"]["all@10"], flush=True)

    current = "R0"

    def consider(name: str) -> None:
        nonlocal current
        verdict = ladder.adopt(hits(results[name]), hits(results[current]))
        decisions.append({"rung": name, "against": current, **verdict})
        if verdict["adopted"]:
            current = name

    consider("R1")
    winner = ladder.pick_dense(results["R2"]["rows"], results["R3"]["rows"])
    consider("R2" if winner == "a" else "R3")
    specs["R4"] = Spec("R4", bm25="header", dense=winner)
    specs["R5"] = replace(specs["R4"], name="R5", rerank=True)
    specs["R6"] = replace(specs["R5"], name="R6", soft_filter=True)
    for name in ("R4", "R5", "R6"):
        results[name] = run_rung(pipeline, specs[name], items)
        print(name, results[name]["summary"]["all@10"], flush=True)
        consider(name)
    specs["R7"] = replace(specs[current], name="R7", split=True)
    results["R7"] = run_rung(pipeline, specs["R7"], items)
    print("R7", results["R7"]["summary"]["all@10"], flush=True)
    consider("R7")

    if not args.skip_r8:
        base = replace(specs[current], name="R8", decompose=True)
        runs = [run_rung(pipeline, base, items, run) for run in range(1, args.runs + 1)]
        majority = [sum(h) * 2 > len(runs) for h in zip(*(hits(r) for r in runs), strict=True)]
        results["R8"] = {**runs[0], "runs": runs, "majority_hits": majority, "cost_usd": spent[0]}
        verdict = ladder.adopt(majority, hits(results[current]))
        decisions.append({"rung": "R8", "against": current, **verdict})
        if verdict["adopted"]:
            current = "R8"

    commit = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()  # fmt: skip
    manifest = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    output = {
        "commit": commit,
        "snapshot": manifest["snapshot_id"],
        "freeze_tag": "eval-freeze-v1",
        "models": revisions,
        "dev_questions_scored": len(items),
        "dev_questions_left_out_because_they_should_be_declined": left_out,
        "decisions": decisions,
        "adopted": current,
        "results": results,
    }
    (RESULTS / "retrieval-dev.json").write_text(
        json.dumps(output, indent=1, sort_keys=True, default=list) + "\n", encoding="utf-8"
    )
    print(f"Adopted: {current}. Spent on R8: ${spent[0]:.2f}.")
    print("Written to eval/results/retrieval-dev.json")
    return 0


def read_key() -> str:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "ANTHROPIC_API_KEY":
            return value.strip().strip("\"'")
    raise SystemExit("No ANTHROPIC_API_KEY. Add it to .env, then run again.")


if __name__ == "__main__":
    sys.exit(main())
