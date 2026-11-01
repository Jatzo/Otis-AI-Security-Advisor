"""CISA's Known Exploited Vulnerabilities catalogue, kept whole.

The catalogue is small (under 2 MB), so it is stored as one file. The store loads every
entry, so "is this CVE exploited?" can be answered for CVEs outside the corpus too.
"""

from pathlib import Path

from advisor.ingest import raw
from advisor.ingest.http import GetJson, get_json

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
CATALOGUE_ID = "known_exploited_vulnerabilities"


def fetch(directory: Path, fetch_json: GetJson = get_json) -> dict[str, str | int]:
    catalogue = fetch_json(KEV_URL)
    raw.write_record(directory, CATALOGUE_ID, catalogue)
    raw.log_fetch(directory, "CISA KEV", KEV_URL)
    return {"version": catalogue["catalogVersion"], "entries": len(catalogue["vulnerabilities"])}
