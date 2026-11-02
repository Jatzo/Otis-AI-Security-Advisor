"""The spot-check sample and sheet. No test here reads a test question."""

import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("spotcheck_for_tests", Path("scripts/spotcheck.py"))
spotcheck = importlib.util.module_from_spec(spec)
sys.modules["spotcheck_for_tests"] = spotcheck
spec.loader.exec_module(spotcheck)

TYPES = ["lookup", "version", "disagree", "multihop", "abstain"]
QUESTIONS = [
    {"id": f"{t[:2]}-{n:03d}", "type": t, "question": f"Q {t} {n}?"}
    for t in TYPES
    for n in range(1, 11)
]


def test_the_draw_is_seeded_stratified_distinct_and_hides_nothing_but_the_row():
    sample = spotcheck.draw(QUESTIONS)

    assert sample == spotcheck.draw(QUESTIONS)
    assert [e["n"] for e in sample] == list(range(1, 25))
    assert len({e["id"] for e in sample}) == 24
    assert sum(e["row"] == "B" for e in sample) == 6
    by_id = {q["id"]: q["type"] for q in QUESTIONS}
    counts = {t: sum(by_id[e["id"]] == t for e in sample if e["row"] == "G") for t in TYPES}
    assert counts == {"lookup": 4, "version": 4, "disagree": 4, "multihop": 3, "abstain": 3}
    assert set(sample[0]) == {"n", "id", "row"}


def test_links_are_built_from_the_ids_alone():
    found = spotcheck.links("See ghsa-ABCD-efgh-1234 and cve-2020-0001, then GHSA-abcd-efgh-1234.")

    assert found == [
        ("GHSA-abcd-efgh-1234", "https://github.com/advisories/GHSA-abcd-efgh-1234"),
        ("CVE-2020-0001", "https://nvd.nist.gov/vuln/detail/CVE-2020-0001"),
    ]


def reply(**fields):
    body = {
        "abstain": False, "verdict": None, "ids": [], "value": None,
        "disagreement": {"flagged": False, "values": {"github": None, "nvd": None}},
        "explanation": "",
    }  # fmt: skip
    return json.dumps({**body, **fields})


def test_the_reader_view_escapes_what_a_model_wrote_and_names_a_declined_reply():
    shown = spotcheck.reader_view(reply(value="<script>alert(1)</script>", explanation="a & b"))
    declined = spotcheck.reader_view(reply(abstain=True, explanation="Not here."))
    unreadable = spotcheck.reader_view("<b>not json</b>")

    assert "<script>" not in shown and "&lt;script&gt;" in shown and "a &amp; b" in shown
    assert "declined" in declined.lower() and "Not here." not in declined
    assert "<b>not json</b>" not in unreadable


def test_the_sheet_shows_no_gold_no_verdict_and_no_row(tmp_path, monkeypatch):
    monkeypatch.setattr(spotcheck, "RESULTS", tmp_path)
    questions = {q["id"]: q for q in QUESTIONS}
    sample = spotcheck.draw(QUESTIONS)
    for name in spotcheck.FILES["dev"].values():
        lines = [{"id": q["id"], "run": 1, "text": reply(value="1.0")} for q in QUESTIONS]
        (tmp_path / name).write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")

    page = spotcheck.build_sheet("dev", sample, questions)

    sections = page[page.index("<section") :]
    assert page.count("<section") == 24
    for hidden in ("gold", "checker", "correct", "baseline", "route", "scorer"):
        assert hidden not in sections.lower()
