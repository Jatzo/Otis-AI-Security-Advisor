"""Asks the model each package-naming question with every record of the package in front of it.

Phase 5, row L (docs/test-plan.md). Questions that name no package are not part of this row. The
smoke run is five dev questions that name a package. The test split needs --allow-test, a single
run and the tagged system, and is run once. A question the API refuses is "not asked": it is listed
and left out of the row, never counted wrong for a limit. The replies are in the baseline's line
format, so eval/score.py reads them unchanged.

Usage:
    python scripts/run_longcontext.py --smoke --max-spend 0.6 --phase-cap 12.1
    python scripts/run_longcontext.py --split test --allow-test --max-spend 6 --phase-cap 12.1
"""

import argparse
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import anthropic  # noqa: E402

from advisor.generation import answer  # noqa: E402
from advisor.longcontext import (  # noqa: E402
    ADDENDUM_FILE,
    build_request,
    package_records,
    packages_named,
    system_blocks,
)
from advisor.retrieval.units import build_units  # noqa: E402

RESULTS = ROOT / "eval" / "results"
STORE = ROOT / "data" / "advisor.db"
SMOKE_QUESTIONS = 5
SMOKE_MAX_TOKENS = 40_000
TOKEN_FILE = RESULTS / "phase5-package-tokens.json"


