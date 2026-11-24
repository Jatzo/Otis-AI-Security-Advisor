"""The completeness check, exactly as docs/completeness-spec-v1.md fixes it.

When a question asks for a whole list about one package, a reply is withheld unless the model was
shown every record of that package, or the reply says plainly that it covers only part of the list.
Nothing here is a setting: the question test, the phrases and the text are the spec's, and a change
to any of them is a marked amendment to the spec first.

It is off unless a caller passes a Completeness to the checker, so the checker as tagged
phase6-system-v1 is what runs by default.
"""

import re

from advisor.retrieval.candidates import names_one_package
from advisor.retrieval.units import Unit

COMPLETE_TEXT = (
    "Otis was not shown every record for this package, so it cannot give a complete list. "
    "Ask about one version or one advisory ID."
)
RULE = 9
SET_ASK = re.compile(
    r"\b(?:which|what)\s+(?:\w+\s+){0,2}?(?:advisories|versions)\b"
    r"|\b(?:list|name)\s+(?:all|every)\b"
    r"|\ball\s+(?:the\s+)?(?:advisories|versions)\b",
    re.IGNORECASE,
)
YES_NO_START = re.compile(r"\s*(?:is|are|does|do|was|were|can|has|have)\b", re.IGNORECASE)
PARTIAL_PHRASES = (
    "only part of",
    "not a complete list",
    "not the complete list",
    "not the full list",
    "incomplete",
    "may not be complete",
    "there may be more",
    "there may be other",
    "not every advisory",
)


class Completeness:
    """Every unit of each package, built once from the store's units."""

    def __init__(self, units: list[Unit], packages: list[str]) -> None:
        self.packages = list(packages)
        self.scope = {
            package: frozenset(u.unit_id for u in units if package in u.packages)
            for package in self.packages
        }

    def covered(self, question: str) -> str | None:
        """The one package a list question names, or None when the question is not covered."""
        if YES_NO_START.match(question) or not SET_ASK.search(question):
            return None
        return names_one_package(question, self.packages)

    def missing(self, question: str, shown_ids: set[str], explanation: str) -> list[str] | None:
        """The unit ids in scope that were not shown, when the reply must be withheld, else None.

        A reply that says plainly it covers only part of the list is never withheld."""
        package = self.covered(question)
        if package is None:
            return None
        lowered = explanation.lower()
        if any(phrase in lowered for phrase in PARTIAL_PHRASES):
            return None
        absent = sorted(self.scope[package] - shown_ids)
        return absent or None
