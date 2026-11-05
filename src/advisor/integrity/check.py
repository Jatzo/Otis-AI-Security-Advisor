"""The ingest check for a record that lies about its fixed version (red team finding 4).

The answer checker compares a reply with the record it cites, so a record that lies passes. This
looks at the record before it is used. There are two signals, and each can say "cannot check":

R, the release list. The fixed version must be one the package's registry has published. It
   catches a fix that does not exist. It cannot catch a lie that names a real release.
X, the second source. The fixed versions GitHub gives must share a version with the end
   versions NVD gives for the same CVE. It can catch a lie about a real release, but GitHub and
   NVD differ on real advisories too, so X only marks a record unverified and never holds it back.

Only R is ever used to hold a record back. This module writes nothing to the store.
"""

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from functools import cmp_to_key

from advisor import versions

LISTED, NOT_LISTED, CANNOT_CHECK = "listed", "not_listed", "cannot_check"
AGREES, DISAGREES = "agrees", "disagrees"
STABLE = re.compile(r"\d+(\.\d+)*")  # digits and dots only: no a1, rc1, alpha or RELEASE


@dataclass(frozen=True)
class Verdict:
    record_id: str
    release: str  # LISTED, NOT_LISTED or CANNOT_CHECK
    second_source: str  # AGREES, DISAGREES or CANNOT_CHECK
    fixed: tuple[str, ...]


def same_version(compare: Callable[[str, str], int], left: str, right: str) -> bool:
    try:
        return compare(left, right) == 0
    except ValueError:
        return left == right


def release_status(
    ecosystem: str,
    range_type: str,
    fixed: str | None,
    released: list[str] | None,
    refined: bool = False,
) -> str:
    """R for one fixed version. A missing fix, a fix of 0, a token that is not a version (a Maven
    RELEASE) and a package with no list are not judged.

    The refined rule also leaves two things unjudged: a pre-release tag, which registries often do
    not keep, and a version older than the oldest stable release the registry lists, which the list
    cannot speak for. It was written after reading the records the first rule flagged."""
    if not fixed or not released or fixed == "0" or not fixed[0].isdigit():
        return CANNOT_CHECK
    try:
        compare = versions.comparator(ecosystem, range_type)
    except ValueError:
        return CANNOT_CHECK
    if refined:
        if not STABLE.fullmatch(fixed):
            return CANNOT_CHECK
        stable = [v for v in released if STABLE.fullmatch(v)]
        try:
            if stable and compare(fixed, min(stable, key=cmp_to_key(compare))) < 0:
                return CANNOT_CHECK
        except ValueError:  # a version this ecosystem's order cannot read, such as npm's 99.99
            return CANNOT_CHECK
    listed = any(same_version(compare, fixed, version) for version in released)
    return LISTED if listed else NOT_LISTED


def second_source_status(ecosystem: str, range_type: str, ours: set[str], theirs: set[str]) -> str:
    """X for one record: GitHub's fixed versions against NVD's end versions. Sharing one version
    is agreement, which is looser than the sets being equal, because the two often split a fix
    across branches differently."""
    if not ours or not theirs:
        return CANNOT_CHECK
    try:
        compare = versions.comparator(ecosystem, range_type)
    except ValueError:
        compare = lambda a, b: 0 if a == b else 1  # noqa: E731 - plain text when no order exists
    shared = any(same_version(compare, a, b) for a in ours for b in theirs)
    return AGREES if shared else DISAGREES


def check_records(
    db: sqlite3.Connection,
    releases: dict[tuple[str, str], list[str]],
    only: set[str] | None = None,
    refined: bool = False,
) -> dict[str, Verdict]:
    """A verdict for every GitHub record that has a range on a corpus package, or for the named
    records only."""
    ranges: dict[str, list[tuple[str, str, str, str | None]]] = {}
    for record_id, ecosystem, package, range_type, fixed in db.execute(
        "SELECT a.record_id, a.ecosystem, a.package, a.range_type, a.fixed"
        " FROM corpus_affected a JOIN records r ON r.record_id = a.record_id AND r.source = 'ghsa'"
    ):
        if only is None or record_id in only:
            ranges.setdefault(record_id, []).append((ecosystem, package, range_type, fixed))
    nvd_ends: dict[str, set[str]] = {}
    for cve_id, end in db.execute(
        "SELECT record_id, version_end_excluding FROM cpe_matches"
        " WHERE vulnerable = 1 AND version_end_excluding IS NOT NULL"
    ):
        nvd_ends.setdefault(cve_id, set()).add(end)
    cves: dict[str, set[str]] = {}
    for record_id, cve_id in db.execute("SELECT record_id, cve_id FROM record_cves"):
        cves.setdefault(record_id, set()).add(cve_id)

    verdicts = {}
    for record_id, rows in ranges.items():
        states = [
            release_status(eco, kind, fixed, releases.get((eco, package)), refined)
            for eco, package, kind, fixed in rows
            if fixed is not None
        ]
        if NOT_LISTED in states:
            release = NOT_LISTED
        elif LISTED in states:
            release = LISTED
        else:
            release = CANNOT_CHECK
        ours = {fixed for *_, fixed in rows if fixed is not None}
        theirs = {end for cve in cves.get(record_id, ()) for end in nvd_ends.get(cve, ())}
        ecosystem, _, kind, _ = rows[0]
        verdicts[record_id] = Verdict(
            record_id,
            release,
            second_source_status(ecosystem, kind, ours, theirs),
            tuple(sorted(ours)),
        )
    return verdicts


def held_back(verdicts: dict[str, Verdict]) -> set[str]:
    """The records to leave out of retrieval: the ones whose fixed version no registry lists."""
    return {v.record_id for v in verdicts.values() if v.release == NOT_LISTED}


def without(db: sqlite3.Connection, record_ids: set[str]) -> sqlite3.Connection:
    """A copy of the store with the named GitHub records removed. The original is not touched."""
    copy = sqlite3.connect(":memory:")
    db.backup(copy)
    for record_id in record_ids:
        copy.execute("DELETE FROM affected WHERE record_id = ?", (record_id,))
        copy.execute("DELETE FROM aliases WHERE record_id = ?", (record_id,))
        copy.execute("DELETE FROM records WHERE record_id = ? AND source = 'ghsa'", (record_id,))
    return copy
