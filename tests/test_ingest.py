"""Fetchers, run against a stand-in for the network. Records here are synthetic."""

import json

import pytest

from advisor.ingest import nvd, osv, raw
from advisor.packages import PACKAGES, Package


def ghsa(record_id, *aliases):
    return {"id": record_id, "aliases": list(aliases)}


def test_a_package_query_keeps_only_github_advisories_and_follows_every_page():
    pages = [
        {"vulns": [ghsa("GHSA-aaaa"), ghsa("PYSEC-2020-1")], "next_page_token": "p2"},
        {"vulns": [ghsa("GHSA-bbbb"), ghsa("MAL-2026-1")]},
    ]
    bodies = []

    def fake_fetch(url, body):
        bodies.append(body)
        return pages[len(bodies) - 1]

    records = osv.query_package(Package("PyPI", "pyyaml"), fake_fetch)

    assert [r["id"] for r in records] == ["GHSA-aaaa", "GHSA-bbbb"]
    assert bodies[1]["page_token"] == "p2"


def test_a_refetch_removes_advisories_that_upstream_no_longer_lists(tmp_path):
    raw.write_record(tmp_path, "GHSA-2222-2222-2222", ghsa("GHSA-2222-2222-2222"))

    counts = osv.fetch_all(tmp_path, lambda url, body: {"vulns": [ghsa("GHSA-3333-3333-3333")]})

    assert [p.stem for p in raw.record_paths(tmp_path)] == ["GHSA-3333-3333-3333"]
    assert len(counts) == len(PACKAGES)


def test_nvd_is_asked_only_for_cves_the_advisories_name(tmp_path):
    raw.write_record(
        tmp_path, "GHSA-4444-4444-4444", ghsa("GHSA-4444-4444-4444", "CVE-2020-1001", "PYSEC-1")
    )
    raw.write_record(
        tmp_path,
        "GHSA-5555-5555-5555",
        ghsa("GHSA-5555-5555-5555", "CVE-2020-1001", "CVE-2021-2002"),
    )

    assert osv.cve_ids(tmp_path) == ["CVE-2020-1001", "CVE-2021-2002"]


def test_nvd_fetch_resumes_and_records_cves_nvd_does_not_know(tmp_path):
    raw.write_record(tmp_path, "CVE-2020-1001", {"id": "CVE-2020-1001"})
    asked = []

    def fake_fetch(url, headers):
        asked.append(url)
        if url.endswith("CVE-2021-2002"):
            return {"vulnerabilities": [{"cve": {"id": "CVE-2021-2002"}}]}
        return {"vulnerabilities": []}

    result = nvd.fetch_cves(
        ["CVE-2020-1001", "CVE-2021-2002", "CVE-2099-9999"],
        tmp_path,
        fake_fetch,
        api_key="",
        sleep=lambda seconds: None,
    )

    assert len(asked) == 2  # the CVE already on disk is not asked for again
    assert result == {"fetched": 2, "already_on_disk": 1, "not_in_nvd": 1}
    assert raw.read_record(tmp_path / "CVE-2099-9999.json") == {
        "id": "CVE-2099-9999",
        "notInNvd": True,
    }


def test_the_manifest_hashes_each_record_and_skips_the_fetch_log(tmp_path):
    path = raw.write_record(tmp_path / "osv", "GHSA-4444-4444-4444", ghsa("GHSA-4444-4444-4444"))
    raw.log_fetch(tmp_path / "osv", "test source", "https://example.invalid")

    manifest = raw.build_manifest(tmp_path)

    source = manifest["sources"]["osv"]
    assert source["records"] == 1
    assert source["sha256"] == {"GHSA-4444-4444-4444": raw.sha256_of(path)}
    assert source["endpoint"] == "https://example.invalid"


def test_the_same_record_always_writes_the_same_bytes(tmp_path):
    first = raw.write_record(tmp_path / "a", "CVE-2020-1001", {"b": 1, "a": [2, 3]})
    second = raw.write_record(tmp_path / "b", "CVE-2020-1001", json.loads('{"a": [2, 3], "b": 1}'))

    assert raw.sha256_of(first) == raw.sha256_of(second)


@pytest.mark.parametrize(
    "record_id", ["GHSA-../../../src/advisor/store", "CVE-2020-1/../x", "../GHSA-aaaa", "x"]
)
def test_a_record_id_that_could_escape_the_folder_is_refused(tmp_path, record_id):
    with pytest.raises(ValueError, match="unexpected ID"):
        raw.write_record(tmp_path, record_id, {})

    assert list(tmp_path.iterdir()) == []


def test_a_fetch_that_fails_part_way_leaves_the_old_snapshot_whole(tmp_path):
    raw.write_record(tmp_path, "GHSA-2222-3333-4444", ghsa("GHSA-2222-3333-4444"))
    calls = []

    def fails_on_the_third_package(url, body):
        calls.append(body)
        if len(calls) == 3:
            raise TimeoutError("network dropped")
        return {"vulns": [ghsa("GHSA-5555-6666-7777")]}

    with pytest.raises(TimeoutError):
        osv.fetch_all(tmp_path, fails_on_the_third_package)

    assert [p.stem for p in raw.record_paths(tmp_path)] == ["GHSA-2222-3333-4444"]


def test_a_fetch_with_a_bad_id_changes_nothing_on_disk(tmp_path):
    raw.write_record(tmp_path, "GHSA-2222-3333-4444", ghsa("GHSA-2222-3333-4444"))

    with pytest.raises(ValueError, match="unexpected advisory IDs"):
        osv.fetch_all(tmp_path, lambda url, body: {"vulns": [ghsa("GHSA-../../escape")]})

    assert [p.stem for p in raw.record_paths(tmp_path)] == ["GHSA-2222-3333-4444"]
