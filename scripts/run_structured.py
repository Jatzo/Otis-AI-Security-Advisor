"""Answers every question of a split with the structured-lookup row (no model, no cost).

Phase 5, row S (docs/test-plan.md). It is built and checked on dev. The test split needs
--allow-test and the tagged system, and is run once. The replies are in the baseline's line format,
so eval/score.py reads them unchanged. Nothing about test outcomes is printed.

Usage:
    python scripts/run_structured.py --split dev
    python scripts/run_structured.py --split test --allow-test
"""

import argparse
import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.structured import Lookups  # noqa: E402

RESULTS = ROOT / "eval" / "results"
STORE = ROOT / "data" / "advisor.db"
NAME = "structured-lookups"


def load_runner():
    path = ROOT / "scripts" / "run_generation.py"
    spec = importlib.util.spec_from_file_location("run_generation", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_generation"] = module
    spec.loader.exec_module(module)
    return module


def result_line(question: dict, reply: dict, seconds: float, proof: dict) -> dict:
    return {
        "id": question["id"], "run": 1, "split": question["split"],
        "text": json.dumps(reply), "stop_reason": "end_turn", "stop_category": None,
        "usage": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}, "price": {},
        "cost_usd": 0.0, "latency_s": round(seconds, 6), "attempts": 1, "request_id": None,
        "model": NAME, "requested_model": NAME, "effort": None, "max_tokens": None, **proof,
    }  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--allow-test", action="store_true")
    args = parser.parse_args()
    runner = load_runner()
    questions = runner.load_questions(args.split)
    out = RESULTS / (
        "test-structured-raw.jsonl" if args.split == "test" else "structured-dev-raw.jsonl"
    )
    if args.split == "test":
        wording = SimpleNamespace(allow_test=args.allow_test, runs=1, dry_run=False, recheck=False)
        stop = runner.test_problem(wording, out, questions, runner.load_preflight().problems)
        if stop:
            print(stop)
            return 1
    runner.guard_freeze()
    lookups = Lookups(sqlite3.connect(f"file:{STORE}?mode=ro", uri=True))
    proof = {"commit": runner.git("rev-parse", "HEAD"), "dirty": False, "hashes": {}}
    lines, declined = [], 0
    for question in questions:
        started = time.monotonic()
        reply = lookups.answer(question["question"])
        declined += reply["abstain"]
        lines.append(result_line(question, reply, time.monotonic() - started, proof))
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in lines), encoding="utf-8")
    shown = f"{declined} declined" if args.split == "dev" else "written"
    print(f"{len(lines)} questions, {shown}: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
