"""The retrieval candidates of the evidence round (docs/evidence-round-plan.md, step 2).

Each one takes R1's ranking and returns the list of unit ids that would go to the model. None of
them is wired into the system: they are run on Dev-R by scripts/retrieval_study2.py and adopted
only if the plan's rule says so.

- R1: R1's top 10 (the control).
- R9: R1's top 10 with each unit followed by its linked units.
- R9x: the same, up to 20. Descriptive only.
- R10: the records of the one package the question names, up to 20, else R1's top 10.
- R11: R1's top 20.
- R1 at 15 and 25: descriptive only.
"""

import re

from advisor.retrieval.units import Unit

TOP = 10
DEEP = 20


def r1(ranked: list[str], k: int = TOP) -> list[str]:
    """R1's list at depth k."""
    return ranked[:k]


def cves_of(unit: Unit) -> list[str]:
    return sorted(a for a in unit.aliases if a.startswith("CVE-"))


class Links:
    """Which units are linked to which, from the CVE IDs the units already carry."""

    def __init__(self, units: list[Unit]) -> None:
        self.ids = {u.unit_id for u in units}
        self.unit = {u.unit_id: u for u in units}
        self.advisories_of: dict[str, list[str]] = {}
        for unit in units:
            if unit.source == "ghsa":
                for cve in cves_of(unit):
                    self.advisories_of.setdefault(cve, []).append(unit.unit_id)
        for found in self.advisories_of.values():
            found.sort()

    def of(self, unit_id: str) -> list[str]:
        """Linked unit ids, in the order the plan fixes.

        An advisory: the NVD record of each CVE in its aliases, then the KEV entry of each.
        An NVD record: the advisories that alias its CVE. A KEV entry: the NVD record, then those
        advisories.
        """
        unit = self.unit[unit_id]
        if unit.source == "ghsa":
            cves = cves_of(unit)
            wanted = [f"nvd:{c}" for c in cves] + [f"kev:{c}" for c in cves]
        else:
            cve = unit_id.split(":", 1)[1]
            wanted = ([f"nvd:{cve}"] if unit.source == "kev" else []) + self.advisories_of.get(
                cve, []
            )
        return [w for w in wanted if w in self.ids and w != unit_id]


def r9(ranked: list[str], links: Links, limit: int = TOP) -> list[str]:
    """Walk R1's ranking from the top. Append each unit if it is not in the output yet, then its
    linked units if they are not, and stop at the limit."""
    out: list[str] = []
    for unit_id in ranked:
        for candidate in (unit_id, *links.of(unit_id)):
            if candidate not in out:
                out.append(candidate)
                if len(out) == limit:
                    return out
    return out


def names_one_package(text: str, packages: list[str]) -> str | None:
    """The package the question names, when it names exactly one of them: a whole-word,
    case-insensitive match on the short name (the part after a colon), which finds the full
    name too. Wordings such as 'Log4j Core' are not matched, and the rule is not widened."""
    found = {
        p
        for p in packages
        if re.search(r"(?<![\w.-])" + re.escape(p.split(":")[-1]) + r"(?![\w-])", text, re.I)
    }
    return found.pop() if len(found) == 1 else None


def r10(
    ranked: list[str], units: list[Unit], question: str, packages: list[str], cap: int = DEEP
) -> tuple[list[str], bool]:
    """The list and whether the question was scoped. A scoped list holds the records of the
    package, ordered by R1's ranking and then by ID for those R1 did not match, cut at the cap.
    An unscoped question gets R1's top 10, unchanged."""
    package = names_one_package(question, packages)
    if package is None:
        return ranked[:TOP], False
    members = {u.unit_id for u in units if package in u.packages}
    position = {unit_id: i for i, unit_id in enumerate(ranked)}
    ordered = sorted(members, key=lambda uid: (position.get(uid, len(ranked)), uid))
    return ordered[:cap], True
