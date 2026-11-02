"""Checks, before any test row is run, that the system under test is the one that was tagged.

Phase 5 scores the test split once ([docs/test-plan.md](../docs/test-plan.md)). The system is
tagged first and nothing in src/, scripts/ or eval/ may differ from the tag afterwards, except
eval/results/ and eval/errata.jsonl, which grow as results are committed. This check is run before
every row, row B included, because the baseline runner is frozen and has no system-tag check.

Usage:
    python scripts/phase5_preflight.py --row baseline
    python scripts/phase5_preflight.py            # the tag and the tree only
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = "phase5-system-v1"
FROZEN = ["--", "src", "scripts", "eval", ":(exclude)eval/results", ":(exclude)eval/errata.jsonl"]
# One results file per row. Retrieval and structured rows are free and guard themselves.
ROW_FILES = {
    "baseline": "baseline-test.jsonl",
    "generation": "test-generation-raw.jsonl",
    "longcontext": "test-longcontext-raw.jsonl",
}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


def problems(tag: str = TAG, run_git: Callable = git) -> list[str]:
    """Every reason a test row must not start, or an empty list."""
    if run_git("rev-parse", "-q", "--verify", f"refs/tags/{tag}").returncode != 0:
        return [f"The tag {tag} does not exist yet. Tag the system first, then run the rows."]
    found = []
    if run_git("diff", "--quiet", tag, *FROZEN).returncode != 0:
        found.append(f"Something under src/, scripts/ or eval/ differs from {tag}.")
    untracked = run_git("ls-files", "--others", "--exclude-standard", *FROZEN).stdout.split()
    if untracked:
        found.append(f"Untracked files are not in {tag}: {untracked[0]}")
    return found


def row_complete(path: Path, test_ids: set[str]) -> bool:
    """Whether every test question already has a line in the row's results file."""
    if not path.exists():
        return False
    done = {json.loads(x)["id"] for x in path.read_text("utf-8").splitlines() if x.strip()}
    return test_ids <= done


def test_question_ids(root: Path = ROOT) -> set[str]:
    lines = (root / "eval" / "questions.jsonl").read_text("utf-8").splitlines()
    return {q["id"] for q in map(json.loads, lines) if q["split"] == "test"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=TAG)
    parser.add_argument("--row", choices=sorted(ROW_FILES))
    args = parser.parse_args()
    found = problems(args.tag)
    if (
        args.row
        and not found
        and row_complete(ROOT / "eval" / "results" / ROW_FILES[args.row], test_question_ids())
    ):
        found.append(
            f"Every test question already has a reply in the {args.row} row. Test is scored once."
        )
    for line in found:
        print(line)
    if not found:
        print(f"OK: the system matches {args.tag}.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
