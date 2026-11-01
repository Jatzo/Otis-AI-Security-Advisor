"""The shape of the evaluation set, checked from the committed files alone (no network).

These tests are what keeps the set honest after the freeze: the right number of questions of
each kind, no advisory in both splits, descriptions that do not copy the advisory's own words,
and every fake ID shown to be absent.
"""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

EVAL = Path("eval")
PLAN = {
    ("lookup", "dev"): 8, ("lookup", "test"): 22,
    ("version", "dev"): 9, ("version", "test"): 26,
    ("multihop", "dev"): 7, ("multihop", "test"): 18,
    ("abstain", "dev"): 8, ("abstain", "test"): 22,
    ("disagree", "dev"): 8, ("disagree", "test"): 22,
}  # fmt: skip


def read_lines(name):
    return [json.loads(line) for line in (EVAL / name).read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def questions():
    return read_lines("questions.jsonl")


@pytest.fixture(scope="module")
def gold():
    return {row["id"]: row for row in read_lines("gold.jsonl")}


def test_the_set_has_the_planned_size_for_each_type_and_split(questions):
    counts = Counter((q["type"], q["split"]) for q in questions)

    assert dict(counts) == PLAN
    assert len(questions) == 150


def test_every_question_has_one_gold_answer_and_ids_are_unique(questions, gold):
    ids = [q["id"] for q in questions]

    assert len(set(ids)) == len(ids) == len(gold)
    assert set(ids) == set(gold)


def test_no_advisory_is_the_subject_of_questions_in_both_splits(questions):
    splits = {}
    for q in questions:
        for subject in q["subjects"]:
            splits.setdefault(subject, set()).add(q["split"])

    assert [s for s, seen in splits.items() if len(seen) > 1] == []


def test_no_advisory_is_the_subject_of_more_than_two_questions(questions):
    uses = Counter(subject for q in questions for subject in q["subjects"])

    assert [s for s, n in uses.items() if n > 2] == []


def test_every_question_names_its_template_and_the_field_that_answers_it(questions):
    for q in questions:
        assert re.fullmatch(r"[A-Z]\d?d?-[a-z]", q["template"]), q["id"]
        assert q["answers_with"] in {"ids", "verdict", "value", "disagreement", "abstain"}


def test_lookups_split_evenly_between_naming_an_id_and_describing_the_advisory(questions):
    lookups = [q for q in questions if q["type"] == "lookup"]
    described = [q for q in lookups if q["subtype"].endswith("_desc")]

    assert len(described) == 15 and len(lookups) - len(described) == 15


def test_description_questions_copy_no_prose_from_the_advisory_and_carry_no_id(questions, gold):
    # Product names and versions repeat by necessity ("Spring MVC and WebFlux", "Django 5.1
    # before 5.1.4"), so the limits are runs of copied prose: 5 words from the title, 8 from
    # the body. Every description question stays under both.
    def runs(text, length):
        words = re.findall(r"[a-z0-9]+", text.lower())
        return {tuple(words[i : i + length]) for i in range(len(words) - length + 1)}

    for q in questions:
        if not q["subtype"].endswith("_desc"):
            continue
        assert "GHSA-" not in q["question"] and "CVE-" not in q["question"], q["id"]
        ghsa = gold[q["id"]]["evidence"]["ghsa"][0]
        record = json.loads(
            (EVAL / "evidence" / "ghsa" / f"{ghsa}.json").read_text(encoding="utf-8")
        )
        assert not runs(q["question"], 5) & runs(record["summary"], 5), q["id"]
        assert not runs(q["question"], 8) & runs(record.get("description") or "", 8), q["id"]


def test_the_description_lookups_use_each_paraphrased_advisory_exactly_once(questions):
    paraphrased = set(
        json.loads((EVAL / "paraphrases.json").read_text(encoding="utf-8"))["entries"]
    )
    used = [s for q in questions if q["subtype"].endswith("_desc") for s in q["subjects"]]

    assert sorted(used) == sorted(paraphrased)


def test_trivial_and_hard_abstain_questions_are_fifteen_each(questions):
    abstain = [q for q in questions if q["type"] == "abstain"]
    trivial = [
        q for q in abstain if q["subtype"] in {"fake_ghsa", "fake_cve", "fake_package", "off_topic"}
    ]

    assert len(trivial) == 15 and len(abstain) - len(trivial) == 15


def test_an_abstain_question_expects_nothing_but_to_abstain(questions, gold):
    for q in questions:
        answer = gold[q["id"]]["gold"]
        if q["type"] == "abstain":
            assert answer["abstain"] is True and answer["ids"] == [] and answer["value"] is None
        else:
            assert answer["abstain"] is False, q["id"]


def test_one_third_of_the_disagreement_questions_are_agree_controls(questions, gold):
    disagree = [q for q in questions if q["type"] == "disagree"]
    agree = [q for q in disagree if not gold[q["id"]]["gold"]["disagreement"]["flagged"]]

    assert len(disagree) == 30 and len(agree) == 10


def test_a_silent_source_is_recorded_as_none_not_as_a_zero(questions, gold):
    for q in questions:
        if q["subtype"] == "one_silent":
            assert gold[q["id"]]["gold"]["disagreement"]["values"]["nvd"] is None


def test_yes_and_no_answers_are_both_common(questions, gold):
    verdicts = [
        gold[q["id"]]["gold"]["verdict"] for q in questions if q["answers_with"] == "verdict"
    ]
    yes = verdicts.count("yes") / len(verdicts)

    assert 0.35 <= yes <= 0.65  # the majority-class floor is reported next to the results


def test_at_least_a_fifth_of_answerable_test_questions_are_after_the_cutoff(questions):
    answerable = [q for q in questions if q["split"] == "test" and q["answers_with"] != "abstain"]
    after = [q for q in answerable if q["slice"] == "post"]

    assert len(after) / len(answerable) >= 0.20


def test_the_maven_release_slice_has_at_least_five_questions(questions):
    assert sum(q["maven_release"] for q in questions) >= 5


def test_every_evidence_file_the_gold_names_is_committed(gold):
    for row in gold.values():
        ev = row["evidence"]
        for ghsa in ev["ghsa"]:
            assert (EVAL / "evidence" / "ghsa" / f"{ghsa}.json").exists(), (row["id"], ghsa)
        for cve in ev["nvd"]:
            assert (EVAL / "evidence" / "nvd" / f"{cve}.json").exists(), (row["id"], cve)
        for ghsa in ev["out_of_scope"]:
            assert (EVAL / "evidence" / "out_of_scope" / f"{ghsa}.json").exists(), (row["id"], ghsa)


def test_every_listed_answer_id_has_evidence(questions, gold):
    for q in questions:
        row = gold[q["id"]]
        if q["answers_with"] == "ids":
            for answer_id in row["gold"]["ids"]:
                if answer_id.startswith("GHSA-"):
                    assert answer_id in row["evidence"]["ghsa"], (q["id"], answer_id)


def test_every_invented_id_and_package_was_checked_and_found_absent(questions):
    checks = json.loads((EVAL / "evidence" / "checks.json").read_text(encoding="utf-8"))
    pattern = {
        "fake_ghsa": r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}",
        "fake_cve": r"CVE-\d{4}-\d+",
        "fake_package": r"[a-z]+(-[a-z]+)+",
    }
    kind = {"fake_ghsa": "ghsa", "fake_cve": "cve", "fake_package": "package"}
    for q in questions:
        if q["subtype"] in pattern:
            name = re.findall(pattern[q["subtype"]], q["question"])
            match = re.search(
                {
                    "fake_ghsa": r"GHSA-\S{14}",
                    "fake_cve": r"CVE-\d{4}-\d+",
                    "fake_package": r"of (\S+) are",
                }[q["subtype"]],
                q["question"],
            )
            assert name and match, q["id"]
            token = match.group(1) if q["subtype"] == "fake_package" else match.group(0)
            assert checks[f"{kind[q['subtype']]}:{token}"]["absent"] is True, q["id"]


