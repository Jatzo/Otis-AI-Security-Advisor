"""The checker, rule by rule, against a small store. No test here calls the API."""

import json

import pytest
from generation_world import (
    FACTS,
    GHOST,
    SPRING,
    A,
    B,
    C,
    D,
    StubClient,
    reply,
    shown,
)

from advisor.generation.answer import respond, system_prompt
from advisor.generation.checker import (
    REFUSAL_TEXT,
    asks_if_affected,
    check,
    question_pairs,
)
from advisor.generation.reading import ANY_ID, normal_id

GA, GB, GC, GD = (f"ghsa:{x}" for x in (A, B, C, D))
NVD_A = "nvd:CVE-2020-0001"
NVD_C = "nvd:CVE-2022-0003"


def run(question, text, *unit_ids, stop="end_turn"):
    return check(question, text, stop, shown(*unit_ids), FACTS)


def affects(record, package, version, affected=True):
    return {
        "kind": "affects", "record": record, "package": package, "version": version,
        "affected": affected,
    }  # fmt: skip


def refused_by(checked, rule):
    assert checked.verdict == "refused" and checked.route == "checker", checked.reasons
    assert checked.rule == rule, (checked.rule, checked.reasons)
    answer = json.loads(checked.text)
    assert answer["abstain"] is True and answer["explanation"] == REFUSAL_TEXT
    assert answer["ids"] == [] and answer["value"] is None and answer["claims"] == []


# --- 1. an ID the evidence never held is cut out, with its claims -----------------------------


def test_a_fabricated_cve_is_cut_from_ids_explanation_and_claims_and_the_reply_is_repaired():
    text = reply(
        verdict=None,
        ids=[A, "CVE-2099-0001"],
        explanation=f"{A} affects it. CVE-2099-0001 affects it too.",
        claims=[
            affects(A, "django", "3.0.4"),
            {"kind": "kev", "cve": "CVE-2099-0001", "listed": True},
        ],
    )

    checked = run("Which advisories affect django 3.0.4?", text, GA)

    assert checked.verdict == "repaired" and checked.route == "answer"
    assert checked.removed_ids == ["CVE-2099-0001"]
    answer = json.loads(checked.text)
    assert answer["ids"] == [A]
    assert answer["explanation"] == f"{A} affects it."
    assert [c["kind"] for c in answer["claims"]] == ["affects"]
    assert "CVE-2099-0001" not in checked.text


def test_an_id_that_only_appears_in_a_record_body_grounds_nothing():
    assert GHOST in shown(GA)[0].body

    text = reply(
        ids=[A, GHOST],
        claims=[affects(A, "django", "3.0.4")],
    )
    checked = run("Which advisories affect django 3.0.4?", text, GA)

    assert checked.verdict == "repaired" and checked.removed_ids == [GHOST]
    assert GHOST not in checked.text


def test_a_reply_whose_every_listed_id_was_invented_is_refused():
    text = reply(ids=["CVE-2099-0001"], claims=[affects(A, "django", "3.0.4")])

    refused_by(run("Which advisories affect django 3.0.4?", text, GA), 3)


def test_an_invented_id_inside_value_or_disagreement_is_refused_not_cut():
    in_value = reply(value="CVE-2099-0001", claims=[affects(A, "django", "3.0.4")])
    in_sides = reply(
        disagreement={"flagged": True, "values": {"github": "CVE-2099-0001", "nvd": None}},
        claims=[affects(A, "django", "3.0.4")],
    )

    refused_by(run("What is the first patched version?", in_value, GA), 3)
    refused_by(run("Do they agree?", in_sides, GA), 3)


def test_the_checked_reply_never_holds_an_id_the_evidence_did_not():
    text = reply(
        ids=[A, "GHSA-qqqq-qqqq-qqqq"],
        explanation="See CVE-2088-0002. It is real.",
        claims=[
            affects(A, "django", "3.0.4"),
            {"kind": "alias", "record": A, "cve": "CVE-2088-0002"},
        ],
    )

    checked = run("Which advisories affect django 3.0.4?", text, GA)

    found = {normal_id(found) for found in ANY_ID.findall(checked.text)}
    assert found <= {A, "CVE-2020-0001"}


