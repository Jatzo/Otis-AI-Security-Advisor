"""Row S: structured lookups against the small store. No model, no API."""

import json
from pathlib import Path

import pytest
from generation_world import DB, A, B, C, D

from advisor.generation.reading import read_reply
from advisor.structured import Lookups

LOOKUPS = Lookups(DB)
KEV_LINE = (
    f"Which of {A}, {B}, {C}, {D} name a CVE on the CISA Known Exploited Vulnerabilities list?"
)


def ask(question):
    return LOOKUPS.answer(question)


def test_a_first_fixed_version_is_read_from_the_advisory_by_id_or_by_cve():
    assert ask(f"What is the first patched version of django for {A}?")["value"] == "3.0.5"
    assert ask("In which version of django was CVE-2020-0001 fixed?")["value"] == "3.0.5"
    assert ask(f"Which release of axios first contains the fix for {B}?")["value"] == "1.4.0"


def test_severity_and_the_pairing_of_a_ghsa_with_its_cve_are_read_from_the_store():
    assert ask(f"What severity label does GitHub give {A}?")["value"] == "moderate"
    assert ask(f"How does GitHub rate the severity of {C}?")["value"] == "critical"
    assert ask(f"Which CVE ID does {A} cover?")["ids"] == ["CVE-2020-0001"]
    assert ask("Which GitHub advisory covers CVE-2021-0002?")["ids"] == [B]


def test_kev_membership_is_a_yes_or_no_and_an_unknown_cve_is_declined():
    assert (
        ask("Is CVE-2021-0002 on the CISA Known Exploited Vulnerabilities list?")["verdict"]
        == "yes"
    )
    assert (
        ask("Is CVE-2020-0001 on the CISA Known Exploited Vulnerabilities list?")["verdict"] == "no"
    )
    assert ask("Is CVE-2099-0001 on the CISA Known Exploited Vulnerabilities list?")["abstain"]


def test_a_version_verdict_follows_the_ranges_for_pypi_npm_and_maven():
    assert ask(f"Is django 3.0.4 affected by {A}?")["verdict"] == "yes"
    assert ask(f"Does {A} affect django version 3.0.5?")["verdict"] == "no"
    assert ask(f"Would axios 1.3.2 be vulnerable to {B}?")["verdict"] == "yes"
    assert ask(f"Is org.springframework:spring-webmvc 4.0.9 affected by {C}?")["verdict"] == "no"


def test_the_advisories_for_a_version_and_the_filters_on_them():
    assert ask("Which advisories affect django 3.0.4?")["ids"] == [A]
    assert ask("List the security advisories that apply to django 3.0.5.")["ids"] == []
    assert ask("Which django advisories affect version 3.0.4 and are rated moderate by GitHub?")[
        "ids"
    ] == [A]
    assert (
        ask("Of the advisories that apply to django 3.0.4, which does GitHub rate high?")["ids"]
        == []
    )


def test_kev_sets_and_picks():
    assert ask("Which axios advisories involve a CVE that CISA lists as known exploited?")[
        "ids"
    ] == [B]
    assert ask(KEV_LINE)["ids"] == [B]
    assert (
        ask("Which django advisories involve a CVE that CISA lists as known exploited?")["ids"]
        == []
    )


def test_scores_dates_and_the_two_comparisons():
    assert ask(f"What is NVD's v3 base score for the CVE that {A} covers?")["value"] == "9.8"
    assert ask(f"Which has the higher GitHub CVSS v3 score: {A} or {C}?")["ids"] == [C]
    assert ask(f"Which has the higher GitHub CVSS v3 score: {A} or {D}?")["abstain"]  # a tie
    assert ask(f"Which was published first: {A} or {B}?")["ids"] == [B]
    assert ask(f"Between {B} and {A}, which advisory is older?")["ids"] == [B]


def test_the_sources_disagree_forms_flag_bands_silence_and_fixed_versions():
    band = ask(
        f"Do GitHub and NVD put {A} in the same severity band? Give the score each one gives."
    )
    silent = ask(f"Do both GitHub and NVD score {D} with CVSS v3? Give each score.")
    fixed = ask(
        f"Do GitHub and NVD agree on the first fixed version for {A}? "
        "Give the version each one names."
    )

    assert band["disagreement"] == {"flagged": True, "values": {"github": "7.5", "nvd": "9.8"}}
    assert silent["disagreement"] == {"flagged": True, "values": {"github": "7.5", "nvd": None}}
    assert fixed["disagreement"] == {
        "flagged": False,
        "values": {"github": "3.0.5", "nvd": "3.0.5"},
    }


@pytest.mark.parametrize(
    "question",
    [
        "What is the first patched version of numpy for GHSA-9fq2-x9r6-wfmf?",
        "What is the first patched version of django for GHSA-zzzz-zzzz-zzzz?",
        "Which package does CVE-2099-0001 affect?",
        "How do I configure nginx to redirect all HTTP traffic to HTTPS?",
        "Is there a public Metasploit module for CVE-2020-0001?",
        "Which advisory describes the Django cache middleware flaw written in another letter case?",
        "Is numpy 1.2.0 affected by GHSA-aaaa-aaaa-aaaa?",
    ],
)
def test_a_form_it_does_not_read_a_package_outside_the_18_or_an_unheld_id_is_declined(question):
    assert ask(question)["abstain"] is True


def test_every_reply_fits_the_answer_schema_so_the_scorer_can_read_it():
    questions = [
        f"What severity label does GitHub give {A}?",
        f"Which CVE ID does {A} cover?",
        "Is CVE-2021-0002 on the CISA Known Exploited Vulnerabilities list?",
        "Which advisories affect django 3.0.4?",
        f"Do GitHub and NVD put {A} in the same severity band? Give the score each one gives.",
        "nothing it reads",
    ]
    for question in questions:
        parsed, problem = read_reply(json.dumps(ask(question)))
        assert problem is None and parsed is not None


def test_the_row_does_not_use_the_question_builder_or_the_lists_it_made_abstentions_from():
    source = Path("src/advisor/structured/__init__.py").read_text(encoding="utf-8")

    for forbidden in (
        "build_questions",
        "OUT_OF_SCOPE",
        "FAKE_PACKAGES",
        "OFF_TOPIC",
        "gold.jsonl",
        "questions.jsonl",
    ):
        assert forbidden not in source
