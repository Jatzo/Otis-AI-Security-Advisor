"""A small committed sample of the snapshot, so the repo can be tested without the full data.

Advisories are picked by rule, not by hand: each rule names a case the system has to handle
(a KEV hit, two CVEs on one advisory, a CVE NVD does not hold, a score that differs between
sources) and takes the lowest advisory ID that meets it. A rule nothing meets is an error,
so the sample cannot quietly stop covering a case.

Advisory and NVD files are copied byte for byte, so their hashes match the manifest.
The KEV file is cut down to the sampled CVEs, which is a change and is recorded as one in
data/ATTRIBUTION.md.
"""

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from advisor.ingest import raw
from advisor.ingest.kev import CATALOGUE_ID

# name -> (query returning one advisory ID or NULL, parameters)
RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "a PyPI advisory": (
        "SELECT MIN(record_id) FROM corpus_affected WHERE ecosystem = ?",
        ("PyPI",),
    ),
    "an npm advisory": ("SELECT MIN(record_id) FROM corpus_affected WHERE ecosystem = ?", ("npm",)),
    "a Maven advisory": (
        "SELECT MIN(record_id) FROM corpus_affected WHERE ecosystem = ?",
        ("Maven",),
    ),
    "an advisory for a CVE on KEV": (
        "SELECT MIN(ghsa_id) FROM source_pairs JOIN kev USING (cve_id)",
        (),
    ),
    "an advisory naming two CVEs": (
        "SELECT MIN(record_id) FROM (SELECT record_id FROM aliases"
        " WHERE alias LIKE 'CVE-%' GROUP BY record_id HAVING COUNT(*) = 2)",
        (),
    ),
    "an advisory naming no CVE": (
        "SELECT MIN(record_id) FROM records WHERE source = 'ghsa' AND record_id NOT IN"
        " (SELECT record_id FROM aliases WHERE alias LIKE 'CVE-%')",
        (),
    ),
    "an advisory whose CVE NVD does not hold": (
        "SELECT MIN(record_id) FROM aliases WHERE alias LIKE 'CVE-%' AND alias NOT IN"
        " (SELECT record_id FROM records WHERE source = 'nvd')",
        (),
    ),
    "a CVE NVD gave only a v2 score": (
        "SELECT MIN(ghsa_id) FROM source_pairs WHERE nvd_no_v3_reason = ?",
        ("only a v2 score",),
    ),
    "a CVE with only the reporter's score on NVD": (
        "SELECT MIN(ghsa_id) FROM source_pairs WHERE nvd_no_v3_reason = ?",
        ("only the reporter's score (Secondary)",),
    ),
    "a CVE NVD has rejected": (
        "SELECT MIN(ghsa_id) FROM source_pairs WHERE nvd_status = ?",
        ("Rejected",),
    ),
    "a pair whose v3 scores differ by 2 points or more": (
        "SELECT MIN(ghsa_id) FROM source_pairs WHERE ABS(github_v3_score - nvd_v3_score) >= 2",
        (),
    ),
    "a GitHub v3.0 vector against an NVD v3.1 vector": (
        "SELECT MIN(ghsa_id) FROM source_pairs"
        " WHERE github_v3_vector LIKE ? AND nvd_v3_vector LIKE ?",
        ("CVSS:3.0/%", "CVSS:3.1/%"),
    ),
    "an advisory scored with CVSS v4": (
        "SELECT MIN(record_id) FROM records WHERE source = 'ghsa' AND cvss4_vector IS NOT NULL",
        (),
    ),
    "a Spring fix versioned with a RELEASE suffix": (
        "SELECT MIN(record_id) FROM corpus_affected WHERE fixed LIKE ?",
        ("%.RELEASE",),
    ),
    "an advisory that also lists a package outside the corpus": (
        "SELECT MIN(a.record_id) FROM affected a WHERE NOT EXISTS"
        " (SELECT 1 FROM corpus_packages c"
        " WHERE c.ecosystem = a.ecosystem AND c.package = a.package)",
        (),
    ),
    "a range that ends at a last affected version": (
        "SELECT MIN(record_id) FROM corpus_affected WHERE last_affected IS NOT NULL",
        (),
    ),
}


def choose(db: sqlite3.Connection) -> dict[str, str]:
    chosen = {}
    for name, (query, params) in RULES.items():
        record_id = db.execute(query, params).fetchone()[0]
        if record_id is None:
            raise LookupError(f"No advisory in the snapshot is {name}; the sample would miss it.")
        chosen[name] = record_id
    return chosen


def checked(record_id: str) -> str:
    """IDs come from upstream records and become file names, so they are checked first."""
    if not raw.RECORD_ID.fullmatch(record_id):
        raise ValueError(f"Refusing to use a record with an unexpected ID: {record_id!r}")
    return record_id


def write_sample(raw_root: Path, db_path: Path, sample_root: Path, snapshot_id: str) -> dict:
    """Replace sample_root with the advisories the rules pick, their NVD records and the
    KEV entries for their CVEs. The new sample is built beside the old one and swapped in
    only when it is whole, so a failure part-way leaves the old sample as it was."""
    with closing(sqlite3.connect(db_path)) as db:
        chosen = choose(db)
    advisory_ids = sorted({checked(record_id) for record_id in chosen.values()})
    staging = sample_root.with_name(sample_root.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        for folder in ("osv", "nvd", "kev"):
            (staging / folder).mkdir(parents=True)
        cve_ids: set[str] = set()
        for advisory_id in advisory_ids:
            source = raw_root / "osv" / f"{advisory_id}.json"
            shutil.copyfile(source, staging / "osv" / source.name)
            aliases = raw.read_record(source).get("aliases", [])
            cve_ids.update(checked(a) for a in aliases if a.startswith("CVE-"))
        for cve_id in sorted(cve_ids):
            source = raw_root / "nvd" / f"{cve_id}.json"
            shutil.copyfile(source, staging / "nvd" / source.name)
        catalogue = raw.read_record(raw_root / "kev" / f"{CATALOGUE_ID}.json")
        catalogue["vulnerabilities"] = [
            v for v in catalogue["vulnerabilities"] if v["cveID"] in cve_ids
        ]
        catalogue["count"] = len(catalogue["vulnerabilities"])
        raw.write_record(staging / "kev", CATALOGUE_ID, catalogue)
        summary = {"snapshot_id": snapshot_id, "chosen_by": chosen}
        text = json.dumps(summary, indent=1, sort_keys=True) + raw.LF
        (staging / "chosen.json").write_text(text, encoding="utf-8", newline=raw.LF)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if sample_root.exists():
        shutil.rmtree(sample_root)
    staging.rename(sample_root)
    return {"advisories": len(advisory_ids), "nvd_records": len(cve_ids), "rules": len(chosen)}