def test_a_model_abstention_stands_unchanged_and_is_counted_as_the_models():
    text = reply(abstain=True, explanation="The records do not say.")

    checked = run("What is the first patched version of numpy?", text, GA)

    assert (checked.verdict, checked.route, checked.text) == ("abstained", "model", text)


def test_an_abstention_that_carries_an_invented_id_is_cut_down_to_a_plain_one():
    text = reply(abstain=True, explanation="Not here. Try CVE-2099-0001 instead.", ids=[])

    checked = run("What is the first patched version of numpy?", text, GA)

    assert checked.verdict == "abstained" and checked.route == "model"
    assert json.loads(checked.text)["explanation"] == "Not here."


# --- 2. the gate ------------------------------------------------------------------------------


def test_a_question_naming_an_id_the_store_lacks_is_refused_and_the_model_is_not_called():
    client = StubClient(reply(ids=[A]))
    question = {
        "id": "ab-001",
        "split": "dev",
        "question": "Which package does CVE-2025-99475 affect?",
    }

    response = respond(question, shown(GA), FACTS, client, system_prompt())

    assert client.requests == []
    assert response.line is None
    assert (response.checked.route, response.checked.verdict, response.checked.rule) == (
        "gate", "refused", 1,
    )  # fmt: skip
    assert json.loads(response.checked.text)["abstain"] is True


def test_the_dev_run_still_asks_the_model_on_a_gated_question_and_the_gate_still_wins():
    client = StubClient(reply(ids=[A], claims=[affects(A, "django", "3.0.4")]))
    question = {
        "id": "ab-001",
        "split": "dev",
        "question": "Which package does CVE-2025-99475 affect?",
    }

    response = respond(question, shown(GA), FACTS, client, system_prompt(), ask_anyway=True)

    assert len(client.requests) == 1
    assert response.line is not None and A in response.line["text"]
    assert response.checked.route == "gate"
    assert json.loads(response.checked.text)["abstain"] is True


def test_a_question_naming_ids_the_store_holds_goes_to_the_model():
    client = StubClient(reply(abstain=True))
    question = {"id": "x", "split": "dev", "question": f"What does {A} describe?"}

    respond(question, shown(GA), FACTS, client, system_prompt())

    assert len(client.requests) == 1


# --- 3. a package outside the 18 ---------------------------------------------------------------


def test_a_question_about_a_package_outside_the_18_is_refused_by_the_model_or_by_a_failed_claim():
    question = f"Is numpy 1.2.0 affected by {A}?"

    declined = run(question, reply(abstain=True), GA)
    claimed = run(
        question,
        reply(verdict="yes", claims=[{"kind": "package", "record": A, "package": "numpy"}]),
        GA,
    )

    assert (declined.route, declined.verdict) == ("model", "abstained")
    refused_by(claimed, 6)


# --- 4. affects: wrong refused for PyPI, npm and Maven, right passes ----------------------------

ECOSYSTEMS = [
    (A, "django", "3.0.4", "3.0.5", GA),
    (B, "axios", "1.3.2", "1.4.0", GB),
    (C, SPRING, "4.0.5", "4.0.9", GC),
]


@pytest.mark.parametrize(("record", "package", "inside", "outside", "unit"), ECOSYSTEMS)
def test_a_right_affects_claim_passes_and_a_wrong_one_is_refused(
    record, package, inside, outside, unit
):
    def ask(version, said):
        question = f"Is {package} {version} affected by {record}?"
        text = reply(
            verdict="yes" if said else "no",
            claims=[affects(record, package, version, said)],
        )
        return run(question, text, unit)

    assert ask(inside, True).verdict == "passed"
    assert ask(outside, False).verdict == "passed"
    refused_by(ask(inside, False), 6)
    refused_by(ask(outside, True), 6)


@pytest.mark.parametrize(("record", "package", "inside", "outside", "unit"), ECOSYSTEMS)
def test_an_affects_claim_about_another_version_or_package_than_the_pair_is_refused(
    record, package, inside, outside, unit
):
    question = f"Is {package} {inside} affected by {record}?"

    other_version = reply(verdict="yes", claims=[affects(record, package, outside, False)])
    other_package = reply(verdict="yes", claims=[affects(record, "flask", inside, True)])

    refused_by(run(question, other_version, unit), 5)
    refused_by(run(question, other_package, unit), 5)


