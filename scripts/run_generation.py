"""Runs the generation and checker on the dev questions, as fixed in docs/generation-plan.md.

Dev only: the questions are filtered to the dev split as they are read, and the run refuses to start
unless everything frozen under eval/ still matches the freeze tag. The model's replies go to
eval/results/generation-dev-raw.jsonl and the same replies after the checker to
generation-dev-checked.jsonl. Both are in the baseline's line format, so eval/score.py reads them
unchanged. The checked file is always rebuilt from the raw one, so --recheck costs nothing.

Usage:
    python scripts/run_generation.py --dry-run
    python scripts/run_generation.py --smoke --max-spend 0.5 --phase-cap 12
    python scripts/run_generation.py --runs 3 --max-spend 6 --phase-cap 12
    python scripts/run_generation.py --recheck [--smoke]
"""

import argparse
import importlib.util
import json
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import anthropic  # noqa: E402

from advisor.generation import answer  # noqa: E402
from advisor.generation.checker import check  # noqa: E402
from advisor.generation.evidence import user_message  # noqa: E402
from advisor.generation.facts import Facts  # noqa: E402
from advisor.retrieval.pipeline import Pipeline, Spec  # noqa: E402
from advisor.retrieval.units import build_units  # noqa: E402

EVAL = ROOT / "eval"
RESULTS = EVAL / "results"
SHOWN = 10  # R1's top 10, whole
R1 = Spec("R1", bm25="header")
HASHED = ("eval/task.md", "src/advisor/generation/addendum.md")
CODE = ("src", "scripts", "eval/task.md")


def guard_freeze() -> None:
    spec = importlib.util.spec_from_file_location(
        "check_eval_frozen", ROOT / "scripts" / "check_eval_frozen.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    problems = module.check(ROOT)
    if problems:
        raise SystemExit("Frozen files differ from the freeze tag:\n" + "\n".join(problems))


def git(*args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout.strip()  # fmt: skip


def provenance() -> dict:
    """The commit, whether the code differs from it, and the git blob id of the task and the
    addendum as they are on disk, so a run says which prompt it used even before a commit."""
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain", "--", *CODE)),
        "hashes": {Path(name).name: git("hash-object", name) for name in HASHED},
    }


def read_lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def dev_questions(smoke: bool) -> list[dict]:
    questions = [q for q in read_lines(EVAL / "questions.jsonl") if q["split"] == "dev"]
    if not smoke:
        return questions
    first: dict[str, dict] = {}
    for question in questions:
        first.setdefault(question["type"], question)
    return list(first.values())


def result_paths(smoke: bool) -> tuple[Path, Path]:
    stem = "generation-smoke-dev" if smoke else "generation-dev"
    return RESULTS / f"{stem}-raw.jsonl", RESULTS / f"{stem}-checked.jsonl"


def phase_spent() -> float:
    """Everything spent on generation so far, smoke run included."""
    return sum(
        line["cost_usd"]
        for path in RESULTS.glob("generation-*-raw.jsonl")
        for line in read_lines(path)
    )


def open_store(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def run_questions(
    questions: list[dict], pipeline: Pipeline, units_by_id: dict, raw_path: Path, client,
    runs: int, max_spend: float, phase_cap: float, proof: dict,
) -> str:  # fmt: skip
    """Asks every question not yet answered in each run. Stops, with the reason, before a call that
    could take either total over its cap. Each line is written as it arrives, so a crash loses
    nothing and a resume spends nothing twice."""
    system = answer.system_prompt()
    done = read_lines(raw_path)
    spent = sum(x["cost_usd"] for x in done)
    overall = phase_spent()
    answered = {(x["run"], x["id"]) for x in done}
    for run in range(1, runs + 1):
        for question in questions:
            if (run, question["id"]) in answered:
                continue
            started = time.monotonic()
            ranked = pipeline.rank(R1, question["question"])[:SHOWN]
            retrieval = time.monotonic() - started
            shown = [units_by_id[unit_id] for unit_id in ranked]
            message = user_message(shown, question["question"])
            worst = answer.worst_case_call(system, message)
            if spent + worst > max_spend or overall + worst > phase_cap:
                return (
                    f"Stopped at run {run}, {question['id']}: ${spent:.2f} spent here, "
                    f"${overall:.2f} in Phase 4. Caps ${max_spend:.2f} and ${phase_cap:.2f}."
                )
            reply, attempts, seconds = answer.ask(client, answer.build_request(system, message))
            line = answer.result_line(question, run, reply, attempts, seconds, shown, proof)
            line["retrieval_s"] = round(retrieval, 3)
            spent += line["cost_usd"]
            overall += line["cost_usd"]
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True) + "\n")
            print(f"run {run} {question['id']} {line['stop_reason']} ${spent:.2f}", flush=True)
    return f"Done. ${spent:.2f} spent on this file, ${overall:.2f} in Phase 4."


