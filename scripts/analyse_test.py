"""The cross-row tables for Phase 5: every row side by side, and the per-question file.

Reads the scored result files of each row (eval/score.py --out), the first run only, and writes
eval/results/<split>-rows-analysis.json and <split>-per-question.csv. Rows: B no retrieval, S
structured lookups, L long context (package-naming questions only), G_raw the system's raw reply,
G the system's checked reply (the headline). A row with no file is listed as not run. Nothing here
calls a model. The split is dev while the code is built and test once, after every row is committed
(docs/test-plan.md).

Usage:
    python scripts/analyse_test.py --split dev
    python scripts/analyse_test.py --split test
"""

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
ROWS = {
    "dev": {
        "B": "baseline-dev.scored.jsonl",
        "S": "structured-dev-raw.scored.jsonl",
        "L": "phase5-l-smoke-dev-raw.scored.jsonl",
        "G_raw": "generation-dev-raw.scored.jsonl",
        "G": "generation-dev-checked.scored.jsonl",
    },
    "test": {
        "B": "baseline-test.scored.jsonl",
        "S": "test-structured-raw.scored.jsonl",
        "L": "test-longcontext-raw.scored.jsonl",
        "G_raw": "test-generation-raw.scored.jsonl",
        "G": "test-generation-checked.scored.jsonl",
    },
}
CHECKED = {"dev": "generation-dev-checked.jsonl", "test": "test-generation-checked.jsonl"}
RETRIEVAL = {"dev": "retrieval-dev.json", "test": "test-retrieval.json"}
NOT_ASKED = {"dev": "phase5-l-smoke-dev-notasked.json", "test": "test-longcontext-notasked.json"}
# Compared by exact McNemar on the questions both rows answered. Secondary, apart from the first.
PAIRS = [("G", "B"), ("G", "S"), ("G", "L"), ("G_raw", "B")]


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_scorer():
    spec = importlib.util.spec_from_file_location("score", ROOT / "eval" / "score.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["score"] = module
    spec.loader.exec_module(module)
    return module


def code(row: dict | None) -> str:
    if row is None:
        return "not_asked"
    return row["outcome"] + ("*" if row["abstained"] else "")


def retrieval_top10(split: str) -> dict[str, list[str]]:
    path = RESULTS / RETRIEVAL[split]
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["rows"] if split == "test" else data["results"]["R1"]["rows"]
    return {r["id"]: r["top20"][:10] for r in rows}


def retrieval_flags(split: str) -> dict[str, bool]:
    path = RESULTS / RETRIEVAL[split]
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["rows"] if split == "test" else data["results"]["R1"]["rows"]
    return {r["id"]: r["all@10"] for r in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--run", type=int, default=1)
    args = parser.parse_args()
    score = load_scorer()
    questions = [
        q for q in read_lines(ROOT / "eval" / "questions.jsonl") if q["split"] == args.split
    ]
    order = [q["id"] for q in questions]
    tables: dict[str, dict[str, dict]] = {}
    for name, file in ROWS[args.split].items():
        path = RESULTS / file
        if path.exists():
            tables[name] = {r["id"]: r for r in read_lines(path) if r["run"] == args.run}
    out: dict = {
        "split": args.split,
        "run": args.run,
        "rows_run": sorted(tables),
        "rows_not_run": sorted(set(ROWS[args.split]) - set(tables)),
    }

    out["summaries"] = {
        name: score.render(score.summarise([t[q] for q in order if q in t]), f"{args.split} {name}")
        for name, t in tables.items()
    }
    notasked = RESULTS / NOT_ASKED[args.split]
    out["long_context_not_asked"] = (
        json.loads(notasked.read_text(encoding="utf-8")) if notasked.exists() else []
    )

    comparisons = {}
    for first, second in PAIRS:
        if first in tables and second in tables:
            shared = [q for q in order if q in tables[first] and q in tables[second]]
            right = score.is_right
            only_first = sum(
                right(tables[first][q]) and not right(tables[second][q]) for q in shared
            )
            only_second = sum(
                right(tables[second][q]) and not right(tables[first][q]) for q in shared
            )
            comparisons[f"{first} against {second}"] = {
                "shared_questions": len(shared),
                "only_first_right": only_first,
                "only_second_right": only_second,
                "exact_mcnemar_p": round(score.mcnemar_p(only_first, only_second), 4),
            }
    out["comparisons"] = comparisons

    if "L" in tables:  # every row on the questions long context was asked
        asked = [q for q in order if q in tables["L"]]
        out["on_the_long_context_questions"] = {
            "questions": len(asked),
            **{
                name: sum(score.is_right(t[q]) for q in asked if q in t)
                for name, t in tables.items()
            },
        }

    flags = retrieval_flags(args.split)
    checked_file = RESULTS / CHECKED[args.split]
    route = {}
    if checked_file.exists():
        for line in read_lines(checked_file):
            if line["run"] == args.run:
                info = line["checker"]
                route[line["id"]] = f"{info['route']}/{info['verdict']}"

    # Row R and the system must have used the same top 10 for every question both cover.
    seen = {}
    raw_file = RESULTS / ROWS[args.split]["G_raw"].replace(".scored", "")
    if raw_file.exists():
        seen = {x["id"]: x["shown"] for x in read_lines(raw_file) if x["run"] == args.run}
    top10 = retrieval_top10(args.split)
    both = [q for q in top10 if q in seen]
    out["retrieval_matches_system"] = {
        "questions_compared": len(both),
        "different": [q for q in both if top10[q] != seen[q]],
    }

    names = list(tables)
    with (RESULTS / f"{args.split}-per-question.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["id", "type", "subtype", "slice", "ecosystem", "stale_risk", "maven_release",
             "r1_had_all_evidence", "checker_route", *names]
        )  # fmt: skip
        for q in questions:
            writer.writerow(
                [q["id"], q["type"], q["subtype"], q["slice"], q["ecosystem"], q["stale_risk"],
                 q["maven_release"], flags.get(q["id"], ""), route.get(q["id"], ""),
                 *(code(tables[n].get(q["id"])) for n in names)]
            )  # fmt: skip
    path = RESULTS / f"{args.split}-rows-analysis.json"
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "summaries"}, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
