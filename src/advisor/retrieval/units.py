"""The units that retrieval searches: one per advisory, NVD record and linked KEV entry.

Each unit gets a header written only from its own record, so a GitHub header never carries an
NVD score and the sources stay separate. The header holds no KEV flag: that is a join across
sources, and putting it in the text would make the KEV questions single-hop. Package and alias
metadata for the soft filter is kept beside the text, not inside it.
"""

import sqlite3
from dataclasses import dataclass

HEADER_LIMIT = 700
MAX_PAIRS = 6
MAX_PACKAGES = 3
MAX_PRODUCTS = 3
WINDOW = 1600
OVERLAP = 200


@dataclass(frozen=True)
class Unit:
    unit_id: str  # ghsa:GHSA-..., nvd:CVE-... or kev:CVE-...; a hit never counts across namespaces
    source: str
    header: str
    body: str
    packages: frozenset[str]  # for the soft filter only
    aliases: frozenset[str]  # every ID that names this unit, upper case


@dataclass(frozen=True)
class Doc:
    """One searchable piece of a unit. Unsplit units have one doc whose id is the unit id."""

    doc_id: str
    unit_id: str
    header: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.header}\n{self.body}".strip()


def build_units(db: sqlite3.Connection) -> list[Unit]:
    """Every unit in the store, ordered by unit id so ties break the same way everywhere."""
    packages_of = packages_by_cve(db)
    units = [*ghsa_units(db), *nvd_units(db, packages_of), *kev_units(db, packages_of)]
    return sorted(units, key=lambda unit: unit.unit_id)


def packages_by_cve(db: sqlite3.Connection) -> dict[str, frozenset[str]]:
    rows = db.execute(
        "SELECT rc.cve_id, a.package FROM record_cves rc"
        " JOIN corpus_affected a ON a.record_id = rc.record_id"
        " JOIN records r ON r.record_id = rc.record_id AND r.source = 'ghsa'"
    )
    found: dict[str, set[str]] = {}
    for cve_id, package in rows:
        found.setdefault(cve_id, set()).add(package)
    return {cve: frozenset(names) for cve, names in found.items()}


def ghsa_units(db: sqlite3.Connection) -> list[Unit]:
    units = []
    query = (
        "SELECT record_id, published, severity, cvss3_score, summary, details"
        " FROM records WHERE source = 'ghsa'"
    )
    for record_id, published, severity, score, summary, details in db.execute(query).fetchall():
        spans = db.execute(
            "SELECT ecosystem, package, introduced, fixed, last_affected FROM corpus_affected"
            " WHERE record_id = ? ORDER BY ecosystem, package, introduced, fixed",
            (record_id,),
        ).fetchall()
        aliases = [
            a for (a,) in db.execute("SELECT alias FROM aliases WHERE record_id = ?", (record_id,))
        ]
        packages = sorted({(eco, name) for eco, name, *_ in spans})
        parts = [f"GitHub advisory {record_id}."]
        if packages:
            named = ", ".join(f"{name} ({eco})" for eco, name in packages[:MAX_PACKAGES])
            parts.append(f"Package: {named}.")
        parts.append(f"Published {(published or '')[:10]}.")
        label = f"Severity {severity}" if severity else "No severity label"
        parts.append(f"{label}, CVSS v3 {score}." if score is not None else f"{label}.")
        tail = f"Aliases: {', '.join(aliases)}." if aliases else ""
        units.append(
            Unit(
                f"ghsa:{record_id}", "ghsa", fit_header(parts, spans, tail),
                "\n".join(x for x in (summary, details) if x),
                frozenset(name for _, name, *_ in spans),
                frozenset({record_id.upper(), *(a.upper() for a in aliases)}),
            )
        )  # fmt: skip
    return units


def span_text(introduced: str | None, fixed: str | None, last_affected: str | None) -> str:
    start = f"from {introduced}" if introduced else "from the first version"
    if fixed:
        return f"{start} before {fixed}"
    if last_affected:
        return f"{start} through {last_affected}"
    return f"{start}, no fix listed"


