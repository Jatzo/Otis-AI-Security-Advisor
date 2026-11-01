"""What a question names: advisory and CVE IDs, and one of the 18 packages.

The patterns come from the ID formats and the package list, not from how any question is
worded. The soft filter only reorders. It never reads a version or a range: working out which
versions are affected is the checker's job, and doing it here would let code answer the question
that retrieval is meant to answer (docs/adr/0001-retrieval-answers-code-checks.md).
"""

import re

from advisor.packages import PACKAGES
from advisor.retrieval.bm25 import IDS
from advisor.retrieval.units import Unit

# Words that are also ordinary English. They count as a package only with a version after
# them, or next to the word package, library or module.
AMBIGUOUS = {"requests", "express", "ws"}
CONTEXT = r"(?:package|library|module|npm|pypi)"
BEFORE = r"(?<![\w.:-])"


def package_patterns() -> dict[str, re.Pattern]:
    patterns = {}
    for _, name in PACKAGES:
        short = name.split(":")[-1]
        if short in AMBIGUOUS:
            word = re.escape(short)
            expression = (
                rf"{BEFORE}{word}(?=\s+v?\d)"
                rf"|{BEFORE}{CONTEXT}\s+{word}(?![\w-])"
                rf"|{BEFORE}{word}\s+{CONTEXT}(?![\w-])"
            )
        else:
            spellings = sorted({name, short}, key=len, reverse=True)
            expression = rf"{BEFORE}(?:{'|'.join(re.escape(s) for s in spellings)})(?![\w-])"
        patterns[name] = re.compile(expression, re.IGNORECASE)
    return patterns


PATTERNS = package_patterns()


def named_ids(query: str) -> set[str]:
    return {found.upper() for found in IDS.findall(query)}


def named_packages(query: str) -> set[str]:
    return {name for name, pattern in PATTERNS.items() if pattern.search(query)}


class Hints:
    """The metadata the soft filter and the two baseline rows need, built once per index."""

    def __init__(self, units: list[Unit]) -> None:
        self.units = {unit.unit_id: unit for unit in units}
        self.by_alias: dict[str, list[str]] = {}
        for unit in units:
            for alias in unit.aliases:
                self.by_alias.setdefault(alias, []).append(unit.unit_id)

    def exact_matches(self, query: str) -> list[str]:
        """B1: every unit that one of the IDs in the question names, by unit id."""
        found = {u for i in named_ids(query) for u in self.by_alias.get(i, [])}
        return sorted(found)

    def whole_packages(self, query: str) -> list[str]:
        """B0: every unit of the packages the question names, by unit id."""
        wanted = named_packages(query)
        return sorted(u.unit_id for u in self.units.values() if u.packages & wanted)

    def soft_filter(self, ranked: list[str], query: str) -> list[str]:
        """R6: exact ID matches first, then units of a named package, then the rest. The order
        inside each group is the ranking that came in."""
        wanted = named_packages(query)
        exact = self.exact_matches(query)
        taken = set(exact)
        named = [u for u in ranked if u not in taken and self.units[u].packages & wanted]
        taken.update(named)
        return exact + named + [u for u in ranked if u not in taken]