def test_a_pair_is_a_package_then_an_optional_version_word_then_a_version():
    assert question_pairs("Does CVE-2020-9402 affect django version 3.0.4?") == [
        ("django", "3.0.4")
    ]
    assert question_pairs("Is org.springframework:spring-webmvc 4.0.1.RELEASE affected?") == [
        (SPRING, "4.0.1.RELEASE")
    ]
    assert question_pairs("Which advisory is fixed in 2.3.29 for struts?") == []
    assert question_pairs("How many requests per second?") == []


def test_only_wording_that_asks_whether_something_is_affected_has_its_polarity_held():
    assert asks_if_affected("Would spring-webmvc 5.1.13 be vulnerable to CVE-2020-5398?")
    assert not asks_if_affected("Is django 3.0.4 safe from GHSA-aaaa-aaaa-aaaa?")


# --- 5. a wrong fixed version, severity, score or KEV claim -----------------------------------


def fixed(record, version, source="github"):
    return {
        "kind": "fixed_in", "record": record, "source": source, "package": "django",
        "version": version,
    }  # fmt: skip


@pytest.mark.parametrize(
    ("right", "wrong", "question", "units"),
    [
        (
            reply(value="3.0.5", claims=[fixed(A, "3.0.5")]),
            reply(value="3.0.4", claims=[fixed(A, "3.0.4")]),
            f"What is the first patched version of django for {A}?",
            (GA,),
        ),
        (
            reply(value="moderate", claims=[{"kind": "severity", "record": A, "label": "medium"}]),
            reply(
                value="critical", claims=[{"kind": "severity", "record": A, "label": "critical"}]
            ),
            f"What severity label does GitHub give {A}?",
            (GA,),
        ),
        (
            reply(
                value="7.5",
                claims=[{"kind": "score", "record": A, "source": "github", "cvss3": "7.5"}],
            ),
            reply(
                value="9.0",
                claims=[{"kind": "score", "record": A, "source": "github", "cvss3": "9.0"}],
            ),
            f"What CVSS v3 score does GitHub give {A}?",
            (GA,),
        ),
        (
            reply(
                value="9.8",
                claims=[
                    {"kind": "score", "record": "CVE-2020-0001", "source": "nvd", "cvss3": "9.8"}
                ],
            ),
            reply(
                value="7.5",
                claims=[
                    {"kind": "score", "record": "CVE-2020-0001", "source": "nvd", "cvss3": "7.5"}
                ],
            ),
            "What CVSS v3 score does NVD give CVE-2020-0001?",
            (GA, NVD_A),
        ),
        (
            reply(value="3.0.5", claims=[fixed("CVE-2020-0001", "3.0.5", "nvd")]),
            reply(value="3.0.6", claims=[fixed("CVE-2020-0001", "3.0.6", "nvd")]),
            "Which version does NVD say fixes CVE-2020-0001?",
            (GA, NVD_A),
        ),
        (
            reply(verdict="yes", claims=[{"kind": "kev", "cve": "CVE-2021-0002", "listed": True}]),
            reply(verdict="no", claims=[{"kind": "kev", "cve": "CVE-2021-0002", "listed": False}]),
            "Is CVE-2021-0002 on the CISA KEV list?",
            (GB,),
        ),
    ],
)
def test_a_right_fact_passes_and_a_wrong_one_is_refused(right, wrong, question, units):
    assert run(question, right, *units).verdict == "passed"
    refused_by(run(question, wrong, *units), 6)


def test_a_cve_that_is_not_the_alias_of_exactly_one_shown_advisory_cannot_stand_for_github():
    claim = {"kind": "score", "record": "CVE-2021-0002", "source": "github", "cvss3": None}

    refused_by(run("Score of CVE-2021-0002?", reply(value=None, claims=[claim]), GA), 4)


# --- 6. unverifiable claims are refused and counted apart -------------------------------------


