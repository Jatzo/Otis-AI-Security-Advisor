"""Runs the generation and checker on the dev questions, as fixed in docs/generation-plan.md and
docs/generation-plan-2.md.

Dev only: the questions are filtered to the dev split as they are read, and the run refuses to start
unless everything frozen under eval/ still matches the freeze tag. The model's replies go to
eval/results/generation-dev-raw.jsonl and the same replies after the checker to
generation-dev-checked.jsonl. Both are in the baseline's line format, so eval/score.py reads them
unchanged. The checked file is always rebuilt from the raw one, so --recheck costs nothing.

--label v2 writes generation-v2-dev-*.jsonl instead, so a run with a changed prompt never lands in
an earlier run's files. A results file is never appended to with a different prompt, and a paid run
refuses to start when the code or the prompt files differ from the commit.

Usage:
    python scripts/run_generation.py --dry-run
    python scripts/run_generation.py --smoke --max-spend 0.5 --phase-cap 12
    python scripts/run_generation.py --runs 3 --max-spend 6 --phase-cap 12
    python scripts/run_generation.py --label v2 --runs 3 --max-spend 5 --phase-cap 12
    python scripts/run_generation.py --recheck [--smoke | --label v2]
    python scripts/run_generation.py --recheck --recheck-to eval/results/NAME-phase6.jsonl
"""

import argparse
import importlib.util
import json
import re
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


def load_questions(split: str, smoke: bool = False) -> list[dict]:
    """The questions of one split, filtered as they are read. The smoke run is dev only."""
    questions = [q for q in read_lines(EVAL / "questions.jsonl") if q["split"] == split]
    if not smoke:
        return questions
    first: dict[str, dict] = {}
    for question in questions:
        first.setdefault(question["type"], question)
    return list(first.values())


def dev_questions(smoke: bool) -> list[dict]:
    return load_questions("dev", smoke)


def result_paths(smoke: bool, label: str | None = None, split: str = "dev") -> tuple[Path, Path]:
    """The raw and checked files. A label (v2) names a run made with a changed prompt, and cannot
    be combined with the smoke run, so each file name says one thing."""
    if label is not None and not re.fullmatch(r"[a-z0-9]+", label):
        raise SystemExit(f"The label {label!r} must be lower-case letters and digits only.")
    if smoke and label is not None:
        raise SystemExit("Use --smoke or --label, not both.")
    if split == "test":
        if smoke or label is not None:
            raise SystemExit("The test run has no smoke run and no label: it is run once.")
        return RESULTS / "test-generation-raw.jsonl", RESULTS / "test-generation-checked.jsonl"
    stem = (
        "generation-smoke-dev"
        if smoke
        else f"generation-{label}-dev"
        if label
        else "generation-dev"
    )
    return RESULTS / f"{stem}-raw.jsonl", RESULTS / f"{stem}-checked.jsonl"


def recheck_target(recheck_to: str | None, default: Path) -> Path:
    """Where a recheck writes. By default it is the checked file next to the raw one. A path given
    with --recheck-to must not end in -checked.jsonl or -raw.jsonl, the names every committed
    results file has, so a recheck with a changed checker can never land over the file of an earlier
    system or over the paid replies."""
    if recheck_to is None:
        return default
    path = Path(recheck_to).resolve()
    if path.name.endswith(("-checked.jsonl", "-raw.jsonl")):
        raise SystemExit(
            f"{path.name} would take the name of a results file. Give --recheck-to a name that "
            "does not end in -checked.jsonl or -raw.jsonl, such as NAME-checked-phase6.jsonl."
        )
    return path


def dirty_problem(proof: dict) -> str | None:
    """A paid run must be made from committed code and prompt, so the result lines name a commit
    that really produced them."""
    if proof["dirty"]:
        return (
            "The code or the prompt files differ from the commit. Commit them first, "
            "then run again."
        )
    return None


def mixed_prompt(done: list[dict], proof: dict) -> str | None:
    """Says why a file must not be appended to: a line in it was made with another addendum or
    task text, and a resumed run would mix two prompts in one file."""
    if any(line.get("hashes") != proof["hashes"] for line in done):
        return (
            "The saved replies in this file were made with a different addendum or task text. "
            "Use a new --label for the new prompt, so one file holds one prompt."
        )
    return None


