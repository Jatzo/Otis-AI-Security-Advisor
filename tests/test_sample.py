"""The committed sample: faithful to the snapshot, small, and still covering every case."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from advisor import store
from advisor.ingest import raw, sample

SAMPLE = Path("data/sample")
MANIFEST = Path("data/manifest.json")


@pytest.fixture(scope="module")
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_advisory_and_nvd_files_are_byte_for_byte_copies_of_the_snapshot(manifest):
    for source in ("osv", "nvd"):
        paths = raw.record_paths(SAMPLE / source)
        assert paths, f"The sample has no {source} records"
        for path in paths:
            assert raw.sha256_of(path) == manifest["sources"][source]["sha256"][path.stem]


def test_the_sample_says_which_snapshot_it_was_drawn_from(manifest):
    chosen = json.loads((SAMPLE / "chosen.json").read_text(encoding="utf-8"))

    assert chosen["snapshot_id"] == manifest["snapshot_id"]


def test_the_sample_stays_small():
    assert len(raw.record_paths(SAMPLE / "osv")) <= 25
    assert sum(p.stat().st_size for p in SAMPLE.rglob("*.json")) < 1_000_000


def test_every_nvd_record_the_advisories_name_is_in_the_sample():
    named = set()
    for path in raw.record_paths(SAMPLE / "osv"):
        named.update(a for a in raw.read_record(path).get("aliases", []) if a.startswith("CVE-"))

    assert {p.stem for p in raw.record_paths(SAMPLE / "nvd")} == named


def test_the_kev_file_holds_only_entries_for_the_sampled_cves():
    catalogue = raw.read_record(SAMPLE / "kev" / "known_exploited_vulnerabilities.json")
    sampled = {p.stem for p in raw.record_paths(SAMPLE / "nvd")}

    assert {v["cveID"] for v in catalogue["vulnerabilities"]} <= sampled
    assert catalogue["count"] == len(catalogue["vulnerabilities"]) > 0


def test_the_sample_still_meets_every_rule_it_was_picked_by(tmp_path):
    store.build(SAMPLE, tmp_path / "sample.db")

    with closing(sqlite3.connect(tmp_path / "sample.db")) as db:
        chosen = sample.choose(db)

    in_sample = {p.stem for p in raw.record_paths(SAMPLE / "osv")}
    assert set(chosen.values()) <= in_sample


def test_a_rule_that_nothing_meets_is_an_error_not_a_gap():
    db = sqlite3.connect(":memory:")
    db.executescript(store.SCHEMA)

    with pytest.raises(LookupError, match="would miss it"):
        sample.choose(db)


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    """A one-advisory snapshot on disk, built into a store, with one rule for picking."""
    advisory = {
        "id": "GHSA-2222-3333-4444",
        "aliases": ["CVE-2020-0001"],
        "affected": [
            {
                "package": {"ecosystem": "PyPI", "name": "pyyaml"},
                "ranges": [
                    {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.0"}]}
                ],
            }
        ],
    }
    raw.write_record(tmp_path / "raw" / "osv", advisory["id"], advisory)
    raw.write_record(tmp_path / "raw" / "nvd", "CVE-2020-0001", {"id": "CVE-2020-0001"})
    kev = {
        "catalogVersion": "test",
        "count": 2,
        "vulnerabilities": [{"cveID": "CVE-2020-0001"}, {"cveID": "CVE-2019-9999"}],
    }
    raw.write_record(tmp_path / "raw" / "kev", "known_exploited_vulnerabilities", kev)
    store.build(tmp_path / "raw", tmp_path / "advisor.db")
    monkeypatch.setattr(
        sample,
        "RULES",
        {
            "a PyPI advisory": (
                "SELECT MIN(record_id) FROM corpus_affected WHERE ecosystem = ?",
                ("PyPI",),
            )
        },
    )
    return tmp_path


def test_write_sample_copies_records_unchanged_and_cuts_kev_to_the_sampled_cves(snapshot):
    result = sample.write_sample(
        snapshot / "raw", snapshot / "advisor.db", snapshot / "out", "abc123"
    )

    copied = snapshot / "out" / "osv" / "GHSA-2222-3333-4444.json"
    assert copied.read_bytes() == (snapshot / "raw" / "osv" / copied.name).read_bytes()
    catalogue = raw.read_record(snapshot / "out" / "kev" / "known_exploited_vulnerabilities.json")
    assert [v["cveID"] for v in catalogue["vulnerabilities"]] == ["CVE-2020-0001"]
    assert catalogue["count"] == 1
    assert result == {"advisories": 1, "nvd_records": 1, "rules": 1}


def test_a_failed_write_leaves_the_old_sample_whole(snapshot):
    (snapshot / "out").mkdir()
    (snapshot / "out" / "old.txt").write_text("the previous sample")
    (snapshot / "raw" / "nvd" / "CVE-2020-0001.json").unlink()

    with pytest.raises(FileNotFoundError):
        sample.write_sample(snapshot / "raw", snapshot / "advisor.db", snapshot / "out", "abc123")

    assert (snapshot / "out" / "old.txt").read_text() == "the previous sample"
    assert not (snapshot / "out.new").exists()


def test_an_alias_that_could_escape_the_folder_is_refused(snapshot):
    advisory = raw.read_record(snapshot / "raw" / "osv" / "GHSA-2222-3333-4444.json")
    advisory["aliases"] = ["CVE-2020-1/../../manifest"]
    raw.write_record(snapshot / "raw" / "osv", advisory["id"], advisory)

    with pytest.raises(ValueError, match="unexpected ID"):
        sample.write_sample(snapshot / "raw", snapshot / "advisor.db", snapshot / "out", "abc123")

    assert not (snapshot / "out").exists()