def test_a_claim_the_code_cannot_check_is_refused_and_counted_apart_from_a_wrong_one():
    unparseable = run(
        f"Is {A} affected?",
        reply(verdict="yes", claims=[affects(A, "django", "banana")]),
        GA,
    )
    no_cpe = run(
        "Which version does NVD say fixes CVE-2022-0003?",
        reply(value="4.0.9", claims=[fixed("CVE-2022-0003", "4.0.9", "nvd")]),
        GC,
        NVD_C,
    )

    refused_by(unparseable, 6)
    assert [c["status"] for c in unparseable.claims] == ["unverifiable"]
    refused_by(no_cpe, 6)
    assert [c["status"] for c in no_cpe.claims] == ["unverifiable"]


# --- 7. support ------------------------------------------------------------------------------


def test_an_id_backed_only_by_a_package_claim_is_refused_when_the_question_has_a_pair():
    text = reply(ids=[A], claims=[{"kind": "package", "record": A, "package": "django"}])

    refused_by(run("Which advisories affect django 3.0.4?", text, GA), 7)


def test_an_id_with_no_claim_is_refused():
    text = reply(ids=[D], claims=[{"kind": "package", "record": A, "package": "django"}])

    refused_by(run("Which advisory covers pillow?", text, GA, GD), 7)


def test_a_verdict_with_no_matching_claim_is_refused_and_so_is_one_that_contradicts_its_claim():
    question = f"Is {A} affected in django 3.0.4?"
    unbacked = reply(verdict="yes", claims=[{"kind": "package", "record": A, "package": "django"}])
    contradicted = reply(verdict="no", claims=[affects(A, "django", "3.0.4", True)])

    refused_by(run(question, unbacked, GA), 7)
    refused_by(run(question, contradicted, GA), 7)


def test_a_verdict_must_rest_on_a_claim_about_the_id_the_question_names():
    question = f"Is pillow 2.0 affected by {A}?"
    other = reply(verdict="yes", claims=[affects(D, "pillow", "2.0", True)])

    refused_by(run(question, other, GA, GD), 7)


def test_a_flagged_that_disagrees_with_its_values_is_refused():
    question = "Do GitHub and NVD agree on the score for CVE-2020-0001?"
    claims = [
        {"kind": "score", "record": A, "source": "github", "cvss3": "7.5"},
        {"kind": "score", "record": "CVE-2020-0001", "source": "nvd", "cvss3": "9.8"},
    ]

    def ask(flagged):
        values = {"github": "7.5", "nvd": "9.8"}
        text = reply(disagreement={"flagged": flagged, "values": values}, claims=claims)
        return run(question, text, GA, NVD_A)

    assert ask(True).verdict == "passed"  # high against critical
    refused_by(ask(False), 7)


def test_a_silent_nvd_side_needs_a_score_claim_of_null_and_makes_flagged_true():
    question = "Do both GitHub and NVD score CVE-2023-0004 with CVSS v3?"
    claims = [
        {"kind": "score", "record": D, "source": "github", "cvss3": "7.5"},
        {"kind": "score", "record": "CVE-2023-0004", "source": "nvd", "cvss3": None},
    ]
    values = {"github": "7.5", "nvd": None}

    def ask(flagged, with_claims=claims):
        text = reply(disagreement={"flagged": flagged, "values": values}, claims=with_claims)
        return run(question, text, GD, "nvd:CVE-2023-0004")

    assert ask(True).verdict == "passed"
    refused_by(ask(False), 7)
    refused_by(ask(True, claims[:1]), 7)


def test_a_value_with_no_matching_passing_claim_is_refused():
    text = reply(value="3.0.5", claims=[{"kind": "package", "record": A, "package": "django"}])

    refused_by(run(f"What is the first patched version for {A}?", text, GA), 7)


# --- the rest of rules 2, 4 and 8 ------------------------------------------------------------


def test_a_reply_that_does_not_parse_is_a_parse_failure_and_is_not_repaired():
    checked = run("Which advisories affect django 3.0.4?", "I think it is " + A, GA)

    assert (checked.verdict, checked.rule) == ("parse_failure", 2)
    assert checked.text == "I think it is " + A


