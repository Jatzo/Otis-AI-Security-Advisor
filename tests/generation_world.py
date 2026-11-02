"""A small in-memory store for the generation tests, built with the real loaders.

Four advisories (PyPI, npm, Maven, and a PyPI one whose NVD record has nothing to read a fix from),
two NVD records, one KEV entry. GHSA-aaaa-aaaa-aaaa's body names an ID that exists nowhere, so a
test can show that text inside a record grounds nothing.
"""

import json
import sqlite3
from types import SimpleNamespace

from advisor import store
from advisor.generation.facts import Facts
from advisor.packages import PACKAGES
from advisor.retrieval.units import build_units

V3_HIGH = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N"  # 7.5
V3_CRITICAL = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 9.8


def ghsa(record_id, cve, ecosystem, package, range_type, introduced, fixed, severity, **more):
    return {
        "id": record_id,
        "aliases": [cve] if cve else [],
        "summary": f"A flaw in {package}",
        "details": more.pop("details", f"Details of {record_id}."),
        "published": more.pop("published", "2026-10-21T20:39:49Z"),
        "database_specific": {"severity": severity},
        "severity": [{"type": "CVSS_V3", "score": more["vector"]}] if more.get("vector") else [],
        "affected": [
            {
                "package": {"ecosystem": ecosystem, "name": package},
                "ranges": [
                    {"type": range_type, "events": [{"introduced": introduced}, {"fixed": fixed}]}
                ],
            }
        ],
    }


def nvd(record_id, vector=None, matches=()):
    metrics = (
        {"cvssMetricV31": [{"type": "Primary", "cvssData": {"vectorString": vector}}]}
        if vector
        else {}
    )
    return {
        "id": record_id,
        "published": "2020-03-04T10:00:00.000",
        "vulnStatus": "Analyzed",
        "descriptions": [{"lang": "en", "value": f"NVD describes {record_id}."}],
        "metrics": metrics,
        "configurations": [{"nodes": [{"cpeMatch": list(matches)}]}] if matches else [],
    }


def cpe(product, **bounds):
    return {"criteria": f"cpe:2.3:a:x:{product}:*:*:*:*:*:*:*:*", "vulnerable": True, **bounds}


A, B, C, D = (f"GHSA-{x * 4}-{x * 4}-{x * 4}" for x in "abcd")
GHOST = "GHSA-zzzz-zzzz-zzzz"
SPRING = "org.springframework:spring-webmvc"

RECORDS = [
    ghsa(
        A,
        "CVE-2020-0001",
        "PyPI",
        "django",
        "ECOSYSTEM",
        "3.0",
        "3.0.5",
        "MODERATE",
        vector=V3_HIGH,
        details=f"This one is next to {GHOST}, which nobody holds.",
    ),  # fmt: skip
    ghsa(
        B,
        "CVE-2021-0002",
        "npm",
        "axios",
        "SEMVER",
        "0",
        "1.4.0",
        "HIGH",
        published="2026-09-01T00:00:00Z",
    ),  # fmt: skip
    ghsa(C, "CVE-2022-0003", "Maven", SPRING, "ECOSYSTEM", "4.0.0", "4.0.9", "CRITICAL"),
    ghsa(D, "CVE-2023-0004", "PyPI", "pillow", "ECOSYSTEM", "1.0", "9.0", "LOW", vector=V3_HIGH),
]
NVD_RECORDS = [
    nvd("CVE-2020-0001", V3_CRITICAL, [cpe("django", versionEndExcluding="3.0.5")]),
    nvd("CVE-2022-0003"),  # nothing to read a fix from
    nvd("CVE-2023-0004", None, [cpe("pillow", versionEndIncluding="8.9")]),
]
KEV = {
    "catalogVersion": "test",
    "vulnerabilities": [
        {"cveID": "CVE-2021-0002", "vendorProject": "axios", "product": "axios"},
    ],
}


def build():
    db = sqlite3.connect(":memory:")
    db.executescript(store.SCHEMA)
    db.executemany("INSERT INTO corpus_packages VALUES (?,?)", PACKAGES)
    for record in RECORDS:
        store.load_ghsa(db, record, "0" * 64)
    for record in NVD_RECORDS:
        store.load_nvd(db, record, "0" * 64)
    store.load_kev(db, KEV)
    return db


DB = build()
FACTS = Facts(DB)
UNITS = {unit.unit_id: unit for unit in build_units(DB)}


def shown(*unit_ids):
    return [UNITS[unit_id] for unit_id in unit_ids]


NO_DISAGREEMENT = {"flagged": False, "values": {"github": None, "nvd": None}}


def reply(**fields):
    """A reply as the model would write it, with every field the schema needs."""
    body = {
        "abstain": False, "verdict": None, "ids": [], "value": None,
        "disagreement": NO_DISAGREEMENT, "explanation": "", "claims": [],
    }  # fmt: skip
    return json.dumps({**body, **fields})


class StubClient:
    """Stands in for the API. Counts what it was asked and never touches the network."""

    def __init__(self, text="{}", stop="end_turn"):
        self.text, self.stop, self.requests = text, stop, []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.requests.append(request)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self.text)],
            stop_reason=self.stop,
            stop_details=None,
            model="claude-sonnet-5-5",
            usage=SimpleNamespace(
                input_tokens=1000,
                output_tokens=500,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=None,
            ),  # fmt: skip
            _request_id="req_stub",
        )
