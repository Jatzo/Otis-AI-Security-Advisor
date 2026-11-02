"""Scores R1, the adopted retrieval rung, on one split, for the Phase 5 retrieval row.

The ladder script is dev only on purpose. This one takes the split as an argument so the same code
can be checked on dev and then run once on test (docs/test-plan.md). Test needs --allow-test and the
tagged system. The other rungs stay dev only, as eval/rules.md section 8 says. B0 and B1, the two
no-model lists, are shown beside R1 as context.

Usage:
    python scripts/retrieval_test.py --split dev
    python scripts/retrieval_test.py --split test --allow-test
"""

import argparse
import importlib.util
import json
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.retrieval import ladder  # noqa: E402
from advisor.retrieval.metrics import evidence_ids  # noqa: E402
from advisor.retrieval.pipeline import Pipeline, Spec  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402

RESULTS = ROOT / "eval" / "results"
R1 = Spec("R1", bm25="header")


def load_items(split: str) -> tuple[list[ladder.Item], list[str]]:
    """The answerable questions of the split as ladder items, and the ids left out because the
    right answer is to decline. Other splits are dropped as the file is read."""
    questions = [
        q for q in ladder.read_lines(ROOT / "eval" / "questions.jsonl") if q["split"] == split
    ]
    gold = {g["id"]: g for g in ladder.read_lines(ROOT / "eval" / "gold.jsonl")}
    items, left_out = [], []
    for q in questions:
        if q["answers_with"] == "abstain":
            left_out.append(q["id"])
            continue
        needed = evidence_ids(gold[q["id"]])
        items.append(
            ladder.Item(q["id"], q["type"], q["template"], q["question"], frozenset(needed))
        )
    return items, left_out


def baselines(pipeline: Pipeline, items: list[ladder.Item]) -> dict:
    whole = [pipeline.hints.whole_packages(i.query) for i in items]
    exact = [pipeline.hints.exact_matches(i.query) for i in items]
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


def problem(args, out: Path) -> str | None:
    if args.split != "test":
        return None
    if not args.allow_test:
        return "Test is scored once per system: give --allow-test."
    if out.exists():
        return "The test retrieval row already exists. Test is scored once."
    spec = importlib.util.spec_from_file_location(
        "phase5_preflight", ROOT / "scripts" / "phase5_preflight.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found = module.problems()
    return found[0] if found else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--db", default=str(ROOT / "data" / "advisor.db"))
    args = parser.parse_args()
    out = RESULTS / ("test-retrieval.json" if args.split == "test" else "retrieval-r1-dev.json")
    stop = problem(args, out)
    if stop:
        print(stop)
        return 1

    items, left_out = load_items(args.split)
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    pipeline = Pipeline(build_units(db))
    rows, seconds = [], []
    for item in items:
        started = time.monotonic()
        ranked = pipeline.rank(R1, item.query)
        seconds.append(time.monotonic() - started)
        rows.append({**ladder.score_ranking(item, ranked), "top20": ranked[:20]})
    ordered = sorted(seconds)
    result = {
        "split": args.split,
        "spec": R1.__dict__,
        "questions_scored": len(items),
        "left_out_because_they_should_be_declined": left_out,
        "baselines": baselines(pipeline, items),
        "rows": rows,
        "summary": ladder.summarise(rows),
        "latency_p50": round(statistics.median(seconds), 4),
        "latency_p95": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 4),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=1, sort_keys=True, default=list) + "\n", encoding="utf-8"
    )
    if args.split == "dev":  # nothing about test outcomes is shown before all rows are in
        print(json.dumps(result["summary"].get("all@10"), default=list), "written", out.name)
    else:
        print("Written to", out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