def load_runner():
    """run_generation.py holds the shared guards and helpers: the freeze check, the spend count, the
    test-split rules. Loaded as a module so the two rows keep to the same ones."""
    path = ROOT / "scripts" / "run_generation.py"
    spec = importlib.util.spec_from_file_location("run_generation", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_generation"] = module
    spec.loader.exec_module(module)
    return module


def paths(smoke: bool) -> tuple[Path, Path]:
    stem = "phase5-l-smoke-dev" if smoke else "test-longcontext"
    return RESULTS / f"{stem}-raw.jsonl", RESULTS / f"{stem}-notasked.json"


def package_questions(runner, split: str, smoke: bool) -> list[dict]:
    """The questions that name a package, grouped by package so consecutive calls share a cached
    prefix. The smoke run takes the first few in file order whose package prompt is small (the
    largest package alone would pass the smoke cap), then sorts them the same way."""
    found = [q for q in runner.load_questions(split) if packages_named(q["question"])]
    if smoke:
        small = [q for q in found if small_prompt(packages_named(q["question"]))]
        found = small[:SMOKE_QUESTIONS]
    return sorted(found, key=lambda q: (packages_named(q["question"]), q["id"]))


def small_prompt(packages: list[str]) -> bool:
    counts = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    return sum(counts[p] for p in packages) <= SMOKE_MAX_TOKENS


def prompt_tokens(packages: list[str], blocks: list[dict]) -> int:
    """The measured size of the prefix when the counts file has it, else a generous guess."""
    if TOKEN_FILE.exists():
        counts = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        if all(p in counts for p in packages):
            return sum(counts[p] for p in packages)
    return sum(len(b["text"]) for b in blocks) // 3


def worst_case(tokens: int) -> float:
    """Every input token at full price and the whole output limit spent. Caching only lowers it."""
    price = answer.PRICE
    return (tokens * price["input"] + answer.MAX_TOKENS * price["output"]) / 1_000_000


def provenance(runner) -> dict:
    return {
        "commit": runner.git("rev-parse", "HEAD"),
        "dirty": bool(runner.git("status", "--porcelain", "--", *runner.CODE)),
        "hashes": {
            "task.md": runner.git("hash-object", "eval/task.md"),
            "longcontext_addendum.md": runner.git(
                "hash-object", str(ADDENDUM_FILE.relative_to(ROOT))
            ),
        },
    }


def run_questions(
    runner, questions: list[dict], units: list, raw_path: Path, missed_path: Path, client,
    max_spend: float, phase_cap: float, proof: dict,
) -> str:  # fmt: skip
    """Asks every question without a reply, stopping before a call whose worst case would pass a
    cap. Each line is written as it arrives. A refused prompt goes in the not-asked list."""
    done = runner.read_lines(raw_path)
    if any(line.get("hashes") != proof["hashes"] for line in done):
        raise SystemExit(
            "The saved replies were made with another prompt. One file holds one prompt."
        )
    missed = json.loads(missed_path.read_text(encoding="utf-8")) if missed_path.exists() else []
    answered = {line["id"] for line in done} | {m["id"] for m in missed}
    spent = sum(line["cost_usd"] for line in done)
    overall = runner.phase_spent("test")
    for question in questions:
        if question["id"] in answered:
            continue
        packages = packages_named(question["question"])
        blocks = system_blocks(package_records(units, packages))
        worst = worst_case(prompt_tokens(packages, blocks))
        if spent + worst > max_spend or overall + worst > phase_cap:
            return (
                f"Stopped at {question['id']}: ${spent:.2f} spent here, ${overall:.2f} in the "
                f"phase. Caps ${max_spend:.2f} and ${phase_cap:.2f}."
            )
        request = build_request(blocks, question["question"])
        try:
            reply, attempts, seconds = answer.ask(client, request)
        except anthropic.BadRequestError as refused:
            if "too long" not in str(refused).lower():
                raise  # a fault in the request is not a question the API refused for its size
            missed.append({"id": question["id"], "reason": str(refused)[:300]})
            missed_path.write_text(json.dumps(missed, indent=1) + "\n", encoding="utf-8")
            print(f"{question['id']} not asked", flush=True)
            continue
        line = answer.result_line(question, 1, reply, attempts, seconds, [], proof)
        line["packages"] = packages
        spent += line["cost_usd"]
        overall += line["cost_usd"]
        with raw_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, sort_keys=True) + "\n")
        print(f"{question['id']} {line['stop_reason']} ${spent:.2f}", flush=True)
    return f"Done. ${spent:.2f} spent on this file, ${overall:.2f} in the phase."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="five dev questions naming a package")
    parser.add_argument("--max-spend", type=float)
    parser.add_argument("--phase-cap", type=float)
    parser.add_argument(
        "--dry-run", action="store_true", help="dev only: size prompts, call nothing"
    )
    args = parser.parse_args()
    runner = load_runner()
    if args.split == "dev" and not args.smoke:
        print("On dev this row only has the smoke run: give --smoke.")
        return 1
    if args.split == "test" and args.smoke:
        print("The smoke run is on dev.")
        return 1

    if args.split == "test" and not TOKEN_FILE.exists():
        print(f"{TOKEN_FILE.name} is missing: run scripts/count_package_tokens.py first.")
        return 1
    questions = package_questions(runner, args.split, args.smoke)
    raw_path, missed_path = paths(args.smoke)
    if args.split == "test":
        wording = SimpleNamespace(
            allow_test=args.allow_test, runs=1, dry_run=args.dry_run, recheck=False
        )
        stop = runner.test_problem(wording, raw_path, questions, runner.load_preflight().problems)
        if stop:
            print(stop)
            return 1
    db = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    units = build_units(db)

    if args.dry_run:
        for q in questions:
            names = packages_named(q["question"])
            blocks = system_blocks(package_records(units, names))
            print(f"{q['id']}  {', '.join(names)}  about {prompt_tokens(names, blocks)} tokens")
        return 0

    runner.guard_freeze()
    if args.max_spend is None or args.phase_cap is None:
        print("Give --max-spend and --phase-cap in dollars. The caps are not optional.")
        return 1
    key = answer.read_key()
    if not key:
        print("No ANTHROPIC_API_KEY. Add it to .env (gitignored), then run again.")
        return 1
    proof = provenance(runner)
    if proof["dirty"]:
        print("The code or the prompt files differ from the commit. Commit them first.")
        return 1
    client = anthropic.Anthropic(api_key=key, max_retries=0)
    RESULTS.mkdir(parents=True, exist_ok=True)
    print(
        run_questions(
            runner, questions, units, raw_path, missed_path, client, args.max_spend,
            args.phase_cap, proof,
        )
    )  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
