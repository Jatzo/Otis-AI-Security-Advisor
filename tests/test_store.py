"""Building the store from a small synthetic snapshot."""

import sqlite3

import pytest

from advisor import store
from advisor.ingest import raw

GHSA_RECORD = {
    "id": "GHSA-2222-3333-4444",
    # Two CVE IDs, as GHSA-j7hp-h8jx-5ppr has; KEV lists only the second.
    "aliases": ["CVE-2020-0001", "CVE-2020-0002", "PYSEC-2020-1"],
    "summary": "Example deserialisation flaw",
    "details": "Loading untrusted input runs code.",
    "published": "2021-04-08T19:24:04Z",
    "database_specific": {"severity": "CRITICAL"},
    "severity": [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}],
    "affected": [
        {
            "package": {"ecosystem": "PyPI", "name": "pyyaml"},
            "ranges": [
                {"type": "ECOSYSTEM", "events": [{"introduced": "5.1"}, {"fixed": "5.2"}]},
                {"type": "GIT", "events": [{"introduced": "abc123"}]},
            ],
        }
    ],
}

NVD_RECORD = {
    "id": "CVE-2020-0001",
    "vulnStatus": "Analyzed",
    "descriptions": [{"lang": "en", "value": "NVD's description."}],
    "metrics": {
        "cvssMetricV31": [
            {
                "type": "Secondary",
                "cvssData": {"vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"},
            },
            {
                "type": "Primary",
                "cvssData": {"vectorString": "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H"},
            },
        ]
    },
    "configurations": [
        {
            "nodes": [
                {
                    "cpeMatch": [
                        {
                            "criteria": "cpe:2.3:a:pyyaml:pyyaml:*:*:*:*:*:*:*:*",
                            "vulnerable": True,
                            "versionEndExcluding": "5.2",
                        }
                    ]
                }
            ]
        }
    ],
}

KEV_CATALOGUE = {
    "catalogVersion": "2026.10.30",
    "vulnerabilities": [
        {"cveID": "CVE-2020-0002", "vendorProject": "Example", "dateAdded": "2022-01-01"}
    ],
}


@pytest.fixture
def db(tmp_path):
    raw.write_record(tmp_path / "raw" / "osv", GHSA_RECORD["id"], GHSA_RECORD)
    raw.write_record(tmp_path / "raw" / "nvd", NVD_RECORD["id"], NVD_RECORD)
    raw.write_record(
        tmp_path / "raw" / "nvd", "CVE-2099-9999", {"id": "CVE-2099-9999", "notInNvd": True}
    )
    raw.write_record(tmp_path / "raw" / "kev", "known_exploited_vulnerabilities", KEV_CATALOGUE)
    counts = store.build(tmp_path / "raw", tmp_path / "advisor.db")
    connection = sqlite3.connect(tmp_path / "advisor.db")
    yield counts, connection
    connection.close()


def test_each_source_keeps_its_own_row_for_the_same_cve(db):
    counts, connection = db
    rows = connection.execute(
        "SELECT source, cvss3_score FROM records JOIN record_cves USING (record_id)"
        " WHERE cve_id = 'CVE-2020-0001' ORDER BY source"
    ).fetchall()

    assert rows == [("ghsa", 9.8), ("nvd", 8.1)]  # the sources disagree, and both are kept
    assert counts["records"] == 2  # a CVE NVD does not know adds no row


def test_nvd_uses_its_own_primary_score_not_the_reporters(db):
    _, connection = db
    vector = connection.execute("SELECT cvss3_vector FROM records WHERE source = 'nvd'").fetchone()[
        0
    ]

    assert "AC:H" in vector


def test_affected_ranges_skip_git_commits(db):
    _, connection = db
    rows = connection.execute(
        "SELECT package, range_type, introduced, fixed FROM affected"
    ).fetchall()

    assert rows == [("pyyaml", "ECOSYSTEM", "5.1", "5.2")]


def test_kev_and_cpe_rows_load(db):
    counts, _ = db
    assert counts["kev"] == 1
    assert counts["cpe_matches"] == 1


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ([{"introduced": "0"}, {"fixed": "1.0"}], [("0", "1.0", None)]),
        ([{"introduced": "2.0"}], [("2.0", None, None)]),
        ([{"introduced": "1.0"}, {"last_affected": "1.4"}], [("1.0", None, "1.4")]),
        (
            [{"introduced": "1.0"}, {"fixed": "1.2"}, {"introduced": "2.0"}, {"fixed": "2.1"}],
            [("1.0", "1.2", None), ("2.0", "2.1", None)],
        ),
    ],
    ids=["closed", "still-open", "last-affected", "two-spans"],
)
def test_osv_events_become_affected_spans(events, expected):
    assert store.spans(events) == expected


def test_an_advisory_joins_to_kev_through_any_of_its_cve_ids(db):
    _, connection = db
    rows = connection.execute(
        "SELECT record_id, kev.cve_id FROM record_cves JOIN kev USING (cve_id)"
    ).fetchall()

    assert rows == [("GHSA-2222-3333-4444", "CVE-2020-0002")]
