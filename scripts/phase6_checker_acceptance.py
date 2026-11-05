"""Judges the saved replies again with the changed checker and applies the written acceptance rule.

It calls no model and rewrites no committed result file. Two commands:

    python scripts/phase6_checker_acceptance.py baseline   (run once, on the Phase 5 checker)
    python scripts/phase6_checker_acceptance.py accept     (run on the changed checker)

`baseline` records, for each of the 120 saved dev replies and the 168 saved red team replies,
what the Phase 5 checker did with it, and which package and version pairs it read in each
question. `accept`
runs the current checker over the same replies and compares. The rule is in
docs/adr/0012 and was written before the first `accept` run.
"""

import argparse
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from advisor.generation.checker import check, question_pairs  # noqa: E402
from advisor.generation.facts import Facts  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402

RESULTS = ROOT / "eval" / "results"
BASELINE = RESULTS / "checker-baseline-phase5.json"
REPORT = RESULTS / "checker-acceptance-phase6.json"
SHIPPED = ("passed", "repaired")
COMMITTED_CHECKED = (
    "eval/results/generation-dev-checked.jsonl",
    "eval/results/generation-v2-dev-checked.jsonl",
    "eval/results/generation-smoke-dev-checked.jsonl",
    "eval/results/test-generation-checked.jsonl",
)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


score = load("frozen_score", ROOT / "eval" / "score.py")
runner = load("frozen_run_redteam", ROOT / "scripts" / "run_redteam.py")


def read_lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def git(*args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()  # fmt: skip


def key(*parts) -> str:
    return "|".join(str(p) for p in parts)


def dev_replies() -> tuple[list[dict], dict, dict]:
    questions = {q["id"]: q for q in read_lines(ROOT / "eval" / "questions.jsonl")
                 if q["split"] == "dev"}  # fmt: skip
    lines = [x for x in read_lines(RESULTS / "generation-dev-raw.jsonl") if x["id"] in questions]
    return lines, questions, {g["id"]: g for g in read_lines(ROOT / "eval" / "gold.jsonl")}


def verdicts(db: sqlite3.Connection) -> tuple[dict, dict]:
    """What the current checker does with every saved reply, and the pairs it reads in questions."""
    facts = Facts(db)
    units_by_id = {u.unit_id: u for u in build_units(db)}
    lines, questions, _ = dev_replies()
    dev, pairs = {}, {}
    for line in lines:
        question = questions[line["id"]]["question"]
        shown = [units_by_id[i] for i in line["shown"]]
        done = check(question, line["text"], line["stop_reason"], shown, facts)
        dev[key(line["run"], line["id"])] = [done.verdict, done.rule]
        pairs[line["id"]] = [list(p) for p in question_pairs(question)]
    red = {}
    for which, file in runner.FILES.items():
        cases = {c.case_id: c for c in runner.spec.load(runner.REDTEAM / file)}
        worlds: dict = {}
        for line in read_lines(RESULTS / f"redteam-r1-{which}-raw.jsonl"):
            case = cases[line["id"]]
            if case.case_id not in worlds:
                worlds[case.case_id] = runner.poisoned_world(db, case)
            world_facts, world_units, _ = worlds[case.case_id]
            shown = [world_units[i] for i in line["shown"]]
            done = check(case.question, line["text"], line["stop_reason"], shown, world_facts)
            red[key(which, line["id"], line["run"])] = [done.verdict, done.rule]
            pairs[key("redteam", case.case_id)] = [list(p) for p in question_pairs(case.question)]
    return {"dev": dev, "redteam": red}, pairs


def command_baseline() -> int:
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'advisor.db'}?mode=ro", uri=True)
    table, pairs = verdicts(db)
    committed = {
        key(x["run"], x["id"]): [x["checker"]["verdict"], x["checker"]["rule"]]
        for x in read_lines(RESULTS / "generation-dev-checked.jsonl")
    }
    if committed != table["dev"]:
        print("The checker does not reproduce the committed dev checked file. Stopping.")
        return 1
    out = {"commit": git("rev-parse", "HEAD"), "pairs": pairs, **table}
    BASELINE.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"The checker reproduces the committed dev checked file ({len(committed)} rows).")
    print(f"Baseline written to {BASELINE.relative_to(ROOT)} for {out['commit'][:7]}.")
    return 0


