"""What the store says, asked one fact at a time.

The checker reads every fact from here and never from the model's text or from the evidence it was
shown. Record ids are in the store's own form: GHSA ids with a lower-case body, CVE ids in upper
case, which is what reading.normal_id produces.
"""

import sqlite3

from advisor.generation.reading import ids_in, normal_id, version_key
from advisor.packages import PACKAGES
from advisor.versions import UnparseableVersion, comparator


def _fold(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def _package_names() -> tuple[dict[str, str], dict[str, str]]:
    """Every spelling the checker accepts, mapped to the corpus name: the plain ones, and the PyPI
    ones that match only after folding - _ and . together. A Maven name matches in full or by its
    artifactId alone, and neither Maven nor npm names are folded."""
    plain: dict[str, str] = {}
    folded: dict[str, str] = {}
    for ecosystem, name in PACKAGES:
        plain[name.lower()] = name
        if ecosystem == "PyPI":
            folded[_fold(name)] = name
        if ecosystem == "Maven":
            plain[name.split(":")[-1].lower()] = name
    return plain, folded


PLAIN_NAMES, FOLDED_NAMES = _package_names()
ECOSYSTEM_OF = {name: ecosystem for ecosystem, name in PACKAGES}


def canonical_package(text: str) -> str | None:
    """The corpus package a name stands for, or None when it is not one of the 18."""
    lowered = text.strip().lower()
    return PLAIN_NAMES.get(lowered) or FOLDED_NAMES.get(_fold(lowered))


def same_version(package: str, left: str, right: str) -> bool:
    """Equal as text after trailing zeros, or equal in the package's own version order. The order
    is how 5.2.20.RELEASE and 5.2.20 are the same Maven version (ADR 0003)."""
    if version_key(left) == version_key(right):
        return True
    ecosystem = ECOSYSTEM_OF[package]
    try:
        return (
            comparator(ecosystem, "SEMVER" if ecosystem == "npm" else "ECOSYSTEM")(left, right) == 0
        )
    except (UnparseableVersion, ValueError):
        return False


class Facts:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def holds_id(self, found: str) -> bool:
        """Whether any record, alias or KEV entry in the store carries this ID."""
        row = self.db.execute(
            "SELECT 1 FROM records WHERE record_id = ? COLLATE NOCASE"
            " UNION SELECT 1 FROM aliases WHERE alias = ? COLLATE NOCASE"
            " UNION SELECT 1 FROM kev WHERE cve_id = ? COLLATE NOCASE",
            (found, found, found),
        ).fetchone()
        return row is not None

    def aliases_of(self, record_id: str) -> set[str]:
        rows = self.db.execute("SELECT alias FROM aliases WHERE record_id = ?", (record_id,))
        return {found for (alias,) in rows for found in ids_in(alias)}

    def records_naming(self, found: str) -> set[str]:
        rows = self.db.execute(
            "SELECT DISTINCT record_id FROM aliases WHERE alias = ? COLLATE NOCASE", (found,)
        )
        return {normal_id(record_id) for (record_id,) in rows}

    def related(self, found: str) -> set[str]:
        """The ID, the aliases its record lists, and the records that list it as an alias."""
        return {found} | self.aliases_of(found) | self.records_naming(found)

    def packages_of(self, record_id: str) -> set[str]:
        rows = self.db.execute(
            "SELECT DISTINCT package FROM corpus_affected WHERE record_id = ?", (record_id,)
        )
        return {package for (package,) in rows}

    def spans(self, record_id: str, package: str) -> list[tuple]:
        """(ecosystem, range_type, introduced, fixed, last_affected) for the corpus package."""
        return self.db.execute(
            "SELECT ecosystem, range_type, introduced, fixed, last_affected FROM corpus_affected"
            " WHERE record_id = ? AND package = ? ORDER BY introduced, fixed, last_affected",
            (record_id, package),
        ).fetchall()

    def record(self, record_id: str, source: str) -> dict | None:
        row = self.db.execute(
            "SELECT severity, cvss3_score, published FROM records"
            " WHERE record_id = ? AND source = ?",
            (record_id, source),
        ).fetchone()
        if row is None:
            return None
        return {"severity": row[0], "cvss3_score": row[1], "published": row[2]}

    def nvd_end_excluding(self, cve: str) -> list[str] | None:
        """The versions NVD gives as the first not affected, or None when no vulnerable CPE row
        exists, which is a claim the code cannot check."""
        rows = self.db.execute(
            "SELECT version_end_excluding FROM cpe_matches WHERE record_id = ? AND vulnerable = 1",
            (cve,),
        ).fetchall()
        if not rows:
            return None
        return [end for (end,) in rows if end]

    def in_kev(self, cve: str) -> bool:
        return (
            self.db.execute("SELECT 1 FROM kev WHERE cve_id = ? COLLATE NOCASE", (cve,)).fetchone()
            is not None
        )
