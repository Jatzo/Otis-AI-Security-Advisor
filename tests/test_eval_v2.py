"""Facts about the built Test v2 set that the write-up relies on. No network, no model."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

from advisor.structured import FORMS

V2 = Path("eval-v2")
V1 = Path("eval")


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def questions():
    return rows(V2 / "questions.jsonl")


@pytest.fixture(scope="module")
def golds():
    return rows(V2 / "gold.jsonl")


def reads(text):
    return any(re.fullmatch(pattern, text) for _, pattern in FORMS)


def test_ids_and_wordings_are_unique_and_none_is_a_v1_question(questions):
    v1_text = {q["question"] for q in rows(V1 / "questions.jsonl")}

    assert len({q["id"] for q in questions}) == len(questions)
    assert len({q["question"] for q in questions}) == len(questions)
    assert not {q["question"] for q in questions} & v1_text
    assert all(q["id"].startswith("v2-") and q["split"] == "v2" for q in questions)


def test_every_question_has_one_gold_row_naming_the_same_field(questions, golds):
    by_id = {g["id"]: g for g in golds}

    assert set(by_id) == {q["id"] for q in questions}
    assert all(by_id[q["id"]]["answers_with"] == q["answers_with"] for q in questions)


def test_the_mix_is_the_one_in_the_plan(questions):
    counts = Counter(q["type"] for q in questions)

    assert counts["abstain"] == 20
    assert counts["disagree"] == 20
    assert counts["lookup"] == 24
    assert counts["version"] == 22
    # One KEV list question short: KEV holds ten advisories, and a repeated answer set is refused.
    assert counts["multihop"] == 23


def test_at_least_45_questions_are_worded_where_the_structured_row_cannot_read_them(questions):
    free = [q for q in questions if q["form"] == "free"]

    assert len(free) >= 45
    assert not [q["id"] for q in free if reads(q["question"])]


def test_the_form_flag_is_not_a_claim_the_v1_wordings_contradict(questions):
    answerable_v1_form = [
        q for q in questions if q["form"] == "v1" and q["answers_with"] != "abstain"
    ]

    assert answerable_v1_form
    assert all(reads(q["question"]) for q in answerable_v1_form)


def test_a_v1_advisory_is_used_only_where_the_question_says_so(questions):
    v1_subjects = {s for q in rows(V1 / "questions.jsonl") for s in q["subjects"]}

    for q in questions:
        overlap = bool(set(q["subjects"]) & v1_subjects)
        assert q["reuses_v1"] == overlap, q["id"]


def test_no_advisory_is_the_subject_of_more_than_two_questions(questions):
    uses = Counter(s for q in questions for s in q["subjects"])

    assert max(uses.values()) <= 2


def test_post_cutoff_share_of_answerable_questions_is_at_least_a_fifth(questions):
    answerable = [q for q in questions if q["answers_with"] != "abstain"]
    post = [q for q in answerable if q["slice"] == "post"]

    assert len(post) / len(answerable) >= 0.2


def test_the_review_table_has_a_row_for_every_question(questions):
    review = (V2 / "review.md").read_text(encoding="utf-8")

    assert all(f"| {q['id']} |" in review for q in questions)