def test_more_than_forty_claims_is_a_refusal_not_a_cut():
    claims = [affects(A, "django", "3.0.4")] * 41

    refused_by(run("Which advisories affect django 3.0.4?", reply(ids=[A], claims=claims), GA), 2)


def test_a_claim_of_an_unknown_kind_or_citing_an_unshown_record_is_refused():
    unknown = reply(verdict="yes", claims=[{"kind": "vibes", "record": A}])
    # A is grounded, because the NVD record shown names it, but its advisory was not shown.
    unshown = reply(ids=[A], claims=[affects(A, "django", "3.0.4")])

    refused_by(run(f"Is {A} affected?", unknown, GA), 4)
    refused_by(run("Which advisories affect django 3.0.4?", unshown, NVD_A), 4)


def test_a_reply_that_answers_with_no_claim_is_refused():
    refused_by(run(f"Is {A} affected?", reply(explanation="Yes, it is."), GA), 8)


# --- 8. a correct reply passes unchanged, and the scorer reads both files ----------------------


def scorer():
    import importlib.util
    import sys
    from pathlib import Path

    name = "score_for_generation_tests"
    spec = importlib.util.spec_from_file_location(name, Path("eval/score.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def severity_case():
    question = {
        "id": "t-1", "type": "lookup", "subtype": "severity_id", "split": "dev", "slice": "x",
        "stale_risk": False, "maven_release": False, "ecosystem": "PyPI",
        "answers_with": "value", "question": f"What severity label does GitHub give {A}?",
    }  # fmt: skip
    gold = {
        "gold": {
            "abstain": False, "verdict": None, "ids": [], "value": "moderate",
            "disagreement": {"flagged": False, "values": {"github": None, "nvd": None}},
        }
    }  # fmt: skip
    claim = {"kind": "severity", "record": A, "label": "moderate"}
    return question, gold, reply(value="moderate", claims=[claim], explanation="It is moderate.")


def test_a_correct_reply_passes_unchanged_and_the_scorer_reads_the_raw_and_checked_lines_alike():
    score = scorer()
    question, gold, text = severity_case()
    checked = run(question["question"], text, GA)
    ids = score.Ids({"advisories": {A: []}, "out_of_scope": [], "nonexistent": []})

    raw_line = {"id": "t-1", "run": 1, "text": text, "stop_reason": "end_turn"}
    checked_line = {**raw_line, "text": checked.text}

    assert checked.verdict == "passed" and checked.text == text
    for line in (raw_line, checked_line):
        assert score.score_question(question, gold, line, ids)["outcome"] == "correct"


def test_a_raw_refusal_stays_a_refusal_in_the_checked_file():
    score = scorer()
    question, gold, text = severity_case()
    checked = run(question["question"], text, GA, stop="refusal")
    ids = score.Ids({"advisories": {A: []}, "out_of_scope": [], "nonexistent": []})

    line = {"id": "t-1", "run": 1, "text": checked.text, "stop_reason": "refusal"}

    assert checked.verdict == "stopped" and checked.text == text
    assert score.score_question(question, gold, line, ids)["outcome"] == "refusal"


def test_a_cut_off_reply_is_not_turned_into_an_answer():
    _, _, text = severity_case()

    checked = run("anything", text[:30], GA, stop="max_tokens")

    assert (checked.verdict, checked.text) == ("stopped", text[:30])


def test_package_names_fold_only_for_pypi_and_a_null_value_needs_no_claim():
    from advisor.generation.facts import canonical_package
    from advisor.generation.reading import is_score_text

    assert canonical_package("Pillow") == "pillow"
    assert canonical_package("log4j-core") == "org.apache.logging.log4j:log4j-core"
    assert canonical_package("log4j_core") is None
    assert canonical_package("spring.webmvc") is None
    assert canonical_package("numpy") is None
    assert is_score_text("8.6 (High)") and not is_score_text("2.3.29")
    assert not is_score_text("8.6" + " " * 200_000 + "x")  # must not take quadratic time

    text = reply(value="none", verdict="yes", claims=[affects(A, "django", "3.0.4")])
    assert run(f"Is {A} affected by django 3.0.4?", text, GA).verdict == "passed"
