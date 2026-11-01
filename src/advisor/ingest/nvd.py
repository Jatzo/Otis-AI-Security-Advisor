"""NVD records for the CVEs the GitHub advisories name, from the NVD API 2.0.

NVD names software by CPE rather than by package, so records are fetched by CVE ID and
joined to packages through the advisories' aliases.

Without an API key NVD allows 5 requests in a rolling 30 seconds; with one, 50. The
fetch is slow on purpose and resumable: a CVE already on disk is never asked for twice.
"""

import os
import time
from collections.abc import Callable
from pathlib import Path

from advisor.ingest import raw
from advisor.ingest.http import GetJson, get_json

CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
SECONDS_BETWEEN_REQUESTS = {False: 6.5, True: 0.7}  # keyed by whether an API key is set


def fetch_cves(
    cve_ids: list[str],
    directory: Path,
    fetch: GetJson = get_json,
    api_key: str | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """Fetch each CVE not already on disk. A CVE NVD does not know is still written,
    as an empty record, so the gap is visible in the snapshot rather than silently absent."""
    api_key = api_key if api_key is not None else os.environ.get("NVD_API_KEY")
    headers = {"apiKey": api_key} if api_key else {}
    pause = SECONDS_BETWEEN_REQUESTS[bool(api_key)]
    fetched = skipped = missing = 0
    for cve_id in cve_ids:
        if (directory / f"{cve_id}.json").exists():
            skipped += 1
            continue
        response = fetch(f"{CVE_URL}?cveId={cve_id}", headers=headers)
        found = response.get("vulnerabilities", [])
        record = found[0]["cve"] if found else {"id": cve_id, "notInNvd": True}
        missing += not found
        raw.write_record(directory, cve_id, record)
        fetched += 1
        sleep(pause)
    raw.log_fetch(directory, "NVD API 2.0", CVE_URL)
    return {"fetched": fetched, "already_on_disk": skipped, "not_in_nvd": missing}