def command_accept() -> int:
    db = sqlite3.connect(f"file:{ROOT / 'data' / 'advisor.db'}?mode=ro", uri=True)
    before = json.loads(BASELINE.read_text(encoding="utf-8"))
    now, pairs = verdicts(db)
    lines, questions, gold = dev_replies()
    ids = score.load_ids()
    report: dict = {"baseline_commit": before["commit"], "problems": []}

    # Rule 1, on the dev replies. The scorer marks the raw reply; a reply it marks wrong and the old
    # checker refused must still be refused.
    changed, recovered, newly_shipped_wrong, lost_right = [], [], [], []
    for line in lines:
        k = key(line["run"], line["id"])
        old, new = before["dev"][k], now["dev"][k]
        row = score.score_question(questions[line["id"]], gold[line["id"]], line, ids)
        right = row["outcome"] == "correct"
        if old != new:
            changed.append({"run": line["run"], "id": line["id"], "old": old, "new": new,
                            "raw_right": right})  # fmt: skip
        if old[0] not in SHIPPED and new[0] in SHIPPED:
            (recovered if right else newly_shipped_wrong).append(k)
        if old[0] in SHIPPED and new[0] not in SHIPPED and right:
            lost_right.append(k)
    report["dev"] = {
        "replies": len(lines), "changed": changed, "recovered_right": recovered,
        "newly_shipped_wrong": newly_shipped_wrong, "right_now_refused": lost_right,
    }  # fmt: skip
    if newly_shipped_wrong:
        report["problems"].append("a reply the scorer marks wrong now ships on dev")
    if lost_right:
        report["problems"].append("a right reply that shipped is now refused on dev")

    # Rule 2, on the red team replies. Judge again and set beside the frozen table.
    red_changed, red_worse = [], []
    for which, file in runner.FILES.items():
        cases = runner.spec.load(runner.REDTEAM / file)
        saved = read_lines(RESULTS / f"redteam-r1-{which}-judged-poisonfix.jsonl")
        again = runner.judge(cases, db, RESULTS / f"redteam-r1-{which}-raw.jsonl", topic_gate=False)
        for old_row, new_row in zip(saved, again, strict=True):
            diff = {f: [old_row[f], new_row[f]] for f in old_row
                    if f != "cost_usd" and old_row[f] != new_row[f]}  # fmt: skip
            if diff:
                red_changed.append({"set": which, "id": old_row["id"], "run": old_row["run"],
                                    "diff": diff})  # fmt: skip
            for field in ("shipped_success", "shipped_obeyed"):
                if new_row[field] and not old_row[field]:
                    red_worse.append(key(which, old_row["id"], old_row["run"], field))
    shipped_before = {k for k, v in before["redteam"].items() if v[0] in SHIPPED}
    shipped_now = {k for k, v in now["redteam"].items() if v[0] in SHIPPED}
    report["redteam"] = {
        "replies": len(now["redteam"]), "judged_rows_changed": red_changed,
        "newly_shipped": sorted(shipped_now - shipped_before),
        "no_longer_shipped": sorted(shipped_before - shipped_now),
        "new_success_or_obeyed": red_worse,
    }  # fmt: skip
    if red_worse:
        report["problems"].append("a red team reply is newly successful or obeyed")
    # ADR 0012 first said that no reply refused today may ship. Fix 2 broke that on 2 right answers
    # and the rule was amended (see the ADR): what counts is that none is a named or obeyed success.
    # The first wording is still reported, so the amendment can be seen.
    report["redteam"]["first_wording_met"] = not report["redteam"]["newly_shipped"]

    # The pairs the checker reads in each question.
    report["pairs_changed"] = {
        k: {"before": before["pairs"][k], "now": pairs[k]}
        for k in pairs if before["pairs"].get(k) != pairs[k]
    }  # fmt: skip

    # The committed checked files must not have moved.
    moved = git("status", "--porcelain", "--", *COMMITTED_CHECKED)
    report["committed_checked_files_unchanged"] = not moved
    if moved:
        report["problems"].append("a committed checked file has changed")

    REPORT.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    show(report)
    return 1 if report["problems"] else 0


def show(report: dict) -> None:
    dev, red = report["dev"], report["redteam"]
    print(f"Dev: {dev['replies']} replies, {len(dev['changed'])} changed.")
    for row in dev["changed"]:
        print(
            f"  {row['id']} run {row['run']}: {row['old']} -> {row['new']} "
            f"(raw right: {row['raw_right']})"
        )
    print(f"  refused and right, now shipped: {len(dev['recovered_right'])}")
    print(f"  wrong, now shipped: {len(dev['newly_shipped_wrong'])}")
    print(f"  right and shipped, now refused: {len(dev['right_now_refused'])}")
    print(
        f"Red team: {red['replies']} replies, "
        f"{len(red['judged_rows_changed'])} judged rows changed."
    )
    for row in red["judged_rows_changed"]:
        print(f"  {row['set']} {row['id']} run {row['run']}: {row['diff']}")
    print(
        f"  newly shipped: {len(red['newly_shipped'])} (first wording of the rule met: "
        f"{red['first_wording_met']}); new success or obeyed: {len(red['new_success_or_obeyed'])}"
    )
    for name in red["newly_shipped"]:
        print(f"    {name}")
    print(f"Pairs changed in {len(report['pairs_changed'])} questions.")
    print(f"Committed checked files unchanged: {report['committed_checked_files_unchanged']}")
    print("PROBLEMS: " + ("; ".join(report["problems"]) if report["problems"] else "none"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["baseline", "accept"])
    args = parser.parse_args()
    return command_baseline() if args.command == "baseline" else command_accept()


if __name__ == "__main__":
    sys.exit(main())
