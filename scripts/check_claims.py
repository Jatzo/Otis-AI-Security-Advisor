"""Checks that every figure in the README is computed from a saved result, not copied by hand.

This is step 1, item 3, of docs/evidence-round-plan.md. The list of claims is in
scripts/claims_data.py. Each claim names a stretch of README text, the figures it shows, and the
computation that gives each figure from a committed file. This script:

1. finds the stretch in the README and the figure inside it;
2. runs the computation and compares it with the figure, to the number of decimals shown;
3. checks that no number in the README prose is left without a claim, except the kinds listed in
   IGNORED (dates, ADR numbers, version names and section references);
4. checks that each source file still has the hash recorded in docs/claims-pins.json. A source
   that changed has to be looked at again, then pinned with `--update-pins`.

A figure in an image cannot be checked, so images are not parsed. The claims marked `manual` say so.

Usage:
    python scripts/check_claims.py              # exit 1 on any problem
    python scripts/check_claims.py --update-pins
    python scripts/check_claims.py --uncovered  # list the numbers that have no claim yet
"""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PINS = ROOT / "docs" / "claims-pins.json"
NUMBER = re.compile(r"\$?\d(?:[\d,]*\d)?(?:\.\d+)?%?")

# Numbers in the README that are labels, not measurements. Each entry is a pattern for the text
# just before the number, one for the text just after it (either may be empty), one the number
# itself must match, and why it is allowed. All are applied after code, links and tags are removed.
MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
ANY = r".*"
IGNORED = [
    (r"(?<![A-Za-z])(?:ADR|Section|section|Phase|round|Test v|step|Step|PEP|SemVer|CC BY|CC0?|"
     r"R|v|FTS|BM)\s*$", "", ANY, "a name"),
    (r"(?<![A-Za-z])(?:top|recall at|question at)\s*$", "", r"10", "the depth"),
    (r"", r"^\s*" + MONTH, ANY, "a date"),
    (r"" + MONTH + r"\s*$", "", ANY, "a year"),
    (r"\d\.$", "", ANY, "part of a version"),
    (r"", r"^\.\d", ANY, "part of a version"),
    (r"\| \[$", "", ANY, "an ADR number in the table"),
    (r"(?<![A-Za-z])[a-z]{1,2}-$", "", ANY, "a question ID"),
    (r"/ p$", "", ANY, "a column heading"),
]  # fmt: skip


@dataclass
class Claim:
    """A stretch of README text and the figures in it, each with the code that makes it."""

    text: str
    shows: list[tuple[str, object]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    manual: str = ""  # why a figure cannot be computed, if so


def decimals(token: str) -> int:
    clean = token.strip("$%").replace(",", "")
    return len(clean.split(".")[1]) if "." in clean else 0


def as_number(token: str) -> float:
    return float(token.strip("$%").replace(",", ""))


def same(token: str, actual: object) -> bool:
    """True when the computed value equals the README token to the decimals the token shows."""
    return abs(float(actual) - as_number(token)) <= 0.5 * 10 ** -decimals(token) + 1e-9


def prose(text: str) -> str:
    """The README with code, links, tags and IDs taken out, so only counted prose is left."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\b(?:GHSA|CVE|BIT)-[\w-]+", " ", text)
    text = re.sub(r"\bclaude-[\w-]+", " ", text)
    return re.sub(r"^#+ .*$|^\d+\. \[.*$", " ", text, flags=re.M)  # headings and the contents list


def sha256(path: Path) -> str:
    """Hash of the file with Windows line endings made Unix ones, so a laptop and CI agree."""
    text = path.read_bytes().replace(bytes([13, 10]), bytes([10]))
    return hashlib.sha256(text).hexdigest()


def load_pins() -> dict[str, str]:
    return json.loads(PINS.read_text(encoding="utf-8")) if PINS.exists() else {}


def run(claims: list[Claim], readme: str, pins: dict[str, str]) -> tuple[list[str], list[str]]:
    """Returns the problems found and the numbers that no claim covers."""
    problems: list[str] = []
    cleaned = prose(readme)
    covered = []  # (start, end) spans of the cleaned text
    for claim in claims:
        start = cleaned.find(claim.text)
        if start < 0:
            problems.append(f"Text not in README: {claim.text[:70]!r}")
            continue
        cursor = 0
        for token, compute in claim.shows:
            at = claim.text.find(token, cursor)
            if at < 0:
                problems.append(f"Figure {token!r} not in its claim text {claim.text[:50]!r}")
                continue
            cursor = at + len(token)
            covered.append((start + at, start + at + len(token)))
            if claim.manual or compute is None:
                continue
            try:
                actual = compute() if callable(compute) else compute
            except (LookupError, ValueError, TypeError, KeyError, StopIteration) as error:
                problems.append(f"{token!r} in {claim.text[:50]!r} could not be computed: {error}")
                continue
            if not same(token, actual):
                problems.append(f"{token!r} in {claim.text[:50]!r} is {actual} in the data")
        for source in claim.sources:
            path = ROOT / source
            if not path.exists():
                problems.append(f"Source missing: {source}")
            elif pins.get(source) != sha256(path):
                problems.append(f"Source changed or not pinned: {source}")
    uncovered = []
    for match in NUMBER.finditer(cleaned):
        if any(a <= match.start() < b for a, b in covered):
            continue
        before = cleaned[max(0, match.start() - 30) : match.start()]
        after = cleaned[match.end() : match.end() + 30]
        if any(
            (re.search(b, before) if b else True)
            and (re.search(a, after) if a else True)
            and re.fullmatch(t, match.group())
            for b, a, t, _ in IGNORED
        ):
            continue
        uncovered.append(f"{match.group()} near {cleaned[match.start() - 25 : match.end() + 25]!r}")
    return problems, uncovered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update-pins", action="store_true")
    parser.add_argument("--uncovered", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / "scripts"))
    from claims_data import CLAIMS  # noqa: PLC0415

    sources = sorted({s for c in CLAIMS for s in c.sources})
    if args.update_pins:
        PINS.write_text(
            json.dumps({s: sha256(ROOT / s) for s in sources}, indent=1) + "\n", encoding="utf-8"
        )
        print(f"Pinned {len(sources)} source files.")
        return 0
    problems, uncovered = run(CLAIMS, README.read_text(encoding="utf-8"), load_pins())
    if args.uncovered:
        print("\n".join(uncovered))
        return 0
    for line in problems:
        print("PROBLEM:", line)
    for line in uncovered:
        print("NO CLAIM:", line)
    done = sum(len(c.shows) for c in CLAIMS)
    print(
        f"{done} figures in {len(CLAIMS)} claims, {len(problems)} problems, "
        f"{len(uncovered)} uncovered."
    )
    return 1 if problems or uncovered else 0


if __name__ == "__main__":
    sys.exit(main())
