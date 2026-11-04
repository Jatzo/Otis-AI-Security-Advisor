"""Fails when anything frozen under eval-v2/ differs from the Test v2 freeze tag.

Test v2 is the second question set (ADR 0009). It lives apart from eval/ so that the v1 guard,
which holds eval/ to its own tag, is left as it was. The same claim is made for it: the questions,
the gold and the rules were fixed before the system was changed. The tag is the receipt, so this
check compares git blobs with the tag and needs no network. It fails if the tag is missing.

Frozen: every file under eval-v2/ except eval-v2/results/ and eval-v2/errata.jsonl. The errata
file may only grow.

The tag is eval-freeze-test-v2. Its name matches the repository ruleset for eval-freeze-* (so it
cannot be moved or deleted), and not the v1 guard's pattern (so the v1 guard never mistakes it
for a newer version of the v1 freeze).

Usage: python scripts/check_eval_v2_frozen.py [--tag eval-freeze-test-v2]
"""

import argparse
import subprocess
import sys
from pathlib import Path

TAG = "eval-freeze-test-v2"
ERRATA = "eval-v2/errata.jsonl"
NOT_FROZEN_PREFIX = "eval-v2/results/"


def git(repo: Path, *args: str, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        capture_output=True, text=not binary, check=False,
    )  # fmt: skip


def blobs(repo: Path, ref: str) -> dict[str, str]:
    """Path to blob id for every frozen file at a commit."""
    listing = git(repo, "ls-tree", "-r", "--full-tree", ref, "--", "eval-v2").stdout
    result = {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        if path != ERRATA and not path.startswith(NOT_FROZEN_PREFIX):
            result[path] = meta.split()[2]
    return result


def show_errata(repo: Path, ref: str) -> bytes:
    shown = git(repo, "show", f"{ref}:{ERRATA}", binary=True)
    return shown.stdout if shown.returncode == 0 else b""


def check(repo: Path, tag: str = TAG) -> list[str]:
    """Every reason the freeze does not hold, or an empty list."""
    if tag not in git(repo, "tag", "--list", tag).stdout.split():
        return [
            f"The freeze tag {tag} does not exist in this checkout. "
            "Fetch the tags (git fetch --tags, or fetch-depth 0 in CI), or tag the freeze."
        ]
    problems = []
    if git(repo, "merge-base", "--is-ancestor", tag, "HEAD").returncode != 0:
        problems.append(f"{tag} is not an ancestor of HEAD: the history was rewritten.")
    frozen, now = blobs(repo, tag), blobs(repo, "HEAD")
    for path in sorted(set(frozen) | set(now)):
        if path not in now:
            problems.append(f"{path} was deleted after {tag}.")
        elif path not in frozen:
            problems.append(f"{path} is new since {tag}. Anything added needs a new freeze tag.")
        elif frozen[path] != now[path]:
            problems.append(
                f"{path} was changed after {tag}. Append the fix to eval-v2/errata.jsonl instead."
            )
    if not show_errata(repo, "HEAD").startswith(show_errata(repo, tag)):
        problems.append(f"{ERRATA} was edited, not appended to, since {tag}.")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=TAG, help="the tag to hold HEAD to")
    args = parser.parse_args()
    problems = check(Path.cwd(), args.tag)
    for problem in problems:
        print(f"FAIL: {problem}", file=sys.stderr)
    if not problems:
        print("OK: everything frozen under eval-v2/ matches the freeze tag.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
