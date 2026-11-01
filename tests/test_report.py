"""The data report, run against a store small enough to count by hand. Records are synthetic."""

import sqlite3

import pytest

from advisor import report, store
from advisor.packages import PACKAGES

V30 = "CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 9.8
V31 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 9.8, same metrics as V30
V31_HARDER = "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H"  # 8.1
V4 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


def advisory(record_id, aliases, ecosystem, name, fixed, label, vector=None, kind="CVSS_V3"):
    return {
        "id": record_id,
        "aliases": aliases,
        "database_specific": {"severity": label},
        "severity": [{"type": kind, "score": vector}] if vector else [],
        "affected": [
            {
                "package": {"ecosystem": ecosystem, "name": name},
                "ranges": [
                    {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": fixed}]}
                ],
            }
        ],
    }


def cve(cve_id, status, metrics=None, end_excluding=None):
    cpe = {"criteria": "cpe:2.3:a:x:y:*:*:*:*:*:*:*:*", "vulnerable": True}
    if end_excluding:
        cpe["versionEndExcluding"] = end_excluding
    return {
        "id": cve_id,
        "vulnStatus": status,
        "metrics": metrics or {},
        "configurations": [{"nodes": [{"cpeMatch": [cpe]}]}],
    }


def metric(vector, kind="Primary", key="cvssMetricV31"):
    return {key: [{"type": kind, "cvssData": {"vectorString": vector}}]}


@pytest.fixture
def db():
    connection = sqlite3.connect(":memory:")
    connection.executescript(store.SCHEMA)
    connection.executemany("INSERT INTO corpus_packages VALUES (?,?)", PACKAGES)
    outside_corpus = {
        "package": {"ecosystem": "RubyGems", "name": "foo"},
        "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.0"}]}],
    }
    two_cves = advisory(
        "GHSA-1", ["CVE-2020-0001", "CVE-2020-0002"], "PyPI", "pyyaml", "5.2", "HIGH", V30
    )
    lodash = advisory("GHSA-2", ["CVE-2021-0003"], "npm", "lodash", "4.17.21", "CRITICAL", V31)
    lodash["affected"].append(outside_corpus)
    advisories = [
        two_cves,
        lodash,
        advisory(
            "GHSA-3",
            ["CVE-2021-0004"],
            "Maven",
            "org.apache.logging.log4j:log4j-core",
            "2.17.1",
            "MODERATE",
            V4,
            "CVSS_V4",
        ),
        advisory("GHSA-4", [], "PyPI", "flask", "2.0", "LOW"),
        advisory("GHSA-5", ["CVE-2022-0005"], "PyPI", "requests", "2.31", "HIGH", V31),
    ]
    nvd_records = [
        cve("CVE-2020-0001", "Analyzed", metric(V31), "5.2"),
        cve("CVE-2020-0002", "Awaiting Analysis"),
        cve("CVE-2021-0003", "Analyzed", metric(V31_HARDER), "4.17.20"),
        cve("CVE-2021-0004", "Modified", metric(V31)),
        cve("CVE-2022-0005", "Modified", metric(V31, kind="Secondary")),
    ]
    for record in advisories:
        store.load_ghsa(connection, record, "hash")
    for record in nvd_records:
        store.load_nvd(connection, record, "hash")
    store.load_kev(
        connection,
        {
            "catalogVersion": "test",
            "vulnerabilities": [{"cveID": "CVE-2020-0002"}, {"cveID": "CVE-2021-0003"}],
        },
    )
    yield connection
    connection.close()


def test_package_counts_ignore_ranges_for_packages_outside_the_corpus(db):
    per_package = {name: total for _, name, total in report.counts_per_package(db)}

    assert per_package["lodash"] == 1
    assert per_package["django"] == 0  # a corpus package with no advisories still has a row
    counts = report.source_counts(db)
    assert counts["Version ranges for packages outside the corpus (ignored)"] == 1
    assert counts["Corpus ranges with no fix and no last affected version"] == 0


def test_an_advisory_naming_two_cves_makes_two_pairs(db):
    comparison = report.cvss_comparison(db)

    assert comparison["pairs"] == 5
    assert sum(comparison["shape"].values()) == comparison["pairs"]  # each pair counted once
    assert comparison["shape"] == {
        "both have a v3 score": 2,
        "GitHub has v3, NVD has no v3 score": 2,
        "NVD has v3, GitHub has no v3 score": 1,
    }


def test_a_v30_vector_and_a_v31_vector_with_the_same_metrics_agree_on_score(db):
    comparison = report.cvss_comparison(db)

    assert comparison["versions"]["CVSS:3.0 vs CVSS:3.1"] == 1
    assert comparison["same_vector"] == 0  # the strings differ by their prefix only
    assert comparison["same_metrics"] == 1
    assert comparison["same_score"] == 1


def test_a_score_gap_that_crosses_a_severity_band_is_counted(db):
    comparison = report.cvss_comparison(db)

    assert comparison["band_changes"] == 1  # 9.8 critical against 8.1 high
    assert comparison["mean_gap"] == pytest.approx(1.7)


def test_v4_scores_are_counted_and_not_dropped(db):
    assert report.cvss_comparison(db)["v4"]["GitHub has a v4 score"] == 1


def test_github_moderate_and_cvss_medium_are_the_same_band(db):
    assert report.github_labels_vs_nvd_band(db)[("medium", "critical")] == 1


def test_a_missing_nvd_score_says_why(db):
    assert dict(report.why_no_v3(db)) == {
        "no score at all": 1,
        "only the reporter's score (Secondary)": 1,
    }


@pytest.mark.parametrize(
    ("metrics", "expected"),
    [
        ({"cvssMetricV2": [{"type": "Primary"}]}, "only a v2 score"),
        ({"cvssMetricV40": [{"type": "Primary"}]}, "only a v4 score"),
        (
            {"cvssMetricV40": [{"type": "Secondary"}], "ssvcV203": [{}]},
            "only the reporter's score (Secondary)",
        ),
        ({}, "no score at all"),
    ],
)
def test_no_v3_reason_names_what_nvd_does_have(metrics, expected):
    assert store.no_v3_reason({"metrics": metrics}) == expected


def test_kev_counts_an_advisory_once_through_whichever_cve_is_listed(db):
    total, by_package = report.kev_hits(db)

    assert total == 2
    assert {name: n for _, name, n in by_package} == {"pyyaml": 1, "lodash": 1}


def test_fixed_versions_are_compared_as_sets_of_text(db):
    assert report.fixed_version_strings(db) == {
        "same set of fixed versions": 1,
        "NVD names no end-excluding version": 3,
        "no version in common": 1,
    }


def test_table_cells_cannot_break_out_of_the_row():
    text = report.table(["Status"], [["a | b\nc"]])

    assert text.splitlines()[-1] == "| a \\| b c |"


def test_a_github_advisory_with_no_label_is_counted_not_a_crash(db):
    db.execute("UPDATE records SET severity = NULL WHERE record_id = 'GHSA-1'")

    assert report.github_labels_vs_nvd_band(db)[("none", "critical")] == 1


def test_markup_in_upstream_text_is_shown_as_text():
    text = report.table(["Status"], [["<img src=x onerror=alert(1)>"]])

    assert "<" not in text.splitlines()[-1]
