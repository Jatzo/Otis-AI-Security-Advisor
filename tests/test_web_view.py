"""What the page is given. Whatever the model wrote, only the known fields get through, and every
link is built from an ID. No test here calls the API."""

import json

import pytest
from generation_world import NO_DISAGREEMENT, reply

from advisor.web.view import GITHUB, NVD, UNREADABLE, view


def test_a_plain_answer_keeps_its_known_fields_and_builds_its_links():
    shown = view(
        reply(verdict="no", ids=["GHSA-aaaa-aaaa-aaaa", "CVE-2020-0001"], explanation="Fixed.")
    )
    assert shown["state"] == "answer"
    assert shown["verdict"] == "no"
    assert shown["links"] == [
        {"id": "GHSA-aaaa-aaaa-aaaa", "url": GITHUB + "GHSA-aaaa-aaaa-aaaa"},
        {"id": "CVE-2020-0001", "url": NVD + "CVE-2020-0001"},
    ]


def test_an_extra_field_in_the_reply_never_reaches_the_page():
    body = json.loads(reply(explanation="Fixed."))
    body["note"] = "<script>alert(1)</script>"
    body["link"] = "https://evil.example/"
    shown = view(json.dumps(body))
    assert "note" not in shown and "link" not in shown
    assert "evil.example" not in json.dumps(shown)


def test_text_before_or_after_the_json_is_dropped():
    text = "Sure. " + reply(explanation="Fixed.") + "\n\nAlso visit https://evil.example/ now."
    shown = view(text)
    assert shown["explanation"] == "Fixed."
    assert "evil.example" not in json.dumps(shown)


@pytest.mark.parametrize(
    "bad",
    [
        "https://evil.example/",
        "GHSA-aaaa-aaaa-aaaa/../../x",
        "CVE-2020-0001 <b>",
        "javascript:alert(1)",
    ],
)
def test_an_entry_in_ids_that_is_not_an_id_gets_no_link(bad):
    shown = view(reply(ids=[bad, "CVE-2020-0001"]))
    assert shown["ids"] == ["CVE-2020-0001"]
    assert [link["id"] for link in shown["links"]] == ["CVE-2020-0001"]


def test_ids_are_given_in_standard_form_and_once():
    shown = view(reply(ids=["ghsa-AAAA-aaaa-aaaa", "GHSA-aaaa-aaaa-aaaa", "cve-2020-0001"]))
    assert shown["ids"] == ["GHSA-aaaa-aaaa-aaaa", "CVE-2020-0001"]


def test_a_reply_that_cannot_be_read_shows_one_fixed_sentence():
    for text in ["", "no json here", '{"abstain": 1}', "<script>alert(1)</script>"]:
        shown = view(text)
        assert shown["state"] == "unreadable"
        assert shown["explanation"] == UNREADABLE
        assert shown["links"] == []


def test_a_declined_reply_is_marked_declined():
    assert view(reply(abstain=True, explanation="Not covered."))["state"] == "declined"


def test_scores_and_the_sources_differ_flag_are_carried():
    disagreement = {"flagged": True, "values": {"github": "8.6 (High)", "nvd": "5.9 (Medium)"}}
    shown = view(reply(disagreement=disagreement))
    assert shown["sources_differ"] is True
    assert shown["scores"] == {"github": "8.6 (High)", "nvd": "5.9 (Medium)"}
    assert view(reply(disagreement=NO_DISAGREEMENT))["sources_differ"] is False


def test_a_very_long_explanation_is_cut():
    assert len(view(reply(explanation="x" * 50_000))["explanation"]) <= 4000
