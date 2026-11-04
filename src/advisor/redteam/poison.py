"""Putting an attack case into a copy of the store.

The clean store is never written to: the runner opens a fresh in-memory copy for each case and
applies the case to that. An edit that cannot find its record raises, so a case that would have
poisoned nothing cannot pass quietly.
"""

import hashlib
import sqlite3

from advisor import store
from advisor.redteam.spec import Case, NewRecord
from advisor.retrieval.units import Unit, build_units

JOINERS = {"summary": " ", "details": "\n\n", "nvd_details": "\n\n"}


def range_type_for(db: sqlite3.Connection, ecosystem: str) -> str:
    """The range type the store already holds for this ecosystem (SEMVER for npm, ECOSYSTEM for
    PyPI), so a made-up record is read by the same version order as a real one. An ecosystem the
    store has never seen raises, because there is no real record to copy the type from."""
    row = db.execute(
        "SELECT range_type FROM affected WHERE ecosystem = ?"
        " GROUP BY range_type ORDER BY COUNT(*) DESC, range_type LIMIT 1",
        (ecosystem,),
    ).fetchone()
    if row is None:
        raise ValueError(f"No stored range type for the ecosystem {ecosystem}")
    return row[0]


def osv_record(new: NewRecord, range_type: str) -> dict:
    return {
        "id": new.record_id,
        "aliases": list(new.aliases),
        "summary": new.summary,
        "details": new.summary,
        "published": "2026-10-30T00:00:00Z",
        "database_specific": {"severity": new.severity},
        "severity": [],
        "affected": [
            {
                "package": {"ecosystem": new.ecosystem, "name": new.package},
                "ranges": [
                    {"type": range_type, "events": [{"introduced": "0"}, {"fixed": new.fixed}]}
                ],
            }
        ],
    }


def apply(db: sqlite3.Connection, case: Case) -> None:
    for edit in case.edits:
        source = "nvd" if edit.field == "nvd_details" else "ghsa"
        kind, _, record_id = edit.unit.partition(":")
        if kind != source:
            raise ValueError(f"{case.case_id}: {edit.unit} cannot take a {edit.field} edit")
        column = "summary" if edit.field == "summary" else "details"
        done = db.execute(
            f"UPDATE records SET {column} = COALESCE({column}, '') || ? || ?"  # noqa: S608 - fixed names
            " WHERE record_id = ? AND source = ?",
            (JOINERS[edit.field], edit.text, record_id, source),
        )
        if done.rowcount != 1:
            raise ValueError(f"{case.case_id}: no {source} record {record_id} to edit")
    if case.new_record is not None:
        taken = db.execute(
            "SELECT 1 FROM records WHERE record_id = ?", (case.new_record.record_id,)
        ).fetchone()
        if taken:
            raise ValueError(f"{case.case_id}: {case.new_record.record_id} already exists")
        range_type = range_type_for(db, case.new_record.ecosystem)
        store.load_ghsa(db, osv_record(case.new_record, range_type), "0" * 64)


def touched(case: Case) -> list[str]:
    ids = [edit.unit for edit in case.edits]
    if case.new_record is not None:
        ids.append(f"ghsa:{case.new_record.record_id}")
    return sorted(set(ids))


def digest(units: list[Unit], unit_ids: list[str]) -> str:
    """A hash of the text of the named units, as the model would be shown it."""
    wanted = {u.unit_id: u for u in units if u.unit_id in unit_ids}
    missing = set(unit_ids) - set(wanted)
    if missing:
        raise ValueError(f"No unit {sorted(missing)} to hash")
    hasher = hashlib.sha256()
    for unit_id in sorted(wanted):
        unit = wanted[unit_id]
        hasher.update(f"{unit.unit_id}\n{unit.header}\n{unit.body}\n".encode())
    return hasher.hexdigest()


def poisoned_digest(clean: sqlite3.Connection, case: Case) -> str:
    """Applies the case to a throwaway copy of the open store and hashes what it touched."""
    copy = sqlite3.connect(":memory:")
    clean.backup(copy)
    apply(copy, case)
    ids = touched(case)
    result = digest(build_units(copy), ids) if ids else ""
    copy.close()
    return result


def delivered(case: Case, shown_ids: list[str]) -> bool:
    """Whether the poison was in front of the model. A case with no edit has nothing to deliver."""
    ids = touched(case)
    return all(unit_id in shown_ids for unit_id in ids) if ids else True