def recheck(
    questions: list[dict], units_by_id: dict, facts: Facts, raw_path: Path, checked_path: Path
) -> Counter:
    """Applies the checker to the saved raw replies and rewrites the checked file. No API call."""
    by_id = {q["id"]: q for q in questions}
    if not read_lines(raw_path):
        raise SystemExit(f"There are no saved replies in {raw_path.name}. Run the questions first.")
    lines = sorted(
        (x for x in read_lines(raw_path) if x["id"] in by_id),
        key=lambda x: (x["run"], list(by_id).index(x["id"])),
    )
    counts: Counter = Counter()
    out = []
    for line in lines:
        shown = [units_by_id[unit_id] for unit_id in line["shown"]]
        checked = check(
            by_id[line["id"]]["question"], line["text"], line["stop_reason"], shown, facts
        )
        counts[(checked.route, checked.verdict)] += 1
        out.append({**line, "text": checked.text, "checker": checked.record()})
    checked_path.write_text(
        "".join(json.dumps(x, sort_keys=True) + "\n" for x in out), encoding="utf-8"
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "advisor.db"))
    parser.add_argument("--smoke", action="store_true", help="the first dev question of each type")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--max-spend", type=float, help="dollars for this results file")
    parser.add_argument("--phase-cap", type=float, help="dollars for all of Phase 4")
    parser.add_argument("--recheck", action="store_true", help="re-apply the checker; no API call")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the first request; call nothing"
    )
    args = parser.parse_args()

    questions = dev_questions(args.smoke)
    raw_path, checked_path = result_paths(args.smoke)
    db = open_store(args.db)
    units = build_units(db)
    units_by_id = {unit.unit_id: unit for unit in units}
    system = answer.system_prompt()

    if args.dry_run:
        pipeline = Pipeline(units)
        first = questions[0]
        ranked = pipeline.rank(R1, first["question"])[:SHOWN]
        message = user_message([units_by_id[i] for i in ranked], first["question"])
        print(f"System prompt: {len(system)} characters. First message: {len(message)} characters.")
        print(f"\n{system}\n---\n{message[:1500]}\n...")
        print(f"\nWorst case for the first call: ${answer.worst_case_call(system, message):.2f}.")
        return 0

    guard_freeze()
    if args.recheck:
        counts = recheck(questions, units_by_id, Facts(db), raw_path, checked_path)
        for (route, verdict), number in sorted(counts.items()):
            print(f"{route:<8}{verdict:<14}{number}")
        print(f"Written to {checked_path.relative_to(ROOT)}")
        return 0

    if args.max_spend is None or args.phase_cap is None:
        print("Give --max-spend and --phase-cap in dollars. The caps are not optional.")
        return 1
    key = answer.read_key()
    if not key:
        print("No ANTHROPIC_API_KEY. Add it to .env (gitignored), then run again.")
        return 1
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    RESULTS.mkdir(parents=True, exist_ok=True)
    print(
        run_questions(
            questions, Pipeline(units), units_by_id, raw_path, client, args.runs,
            args.max_spend, args.phase_cap, provenance(),
        )
    )  # fmt: skip
    counts = recheck(questions, units_by_id, Facts(db), raw_path, checked_path)
    for (route, verdict), number in sorted(counts.items()):
        print(f"{route:<8}{verdict:<14}{number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