def test_severity_answers_use_the_wording_of_the_corpus(questions, gold):
    for q in questions:
        if q["subtype"] in {"severity_id", "severity_desc"}:
            assert gold[q["id"]]["gold"]["value"] in {"low", "moderate", "high", "critical"}, q[
                "id"
            ]
        if q["subtype"] == "b_intersect":
            assert "medium" not in q["question"].lower(), q["id"]  # the corpus says moderate


def test_a_silent_nvd_means_no_v3_score_of_any_kind_on_its_record(questions, gold):
    # A Secondary (reporter's) v3 score on the NVD record would make "NVD gives none" arguable.
    for q in questions:
        if q["subtype"] != "one_silent":
            continue
        (cve,) = gold[q["id"]]["evidence"]["nvd"]
        record = json.loads((EVAL / "evidence" / "nvd" / f"{cve}.json").read_text(encoding="utf-8"))
        metrics = record.get("metrics") or {}
        assert not metrics.get("cvssMetricV31") and not metrics.get("cvssMetricV30"), q["id"]


def test_no_two_list_questions_share_the_same_answer_set(questions, gold):
    seen = {}
    for q in questions:
        if q["subtype"] in {"set", "b_intersect", "a2_kev_set"}:
            key = (q["subtype"], tuple(gold[q["id"]]["gold"]["ids"]))
            assert key not in seen, (seen.get(key), q["id"])
            seen[key] = q["id"]
