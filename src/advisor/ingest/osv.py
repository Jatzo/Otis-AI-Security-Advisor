"""GitHub-reviewed advisories, fetched in OSV format from OSV.dev.

OSV.dev also returns PyPA (PYSEC-), OSS-Fuzz and malware (MAL-) records for the same
packages. Only GHSA- records are kept, so each advisory is counted once and every
record in the corpus carries the GitHub Advisory Database's CC BY 4.0 licence.
OSV.dev leaves withdrawn advisories out of query results, so they are not in the corpus.
"""

from pathlib import Path

from advisor.ingest import raw
from advisor.ingest.http import GetJson, get_json
from advisor.packages import PACKAGES, Package

QUERY_URL = "https://api.osv.dev/v1/query"


def query_package(package: Package, fetch: GetJson = get_json) -> list[dict]:
    """Every GitHub-reviewed advisory OSV.dev lists for one package, all pages."""
    records, page_token = [], None
    while True:
        body: dict = {"package": {"name": package.name, "ecosystem": package.ecosystem}}
        if page_token:
            body["page_token"] = page_token
        response = fetch(QUERY_URL, body=body)
        records += [v for v in response.get("vulns", []) if v["id"].startswith("GHSA-")]
        page_token = response.get("next_page_token")
        if not page_token:
            return records


def fetch_all(directory: Path, fetch: GetJson = get_json) -> dict[str, int]:
    """Write one file per advisory and return the count per package.

    An advisory listing two corpus packages is written once; its file holds both.
    """
    # Every package is fetched and every ID checked before anything on disk changes, so
    # a failure part-way leaves the previous snapshot whole rather than half-replaced.
    fetched = {package.name: query_package(package, fetch) for package in PACKAGES}
    bad_ids = [
        r["id"] for rs in fetched.values() for r in rs if not raw.RECORD_ID.fullmatch(r["id"])
    ]
    if bad_ids:
        raise ValueError(f"OSV.dev returned unexpected advisory IDs: {bad_ids[:5]}")
    # A full refetch replaces the folder, so an advisory withdrawn upstream since the
    # last fetch does not linger in the snapshot.
    for old in raw.record_paths(directory) if directory.exists() else []:
        old.unlink()
    for records in fetched.values():
        for record in records:
            raw.write_record(directory, record["id"], record)
    raw.log_fetch(directory, "GitHub Advisory Database via OSV.dev", QUERY_URL)
    return {name: len(records) for name, records in fetched.items()}


def cve_ids(directory: Path) -> list[str]:
    """The CVE IDs the fetched advisories name, which is what NVD is asked for."""
    ids = set()
    for path in raw.record_paths(directory):
        ids.update(a for a in raw.read_record(path).get("aliases", []) if a.startswith("CVE-"))
    return sorted(ids)
