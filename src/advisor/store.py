"""The normalised store: one SQLite file built from the raw snapshot, never edited by hand.

Each source keeps its own rows. A CVE described by both GitHub and NVD appears twice,
once per source, because the two often disagree on severity or affected versions, and
that disagreement is something the system has to show rather than average away.

Join records to CVEs through the record_cves view, never by picking one CVE per record:
a GitHub advisory can name several CVEs (GHSA-j7hp-h8jx-5ppr names two), and which one
comes first is an accident of upstream ordering.
"""

import sqlite3
from pathlib import Path

from cvss import CVSS3, CVSS4

from advisor.ingest import raw
from advisor.ingest.kev import CATALOGUE_ID

SCHEMA = """
CREATE TABLE records (
    record_id     TEXT PRIMARY KEY,   -- GHSA-... or CVE-...
    source        TEXT NOT NULL CHECK (source IN ('ghsa', 'nvd')),
    published     TEXT,
    modified      TEXT,
    status        TEXT,               -- NVD analysis status, e.g. 'Analyzed', 'Awaiting Analysis'
    summary       TEXT,
    details       TEXT,
    severity      TEXT,               -- GitHub's own label: LOW, MODERATE, HIGH, CRITICAL
    cvss3_vector  TEXT,
    cvss3_score   REAL,
    cvss4_vector  TEXT,
    cvss4_score   REAL,
    raw_sha256    TEXT NOT NULL
);
CREATE TABLE aliases (record_id TEXT NOT NULL, alias TEXT NOT NULL);
CREATE TABLE affected (
    record_id     TEXT NOT NULL,
    ecosystem     TEXT NOT NULL,
    package       TEXT NOT NULL,
    range_type    TEXT NOT NULL,      -- ECOSYSTEM or SEMVER, as OSV gives it
    introduced    TEXT,
    fixed         TEXT,               -- NULL with last_affected NULL means still unfixed
    last_affected TEXT
);
CREATE TABLE cpe_matches (
    record_id                 TEXT NOT NULL,
    criteria                  TEXT NOT NULL,
    vulnerable                INTEGER NOT NULL,
    version_start_including   TEXT,
    version_start_excluding   TEXT,
    version_end_including     TEXT,
    version_end_excluding     TEXT
);
CREATE TABLE kev (
    cve_id        TEXT PRIMARY KEY,
    vendor        TEXT,
    product       TEXT,
    name          TEXT,
    date_added    TEXT,
    ransomware    TEXT,
    catalogue     TEXT NOT NULL
);
CREATE INDEX aliases_by_alias ON aliases (alias);
-- Every (record, CVE) pair: a GitHub advisory's CVE aliases, and an NVD record's own ID.
CREATE VIEW record_cves AS
    SELECT record_id, alias AS cve_id FROM aliases WHERE alias LIKE 'CVE-%'
    UNION SELECT record_id, record_id FROM records WHERE source = 'nvd';
CREATE INDEX affected_by_package ON affected (ecosystem, package);
"""

ROW_COUNTS = {
    "records": "SELECT COUNT(*) FROM records",
    "aliases": "SELECT COUNT(*) FROM aliases",
    "affected": "SELECT COUNT(*) FROM affected",
    "cpe_matches": "SELECT COUNT(*) FROM cpe_matches",
    "kev": "SELECT COUNT(*) FROM kev",
}


def build(raw_root: Path, db_path: Path) -> dict[str, int]:
    """Rebuild the store from scratch and return row counts per table."""
    db_path.unlink(missing_ok=True)
    db = sqlite3.connect(db_path)
    try:
        db.executescript(SCHEMA)
        for path in raw.record_paths(raw_root / "osv"):
            load_ghsa(db, raw.read_record(path), raw.sha256_of(path))
        for path in raw.record_paths(raw_root / "nvd"):
            load_nvd(db, raw.read_record(path), raw.sha256_of(path))
        kev_path = raw_root / "kev" / f"{CATALOGUE_ID}.json"
        if kev_path.exists():
            load_kev(db, raw.read_record(kev_path))
        db.commit()
        return {table: db.execute(query).fetchone()[0] for table, query in ROW_COUNTS.items()}
    finally:
        db.close()