def spend_files(split: str = "dev") -> list[Path]:
    """The files a phase's cap counts. Phase 4 is every generation run on dev. Phase 5 is every test
    row, the baseline's test file and the long-context smoke run, so neither blocks the other."""
    if split == "test":
        return [
            *RESULTS.glob("test-*-raw.jsonl"),
            RESULTS / "baseline-test.jsonl",
            *RESULTS.glob("phase5-l-smoke-dev-*raw.jsonl"),
        ]
    return list(RESULTS.glob("generation-*-raw.jsonl"))


def phase_spent(split: str = "dev") -> float:
    """Everything spent in the phase so far, smoke runs included."""
    return sum(line["cost_usd"] for path in spend_files(split) for line in read_lines(path))


def load_preflight():
    spec = importlib.util.spec_from_file_location(
        "phase5_preflight", ROOT / "scripts" / "phase5_preflight.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_problem(args, raw_path: Path, questions: list[dict], preflight_problems) -> str | None:
    """Says why the test split must not be run, or None. Test is scored once: one run, asked for by
    name, from the tagged system, and never a dry run, which would print a test question."""
    if not args.allow_test:
        return "Test is scored once per system: give --allow-test."
    if args.runs != 1:
        return "Test is scored once per system: a single run."
    if args.dry_run:
        return "A dry run on test would print a test question. Dry runs are on dev only."
    if args.recheck:
        return None
    done = {line["id"] for line in read_lines(raw_path)}
    if {q["id"] for q in questions} <= done:
        return "Every test question already has a reply. Test is scored once."
    found = preflight_problems()
    return found[0] if found else None


def open_store(path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def run_questions(
    questions: list[dict], pipeline: Pipeline, units_by_id: dict, raw_path: Path, client,
    runs: int, max_spend: float, phase_cap: float, proof: dict, split: str = "dev",
) -> str:  # fmt: skip
    """Asks every question not yet answered in each run. Stops, with the reason, before a call that
    could take either total over its cap. Each line is written as it arrives, so a crash loses
    nothing and a resume spends nothing twice."""
    system = answer.system_prompt()
    done = read_lines(raw_path)
    problem = mixed_prompt(done, proof)
    if problem:
        raise SystemExit(problem)
    spent = sum(x["cost_usd"] for x in done)
    overall = phase_spent(split)
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
                    f"${overall:.2f} in the phase. Caps ${max_spend:.2f} and ${phase_cap:.2f}."
                )
            reply, attempts, seconds = answer.ask(client, answer.build_request(system, message))
            line = answer.result_line(question, run, reply, attempts, seconds, shown, proof)
            line["retrieval_s"] = round(retrieval, 3)
            spent += line["cost_usd"]
            overall += line["cost_usd"]
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True) + "\n")
            print(f"run {run} {question['id']} {line['stop_reason']} ${spent:.2f}", flush=True)
    return f"Done. ${spent:.2f} spent on this file, ${overall:.2f} in the phase."


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
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--allow-test", action="store_true", help="test is scored once")
    parser.add_argument("--smoke", action="store_true", help="the first dev question of each type")
    parser.add_argument("--label", help="names the results files for a run with a changed prompt")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--max-spend", type=float, help="dollars for this results file")
    parser.add_argument("--phase-cap", type=float, help="dollars for the whole phase")
    parser.add_argument("--recheck", action="store_true", help="re-apply the checker; no API call")
    parser.add_argument(
        "--recheck-to", help="with --recheck, write here and leave the checked file as it is"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the first request; call nothing"
    )
    args = parser.parse_args()

    if args.recheck_to and not args.recheck:
        print("--recheck-to only goes with --recheck.")
        return 1
    questions = load_questions(args.split, args.smoke)
    raw_path, checked_path = result_paths(args.smoke, args.label, args.split)
    if args.split == "test":
        problem = test_problem(args, raw_path, questions, load_preflight().problems)
        if problem:
            print(problem)
            return 1
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
        checked_path = recheck_target(args.recheck_to, checked_path)
        counts = recheck(questions, units_by_id, Facts(db), raw_path, checked_path)
        if args.split == "dev":  # nothing about test outcomes is shown before all rows are in
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
    proof = provenance()
    problem = dirty_problem(proof)
    if problem:
        print(problem)
        return 1
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    RESULTS.mkdir(parents=True, exist_ok=True)
    print(
        run_questions(
            questions, Pipeline(units), units_by_id, raw_path, client, args.runs,
            args.max_spend, args.phase_cap, proof, args.split,
        )
    )  # fmt: skip
    counts = recheck(questions, units_by_id, Facts(db), raw_path, checked_path)
    if args.split == "dev":
        for (route, verdict), number in sorted(counts.items()):
            print(f"{route:<8}{verdict:<14}{number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