def fit_header(parts: list[str], spans: list[tuple], tail: str) -> str:
    """Builds a header of at most HEADER_LIMIT characters. The affected ranges give way first."""
    shown = min(len(spans), MAX_PAIRS)
    while True:
        pairs = [f"{name} {span_text(*rest)}" for _, name, *rest in spans[:shown]]
        more = len(spans) - shown
        if more:
            pairs.append(f"and {more} more")
        affected = f"Affected: {'; '.join(pairs)}." if pairs else ""
        header = " ".join(x for x in (*parts, affected, tail) if x)
        if len(header) <= HEADER_LIMIT or shown <= 1:
            return header[:HEADER_LIMIT]
        shown -= 1


def nvd_units(db: sqlite3.Connection, packages_of: dict[str, frozenset[str]]) -> list[Unit]:
    units = []
    query = (
        "SELECT record_id, published, status, cvss3_score, details"
        " FROM records WHERE source = 'nvd'"
    )
    for record_id, published, status, score, details in db.execute(query).fetchall():
        products = []
        for (criteria,) in db.execute(
            "SELECT DISTINCT criteria FROM cpe_matches WHERE record_id = ? ORDER BY criteria",
            (record_id,),
        ):
            fields = criteria.split(":")
            product = ":".join(fields[3:5]) if len(fields) > 4 else criteria
            if product not in products:
                products.append(product)
        parts = [f"NVD record {record_id}.", f"Status {status}." if status else ""]
        parts.append(f"Published {(published or '')[:10]}.")
        parts.append(f"CVSS v3 {score}." if score is not None else "No CVSS v3 score.")
        if products:
            parts.append(f"Products: {', '.join(products[:MAX_PRODUCTS])}.")
        header = " ".join(x for x in parts if x)[:HEADER_LIMIT]
        units.append(
            Unit(
                f"nvd:{record_id}", "nvd", header, details or "",
                packages_of.get(record_id, frozenset()), frozenset({record_id.upper()}),
            )
        )  # fmt: skip
    return units


def kev_units(db: sqlite3.Connection, packages_of: dict[str, frozenset[str]]) -> list[Unit]:
    """Only KEV entries whose CVE some corpus advisory names: the rest are not about these
    packages."""
    units = []
    query = (
        "SELECT cve_id, vendor, product, name, date_added, ransomware FROM kev"
        " WHERE cve_id IN (SELECT cve_id FROM record_cves)"
    )
    for cve_id, vendor, product, name, added, ransomware in db.execute(query).fetchall():
        header = (
            f"CISA KEV entry {cve_id}. Vendor {vendor}, product {product}. "
            f"Added to the catalogue {added}. Used in ransomware campaigns: {ransomware}."
        )[:HEADER_LIMIT]
        units.append(
            Unit(
                f"kev:{cve_id}", "kev", header, name or "",
                packages_of.get(cve_id, frozenset()), frozenset({cve_id.upper()}),
            )
        )  # fmt: skip
    return units


def whole_docs(units: list[Unit]) -> list[Doc]:
    return [Doc(u.unit_id, u.unit_id, u.header, u.body) for u in units]


def split_docs(units: list[Unit]) -> list[Doc]:
    """Rung R7: records over WINDOW characters become overlapping windows, header repeated."""
    docs = []
    for unit in units:
        if len(unit.body) <= WINDOW:
            docs.append(Doc(unit.unit_id, unit.unit_id, unit.header, unit.body))
            continue
        start, number = 0, 0
        while start < len(unit.body):
            piece = unit.body[start : start + WINDOW]
            docs.append(Doc(f"{unit.unit_id}#{number}", unit.unit_id, unit.header, piece))
            if start + WINDOW >= len(unit.body):
                break
            start += WINDOW - OVERLAP
            number += 1
    return docs


def collapse(doc_ids: list[str], docs: list[Doc]) -> list[str]:
    """Turns a ranked list of doc ids into unique unit ids, keeping the first hit of each, so
    that k always counts records and never pieces of one record."""
    unit_of = {doc.doc_id: doc.unit_id for doc in docs}
    seen: set[str] = set()
    ranked = []
    for doc_id in doc_ids:
        unit_id = unit_of[doc_id]
        if unit_id not in seen:
            seen.add(unit_id)
            ranked.append(unit_id)
    return ranked