def load_ghsa(db: sqlite3.Connection, record: dict, sha256: str) -> None:
    aliases = record.get("aliases", [])
    vectors = {s["type"]: s["score"] for s in record.get("severity", [])}
    cvss3, cvss4 = vectors.get("CVSS_V3"), vectors.get("CVSS_V4")
    db.execute(
        "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            record["id"],
            "ghsa",
            record.get("published"),
            record.get("modified"),
            None,
            record.get("summary"),
            record.get("details"),
            record.get("database_specific", {}).get("severity"),
            cvss3,
            score(cvss3, CVSS3),
            cvss4,
            score(cvss4, CVSS4),
            sha256,
        ),
    )
    db.executemany("INSERT INTO aliases VALUES (?,?)", [(record["id"], a) for a in aliases])
    for affected in record.get("affected", []):
        package = affected["package"]
        for version_range in affected.get("ranges", []):
            if version_range["type"] == "GIT":
                continue  # commit hashes, not versions a user could ask about
            for span in spans(version_range["events"]):
                db.execute(
                    "INSERT INTO affected VALUES (?,?,?,?,?,?,?)",
                    (record["id"], package["ecosystem"], package["name"], version_range["type"])
                    + span,
                )


def spans(events: list[dict]) -> list[tuple[str | None, str | None, str | None]]:
    """Turn OSV's ordered events into (introduced, fixed, last_affected) spans.

    An introduced with nothing after it is still open: every later version is affected.
    """
    result, introduced = [], None
    for event in events:
        if "introduced" in event:
            if introduced is not None:
                result.append((introduced, None, None))
            introduced = event["introduced"]
        elif "fixed" in event or "last_affected" in event:
            result.append((introduced, event.get("fixed"), event.get("last_affected")))
            introduced = None
    if introduced is not None:
        result.append((introduced, None, None))
    return result


def load_nvd(db: sqlite3.Connection, record: dict, sha256: str) -> None:
    if record.get("notInNvd"):
        return
    description = next(
        (d["value"] for d in record.get("descriptions", []) if d.get("lang") == "en"), None
    )
    cvss3, cvss4 = (
        primary_vector(record, ("cvssMetricV31", "cvssMetricV30")),
        primary_vector(record, ("cvssMetricV40",)),
    )
    db.execute(
        "INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            record["id"],
            "nvd",
            record.get("published"),
            record.get("lastModified"),
            record.get("vulnStatus"),
            None,
            description,
            None,
            cvss3,
            score(cvss3, CVSS3),
            cvss4,
            score(cvss4, CVSS4),
            sha256,
        ),
    )
    for configuration in record.get("configurations", []):
        for node in configuration.get("nodes", []):
            for match in node.get("cpeMatch", []):
                db.execute(
                    "INSERT INTO cpe_matches VALUES (?,?,?,?,?,?,?)",
                    (
                        record["id"],
                        match["criteria"],
                        int(match.get("vulnerable", False)),
                        match.get("versionStartIncluding"),
                        match.get("versionStartExcluding"),
                        match.get("versionEndIncluding"),
                        match.get("versionEndExcluding"),
                    ),
                )


def primary_vector(record: dict, metric_keys: tuple[str, ...]) -> str | None:
    """NVD's own score where it has one. NVD also republishes the CNA's score as
    'Secondary'; that is the reporter's view, not NVD's, so it is not used here.
    A CVE NVD has not analysed yet has no Primary score, and that gap is kept."""
    for key in metric_keys:
        for metric in record.get("metrics", {}).get(key, []):
            if metric.get("type") == "Primary":
                return metric["cvssData"]["vectorString"]
    return None


def load_kev(db: sqlite3.Connection, catalogue: dict) -> None:
    db.executemany(
        "INSERT OR REPLACE INTO kev VALUES (?,?,?,?,?,?,?)",
        [
            (
                v["cveID"],
                v.get("vendorProject"),
                v.get("product"),
                v.get("vulnerabilityName"),
                v.get("dateAdded"),
                v.get("knownRansomwareCampaignUse"),
                catalogue["catalogVersion"],
            )
            for v in catalogue["vulnerabilities"]
        ],
    )


def score(vector: str | None, kind: type[CVSS3] | type[CVSS4]) -> float | None:
    """The base score computed from the vector, so both sources are scored by the same code."""
    if not vector:
        return None
    return float(kind(vector).base_score)
