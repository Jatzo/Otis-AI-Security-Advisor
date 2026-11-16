"""The claim checker catches a wrong figure, a figure with no claim, and a source that moved."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_claims as cc  # noqa: E402

TEXT = "The checked system was right on 66 of 110 test questions."


def toy(shows, text=TEXT):
    return cc.Claim(text, shows)


def test_a_figure_that_matches_its_computation_passes():
    claim = toy([("66", lambda: 66), ("110", lambda: 110)])
    problems, uncovered = cc.run([claim], TEXT, {})
    assert problems == []
    assert uncovered == []


def test_a_figure_that_differs_from_its_computation_is_reported():
    claim = toy([("66", lambda: 65), ("110", lambda: 110)])
    problems, _ = cc.run([claim], TEXT, {})
    assert len(problems) == 1
    assert "'66'" in problems[0]
    assert "65" in problems[0]


def test_a_number_with_no_claim_is_reported_as_uncovered():
    claim = toy([("66", lambda: 66)])
    _, uncovered = cc.run([claim], TEXT, {})
    assert len(uncovered) == 1
    assert uncovered[0].startswith("110")


def test_claim_text_that_is_not_in_the_readme_is_reported():
    claim = toy([("66", lambda: 66)], text="right on 67 of them")
    problems, _ = cc.run([claim], TEXT, {})
    assert "Text not in README" in problems[0]


def test_a_figure_is_compared_to_the_decimals_the_readme_shows():
    assert cc.same("6.3", 6.25)
    assert cc.same("60%", 60.0)
    assert cc.same("1,164", 1164)
    assert not cc.same("0.0303", 0.0313)


def test_dates_versions_and_adr_numbers_are_not_counted_as_figures():
    readme = "Closed on 5 November 2026 under ADR 0014, with PEP 440 and Maven 3.9.9 ordering."
    _, uncovered = cc.run([], readme, {})
    assert uncovered == []


def test_a_source_that_changed_since_it_was_pinned_is_reported(tmp_path, monkeypatch):
    source = tmp_path / "result.jsonl"
    source.write_text('{"a": 1}\n', encoding="utf-8")
    monkeypatch.setattr(cc, "ROOT", tmp_path)
    claim = cc.Claim(TEXT, [("66", lambda: 66), ("110", lambda: 110)], ["result.jsonl"])
    pinned = {"result.jsonl": cc.sha256(source)}
    assert cc.run([claim], TEXT, pinned)[0] == []
    source.write_text('{"a": 2}\n', encoding="utf-8")
    problems, _ = cc.run([claim], TEXT, pinned)
    assert "changed or not pinned" in problems[0]


def test_windows_and_unix_line_endings_give_the_same_pin(tmp_path):
    unix = tmp_path / "unix.txt"
    windows = tmp_path / "windows.txt"
    unix.write_bytes(b"one\ntwo\n")
    windows.write_bytes(b"one\r\ntwo\r\n")
    assert cc.sha256(unix) == cc.sha256(windows)


def test_the_real_readme_has_a_claim_for_every_figure():
    sys.path.insert(0, str(ROOT / "scripts"))
    from claims_data import CLAIMS  # noqa: PLC0415

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    problems, uncovered = cc.run(CLAIMS, readme, cc.load_pins())
    assert problems == []
    assert uncovered == []


def test_a_wrong_retrieval_depth_is_not_waved_through_as_a_label():
    _, uncovered = cc.run([], "The top 10 go to the model, and the top 12 do not.", {})
    assert len(uncovered) == 1
    assert uncovered[0].startswith("12")
