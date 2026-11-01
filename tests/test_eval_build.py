"""The building blocks of the question builder, on tiny synthetic inputs. No network."""

import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("eval").resolve()))
spec = importlib.util.spec_from_file_location("build_questions", Path("eval/build_questions.py"))
build = importlib.util.module_from_spec(spec)
sys.modules["build_questions"] = build
spec.loader.exec_module(build)

GHSA_A = "GHSA-2222-3333-4444"
GHSA_B = "GHSA-5555-6666-7777"


def tiny_world(paraphrases=()):
    return build.World(
        {}, {}, {}, {}, {}, set(), {}, None, {p: "a description" for p in paraphrases}
    )


def item(subtype="fixed_id", subjects=(GHSA_A,), question="q"):
    return build.Item(
        "lookup", subtype, "L1-a", question, "value", build.answer(), "how", list(subjects)
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [(None, "none"), (0.0, "none"), (3.9, "low"), (4.0, "medium"), (6.9, "medium"),
     (7.0, "high"), (8.9, "high"), (9.0, "critical"), (10.0, "critical")],
)  # fmt: skip
def test_scores_fall_in_the_bands_the_rules_name(score, expected):
    assert build.band(score) == expected


@pytest.mark.parametrize(
    ("ecosystem", "version", "expected"),
    [
        ("PyPI", "3.10.11", True), ("PyPI", "3.10.11rc0", False), ("PyPI", "2.0.dev1", False),
        ("npm", "4.17.21", True), ("npm", "5.0.0-beta.3", False),
        ("Maven", "5.2.20.RELEASE", True), ("Maven", "2.0-beta7", False),
        ("Maven", "3.0.0-alpha1", False), ("Maven", "7.0.0-M1", False),
    ],
)  # fmt: skip
def test_only_plain_releases_are_used_as_the_version_in_a_question(ecosystem, version, expected):
    assert build.is_final(ecosystem, version) is expected


def test_an_advisory_stays_in_the_split_it_was_first_used_in():
    state = build.State()
    state.take(item(), "dev", post=False)

    assert state.allowed([GHSA_A], "dev")
    assert not state.allowed([GHSA_A], "test")
    assert state.allowed([GHSA_B], "test")


def test_an_advisory_is_not_the_subject_of_a_third_question():
    state = build.State()
    state.take(item(question="one"), "dev", post=False)
    state.take(item(question="two"), "dev", post=False)

    assert not state.allowed([GHSA_A], "dev")


def test_a_paraphrased_advisory_is_kept_for_the_description_lookups():
    builder = build.Builder(tiny_world([GHSA_A]), None, [])

    assert builder.make_item("dev", item("fixed_id")) is None
    assert builder.make_item("dev", item("identify_desc")) is not None


def test_the_same_question_text_is_never_asked_twice():
    builder = build.Builder(tiny_world(), None, [])
    first = builder.make_item("dev", item(question="same"))
    builder.st.take(first, "dev", post=False)

    assert builder.make_item("dev", item(subjects=(GHSA_B,), question="same")) is None


def test_an_invented_id_is_checked_once_and_remembered(tmp_path):
    calls = []

    def fake_get(url):
        calls.append(url)
        return 404, None

    absence = build.Absence(tmp_path / "checks.json", fake_get, pause=0)

    assert absence.absent("ghsa", "GHSA-2222-3333-4444") is True
    assert absence.absent("ghsa", "GHSA-2222-3333-4444") is True
    assert len(calls) == 1
    absence.save()
    assert build.Absence(tmp_path / "checks.json", fake_get, pause=0).known == absence.known


def test_an_id_that_exists_is_not_called_absent(tmp_path):
    absence = build.Absence(
        tmp_path / "checks.json", lambda url: (200, {"vulnerabilities": [{}]}), pause=0
    )

    assert absence.absent("cve", "CVE-2021-44228") is False


def test_nvd_answering_with_no_records_means_the_cve_is_absent(tmp_path):
    absence = build.Absence(
        tmp_path / "checks.json", lambda url: (200, {"vulnerabilities": []}), pause=0
    )

    assert absence.absent("cve", "CVE-2025-99999") is True


def test_an_answer_always_carries_every_scored_field():
    assert set(build.answer()) == {"abstain", "verdict", "ids", "value", "disagreement"}
    assert set(build.answer()["disagreement"]) == {"flagged", "values"}


def test_a_list_question_repeating_an_earlier_answer_set_is_refused():
    builder = build.Builder(tiny_world(), None, [])
    first = build.Item(
        "version", "set", "V2-a", "q1", "ids", build.answer(ids=[GHSA_A]), "how", [GHSA_A]
    )
    again = build.Item(
        "version", "set", "V2-b", "q2", "ids", build.answer(ids=[GHSA_A]), "how", [GHSA_A]
    )
    builder.st.take(builder.make_item("dev", first), "dev", post=False)

    assert builder.make_item("dev", again) is None
    assert builder.drops["a list question repeated an earlier answer set"] == 1
