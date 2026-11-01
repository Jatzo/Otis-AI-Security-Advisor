"""Fails when anything frozen under eval/ differs from the freeze tag.

The claim in the write-up is that the questions, the gold, the rules and the scorer were fixed
before any system was run against them. The tag is the receipt for that claim, so this check
compares git blobs with the tag and needs no network. It fails if the tag is missing, because a
freeze that cannot be shown is not a freeze.

Frozen: every file under eval/ except eval/results/ and eval/errata.jsonl. The errata file may
only grow: what the tag held must still be its first bytes.

Usage: python scripts/check_eval_frozen.py [--tag eval-freeze-v1.1]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

TAG_PATTERN = re.compile(r"eval-freeze-v(\d+(?:\.\d+)*)")
ERRATA = "eval/errata.jsonl"
NOT_FROZEN_PREFIX = "eval/results/"


def git(repo: Path, *args: str, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        capture_output=True, text=not binary, check=False,
    )  # fmt: skip


def freeze_tags(repo: Path) -> list[str]:
    """Freeze tags, oldest first by version number (v1 before v1.1 before v2)."""
    names = git(repo, "tag", "--list", "eval-freeze-v*").stdout.split()
    found = [n for n in names if TAG_PATTERN.fullmatch(n)]
    return sorted(
        found, key=lambda n: [int(p) for p in TAG_PATTERN.fullmatch(n).group(1).split(".")]
    )


def blobs(repo: Path, ref: str) -> dict[str, str]:
    """Path to blob id for every frozen file at a commit."""
    listing = git(repo, "ls-tree", "-r", "--full-tree", ref, "--", "eval").stdout
    result = {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        if path != ERRATA and not path.startswith(NOT_FROZEN_PREFIX):
            result[path] = meta.split()[2]
    return result


def show_errata(repo: Path, ref: str) -> bytes:
    shown = git(repo, "show", f"{ref}:{ERRATA}", binary=True)
    return shown.stdout if shown.returncode == 0 else b""


def check(repo: Path, tag: str | None = None) -> list[str]:
    """Every reason the freeze does not hold, or an empty list."""
    tags = freeze_tags(repo)
    tag = tag or (tags[-1] if tags else None)
    if tag is None or tag not in tags:
        return [
            f"The freeze tag {tag or 'eval-freeze-v1'} does not exist in this checkout. "
            "Fetch the tags (git fetch --tags, or fetch-depth 0 in CI), or tag the freeze."
        ]
    problems = []
    for earlier in tags:
        if git(repo, "merge-base", "--is-ancestor", earlier, "HEAD").returncode != 0:
            problems.append(f"{earlier} is not an ancestor of HEAD: the history was rewritten.")
    frozen, now = blobs(repo, tag), blobs(repo, "HEAD")
    for path in sorted(set(frozen) | set(now)):
        if path not in now:
            problems.append(f"{path} was deleted after {tag}.")
        elif path not in frozen:
            problems.append(
                f"{path} is new since {tag}. Anything added under eval/ needs a new freeze tag."
            )
        elif frozen[path] != now[path]:
            problems.append(
                f"{path} was changed after {tag}. Append the fix to eval/errata.jsonl instead."
            )
    if not show_errata(repo, "HEAD").startswith(show_errata(repo, tag)):
        problems.append(f"{ERRATA} was edited, not appended to, since {tag}.")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="the tag to hold HEAD to (default: the newest freeze tag)")
    args = parser.parse_args()
    problems = check(Path.cwd(), args.tag)
    for problem in problems:
        print(f"FAIL: {problem}", file=sys.stderr)
    if not problems:
        print("OK: everything frozen under eval/ matches the freeze tag.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
