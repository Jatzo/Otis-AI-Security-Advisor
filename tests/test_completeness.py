"""The completeness check of docs/completeness-spec-v1.md, and the runner options that use it.
No test here calls the API."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from generation_world import FACTS, SPRING, UNITS, A, B, StubClient, reply, shown

from advisor.generation import completeness as spec
from advisor.generation.checker import check
from advisor.generation.completeness import COMPLETE_TEXT, Completeness
from advisor.retrieval import candidates
from advisor.retrieval.units import Unit

GA = f"ghsa:{A}"
PACKAGES = ["django", "axios", SPRING, "pillow"]
COMPLETE = Completeness(list(UNITS.values()), PACKAGES)
DJANGO = sorted(COMPLETE.scope["django"])
QUESTION = "Which advisories affect django 3.0.4?"


def load(name, path):
    module_spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    return module


runner = load("run_generation_for_completeness_tests", "scripts/run_generation.py")


def affects(record):
    return {
        "kind": "affects", "record": record, "package": "django", "version": "3.0.4",
        "affected": True,
    }  # fmt: skip


def good(**more):
    return reply(ids=[A], claims=[affects(A)], explanation=f"{A} affects it.", **more)


def run(unit_ids, text=None, question=QUESTION, completeness=COMPLETE):
    return check(question, text or good(), "end_turn", shown(*unit_ids), FACTS, completeness)


# --- which questions it covers ----------------------------------------------------------------


def test_the_scope_of_a_package_is_every_unit_that_names_it_and_no_other():
    assert GA in DJANGO
    assert not any(unit_id.endswith(B) for unit_id in DJANGO)


@pytest.mark.parametrize(
    ("question", "package"),
    [
        ("Which advisories affect django?", "django"),
        ("which versions of axios are fixed?", "axios"),
        ("What advisories affect pillow?", "pillow"),
        ("List all advisories for pillow.", "pillow"),
        ("Name every advisory for django 3.0.4.", "django"),
        ("Show all the advisories that mention axios.", "axios"),
    ],
)
def test_a_question_that_asks_for_a_list_about_one_package_is_covered(question, package):
    assert COMPLETE.covered(question) == package


@pytest.mark.parametrize(
    "question",
    [
        "Is django 3.0.4 affected by anything?",
        "  Does axios have any advisories?",
        "Which advisories affect django and axios?",
        "Which advisories affect Rails?",
        "Tell me about django.",
        "What is the severity of django?",
    ],
)
def test_yes_no_questions_and_questions_with_no_or_two_packages_are_not_covered(question):
    assert COMPLETE.covered(question) is None


# --- when a reply is withheld -----------------------------------------------------------------


def test_a_reply_is_withheld_when_a_record_of_the_package_was_not_shown():
    checked = run([GA])

    assert checked.verdict == "refused" and checked.route == "checker" and checked.rule == 9
    body = json.loads(checked.text)
    assert body["abstain"] is True and body["explanation"] == COMPLETE_TEXT
    assert body["ids"] == [] and body["claims"] == []
    assert "were not shown" in checked.reasons[0]


def test_a_reply_is_shown_when_every_record_of_the_package_was_shown():
    checked = run(DJANGO)

    assert checked.verdict == "passed" and checked.rule is None


def test_the_check_is_off_unless_it_is_asked_for():
    assert run([GA], completeness=None).verdict == "passed"
    assert check(QUESTION, good(), "end_turn", shown(GA), FACTS).verdict == "passed"


@pytest.mark.parametrize("phrase", spec.PARTIAL_PHRASES)
def test_a_reply_that_says_plainly_it_covers_only_part_of_the_list_is_shown(phrase):
    text = reply(
        ids=[A], claims=[affects(A)], explanation=f"{A} affects it. This is {phrase.upper()}."
    )

    assert run([GA], text).verdict == "passed"


def test_an_abstention_is_left_as_the_model_wrote_it():
    text = reply(abstain=True, explanation="Otis does not hold enough to say.")

    checked = run([GA], text)

    assert checked.verdict == "abstained" and checked.route == "model"


def test_a_question_that_is_not_covered_is_not_withheld_even_if_records_are_missing():
    text = reply(ids=[A], claims=[affects(A)], explanation=f"{A} affects it.")

    assert run([GA], text, "Is django 3.0.4 affected by anything?").verdict == "passed"


def test_a_reply_with_no_ids_is_still_covered():
    text = reply(ids=[], claims=[affects(A)], explanation="It is affected.")

    assert run(DJANGO, text).verdict == "passed"
    assert run([GA], text).rule == 9


def test_a_reply_that_rule_3_repaired_is_still_withheld_when_records_are_missing():
    text = reply(ids=[A, "CVE-2099-0001"], claims=[affects(A)], explanation=f"{A} affects it.")

    checked = run([GA], text)

    assert checked.rule == 9 and checked.removed_ids == ["CVE-2099-0001"]


def test_a_package_with_more_than_ten_records_can_never_pass():
    many = [
        Unit(f"ghsa:GHSA-{i:04d}", "ghsa", "h", "b", frozenset({"django"}), frozenset())
        for i in range(11)
    ]
    big = Completeness(many, ["django"])
    shown_ten = {u.unit_id for u in many[:10]}

    assert big.missing(QUESTION, shown_ten, "") == [many[10].unit_id]


# --- the runner options -----------------------------------------------------------------------


def args(**more):
    base = {
        "split": "dev", "retrieval": "R1", "completeness": False, "recheck": False,
        "recheck_to": None, "dry_run": False, "label": None,
    }  # fmt: skip
    return SimpleNamespace(**{**base, **more})


def test_the_defaults_have_nothing_to_refuse():
    assert runner.option_problem(args()) is None


def test_r9_and_completeness_are_refused_on_the_test_split():
    assert runner.option_problem(args(split="test", retrieval="R9"))
    assert runner.option_problem(args(split="test", completeness=True))


def test_a_paid_run_with_r9_or_completeness_needs_its_own_label():
    assert runner.option_problem(args(retrieval="R9"))
    assert runner.option_problem(args(completeness=True))
    assert runner.option_problem(args(retrieval="R9", completeness=True, label="r9")) is None


def test_a_dry_run_or_a_recheck_with_r9_needs_no_label():
    assert runner.option_problem(args(retrieval="R9", dry_run=True)) is None
    assert runner.option_problem(args(retrieval="R9", recheck=True)) is None


def test_a_recheck_with_completeness_must_write_elsewhere():
    assert runner.option_problem(args(completeness=True, recheck=True))
    assert (
        runner.option_problem(args(completeness=True, recheck=True, recheck_to="out-phase7.jsonl"))
        is None
    )


def test_shown_ids_is_r1s_top_ten_by_default_and_r9s_linked_records_for_r9():
    units = list(UNITS.values())
    links = candidates.Links(units)
    ranked = [u.unit_id for u in units]

    assert runner.shown_ids(ranked, "R1", None) == ranked[:10]
    assert runner.shown_ids(ranked, "R9", links) == candidates.r9(ranked, links, 10)


def test_a_file_is_never_resumed_with_another_retrieval_but_older_lines_count_as_r1():
    hashes = {"task.md": "t", "addendum.md": "a"}
    older = [{"hashes": hashes}]
    r9_lines = [{"hashes": hashes, "retrieval": "R9"}]

    assert runner.mixed_prompt(older, {"hashes": hashes}) is None
    assert runner.mixed_prompt(r9_lines, {"hashes": hashes, "retrieval": "R9"}) is None
    assert "different retrieval" in runner.mixed_prompt(
        older, {"hashes": hashes, "retrieval": "R9"}
    )
    assert "different retrieval" in runner.mixed_prompt(r9_lines, {"hashes": hashes})


def test_a_recheck_applies_rule_9_only_when_given_a_completeness(tmp_path):
    raw = tmp_path / "x-raw.jsonl"
    line = {
        "id": "q1", "run": 1, "split": "dev", "text": good(), "stop_reason": "end_turn",
        "cost_usd": 0.0, "shown": [GA],
    }  # fmt: skip
    raw.write_text(json.dumps(line) + "\n", encoding="utf-8")
    question = {"id": "q1", "question": QUESTION, "split": "dev", "type": "version"}
    plain, withheld = tmp_path / "plain.jsonl", tmp_path / "withheld.jsonl"

    without = runner.recheck([question], UNITS, FACTS, raw, plain)
    with_rule = runner.recheck([question], UNITS, FACTS, raw, withheld, COMPLETE)

    assert dict(without) == {("answer", "passed"): 1}
    assert dict(with_rule) == {("checker", "refused"): 1}
    (out,) = [json.loads(x) for x in withheld.read_text(encoding="utf-8").splitlines()]
    assert out["checker"]["rule"] == 9


def test_a_phrase_in_a_sentence_that_rule_3_cuts_still_counts_as_the_reply_saying_so():
    text = reply(
        ids=[A, "CVE-2099-0001"],
        claims=[affects(A)],
        explanation=f"{A} affects it. This is only part of the list, and CVE-2099-0001 is another.",
    )

    checked = run([GA], text)

    assert checked.verdict == "repaired" and checked.rule is None


def test_a_run_with_r9_shows_r9s_list_and_stamps_its_lines_while_r1_lines_stay_as_before(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    units = list(UNITS.values())
    pipeline, links = runner.Pipeline(units), candidates.Links(units)
    question = {"id": "t-1", "split": "dev", "type": "version", "question": QUESTION}
    proof = {"commit": "abc", "dirty": False, "hashes": {"addendum.md": "aa", "task.md": "bb"}}
    expected = candidates.r9(pipeline.rank(runner.R1, QUESTION), links, 10)

    def asked(retrieval, stamped):
        raw = tmp_path / f"{retrieval}-raw.jsonl"
        runner.run_questions(
            [question], pipeline, UNITS, raw, StubClient(good()), 1, 10.0, 10.0,
            {**proof, **stamped}, retrieval=retrieval, links=links,
        )  # fmt: skip
        return json.loads(raw.read_text(encoding="utf-8").splitlines()[0])

    r9_line = asked("R9", {"retrieval": "R9"})
    r1_line = asked("R1", {})

    assert r9_line["shown"] == expected and r9_line["retrieval"] == "R9"
    assert r1_line["shown"] == pipeline.rank(runner.R1, QUESTION)[:10]
    assert "retrieval" not in r1_line
