"""Judges the saved round 1 red team replies again, with the poison builder's range type fixed.

The first poison builder gave every new record the range type ECOSYSTEM, so the checker could not
order npm versions (docs/debug-log.md, 2026-11-04). The fix changes only how the checker reads a
new record. The text the model was shown is the same, so the saved replies still stand and judging
them again is exact, not an estimate. This calls no model and never overwrites a saved file.

Two steps per set:
1. Control: judge with the old behaviour (every new record ECOSYSTEM) and require the result to
   equal the saved judged file. If it does not, nothing else is trusted and the script stops.
2. Judge with the fixed builder, write the result beside the saved one with the suffix
   -poisonfix, and print every row that differs.

Usage: python scripts/replay_poison_fix.py
"""

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.redteam import poison  # noqa: E402

_loaded = importlib.util.spec_from_file_location("run_redteam", ROOT / "scripts" / "run_redteam.py")
runner = importlib.util.module_from_spec(_loaded)
_loaded.loader.exec_module(runner)

RESULTS = ROOT / "eval" / "results"
NOT_COMPARED = ("cost_usd",)  # money is the same either way; every other field is compared


def rows_without_cost(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in row.items() if k not in NOT_COMPARED} for row in rows]


def read_json_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    clean = sqlite3.connect(f"file:{ROOT / 'data' / 'advisor.db'}?mode=ro", uri=True)
    fixed_builder = poison.range_type_for
    for which, file in runner.FILES.items():
        cases = runner.spec.load(runner.REDTEAM / file)
        raw_path = RESULTS / f"redteam-r1-{which}-raw.jsonl"
        saved = read_json_lines(RESULTS / f"redteam-r1-{which}-judged.jsonl")

        poison.range_type_for = lambda db, ecosystem: "ECOSYSTEM"  # noqa: ARG005 - the old builder
        control = runner.judge(cases, clean, raw_path, topic_gate=False)
        poison.range_type_for = fixed_builder
        if rows_without_cost(control) != rows_without_cost(saved):
            print(f"{which}: the control does not match the saved judged file. Stopping.")
            return 1
        print(f"{which}: the control matches the saved judged file ({len(saved)} rows).")

        after = runner.judge(cases, clean, raw_path, topic_gate=False)
        for old, new in zip(saved, after, strict=True):
            diff = {k: (old[k], new[k]) for k in old if k != "cost_usd" and old[k] != new[k]}
            if diff:
                print(f"  changed: {old['id']} run {old['run']}: {diff}")
        (RESULTS / f"redteam-r1-{which}-judged-poisonfix.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in after), encoding="utf-8"
        )
        table = runner.summarise(after)
        (RESULTS / f"redteam-r1-{which}-summary-poisonfix.json").write_text(
            json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8"
        )
        runner.print_table(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
