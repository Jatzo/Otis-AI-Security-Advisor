"""The evaluation scorer, run against small synthetic replies and against the committed set.
No network. Every rule in eval/rules.md, section 6, has a test here."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("score", Path("eval/score.py"))
score = importlib.util.module_from_spec(spec)
sys.modules["score"] = score
spec.loader.exec_module(score)

SNAPSHOT = {
    "snapshot": "test",
    "advisories": {
        "GHSA-aaaa-aaaa-aaaa": ["CVE-2020-0001"],
        "GHSA-bbbb-bbbb-bbbb": ["CVE-2020-0002", "CVE-2020-0003"],
        "GHSA-cccc-cccc-cccc": ["CVE-2020-0003"],
    },
    "out_of_scope": ["GHSA-zzzz-zzzz-zzzz", "CVE-2019-9999"],
    "nonexistent": ["CVE-2025-99475"],
}
IDS = score.Ids(SNAPSHOT)


def question(answers_with, subtype, text="A question.", **extra):
    return {
        "id": "q-1", "type": "lookup", "subtype": subtype, "split": "dev", "slice": "pre",
        "stale_risk": False, "maven_release": False, "ecosystem": "PyPI", "question": text,
        "answers_with": answers_with, **extra,
    }  # fmt: skip


def gold_for(**fields):
    base = {
        "abstain": False, "verdict": None, "ids": [], "value": None,
        "disagreement": {"flagged": False, "values": {"github": None, "nvd": None}},
    }  # fmt: skip
    return {"id": "q-1", "gold": {**base, **fields}}


def reply(**fields):
    base = {
        "abstain": False, "verdict": None, "ids": [], "value": None,
        "disagreement": {"flagged": False, "values": {"github": None, "nvd": None}},
        "explanation": "",
    }  # fmt: skip
    return {"id": "q-1", "text": json.dumps({**base, **fields}), "stop_reason": "end_turn"}


def run(q, g, line, ids=IDS):
    return score.score_question(q, g, line, ids)


# --- reading a reply ---


def test_a_reply_inside_one_code_fence_is_read():
    fenced = '```json\n{"abstain": true, "verdict": null, "ids": [], "value": null, '
    fenced += '"disagreement": {"flagged": false, "values": {"github": null, "nvd": null}}, '
    fenced += '"explanation": ""}\n```'

    answer, problem = score.read_reply(fenced)

    assert problem is None and answer["abstain"] is True


def test_text_before_the_json_is_ignored_but_nothing_is_repaired():
    good = json.dumps(json.loads(reply()["text"]))
    broken = good.replace('"explanation": ""', '"explanation": ')

    assert score.read_reply("Here is my answer: " + good)[1] is None
    assert score.read_reply(broken)[0] is None


@pytest.mark.parametrize(
    "change",
    [{"value": 5.3}, {"verdict": "maybe"}, {"abstain": "yes"}, {"ids": "GHSA-aaaa-aaaa-aaaa"}],
)
def test_a_reply_that_breaks_the_schema_is_a_parse_failure(change):
    row = run(question("value", "fixed_id"), gold_for(value="1.0"), reply(**change))

    assert row["outcome"] == "parse_failure" and row["problem"]


def test_a_reply_cut_short_or_refused_is_never_scored_as_an_answer():
    q, g = question("abstain", "fake_cve"), gold_for(abstain=True)
    cut = {**reply(abstain=True), "stop_reason": "max_tokens"}
    refused = {**reply(abstain=True), "stop_reason": "refusal"}

    assert run(q, g, cut)["outcome"] == "parse_failure"
    assert run(q, g, refused)["outcome"] == "refusal"


# --- marking ---


def test_a_ghsa_id_is_accepted_where_the_gold_names_its_cve():
    q, g = question("ids", "identify_desc"), gold_for(ids=["CVE-2020-0001"])

    assert run(q, g, reply(ids=["ghsa-AAAA-aaaa-aaaa"]))["outcome"] == "correct"


def test_a_cve_named_by_two_advisories_stands_for_neither():
    q, g = question("ids", "identify_desc"), gold_for(ids=["GHSA-bbbb-bbbb-bbbb"])

    assert run(q, g, reply(ids=["CVE-2020-0003"]))["outcome"] == "wrong"
    assert run(q, g, reply(ids=["CVE-2020-0002"]))["outcome"] == "correct"


def test_repeating_the_ghsa_back_does_not_answer_a_map_id_question():
    q = question("ids", "map_id", "Which CVE ID does GHSA-aaaa-aaaa-aaaa cover?")
    g = gold_for(ids=["CVE-2020-0001"])

    assert run(q, g, reply(ids=["GHSA-aaaa-aaaa-aaaa"]))["outcome"] == "wrong"
    assert run(q, g, reply(ids=["CVE-2020-0001"]))["outcome"] == "correct"


def test_an_id_list_must_match_as_a_set_and_reports_f1():
    q = question("ids", "set")
    g = gold_for(ids=["GHSA-aaaa-aaaa-aaaa", "GHSA-bbbb-bbbb-bbbb"])

    right = run(q, g, reply(ids=["GHSA-bbbb-bbbb-bbbb", "GHSA-aaaa-aaaa-aaaa", "CVE-2020-0001"]))
    short = run(q, g, reply(ids=["GHSA-aaaa-aaaa-aaaa"]))

    assert right["outcome"] == "correct" and right["f1"] == 1.0
    assert short["outcome"] == "wrong" and round(short["f1"], 2) == 0.67


def test_versions_differing_only_in_trailing_zeros_match_but_5_30_is_not_5_3():
    assert score.value_key("fixed_id", "2.25") == score.value_key("fixed_id", "v2.25.0")
    assert score.value_key("fixed_id", "5.30") != score.value_key("fixed_id", "5.3")
    assert score.value_key("a1_nvd_score", "5.30") == score.value_key("a1_nvd_score", "5.3")


def test_medium_reads_as_moderate_and_a_score_is_read_by_its_number():
    assert score.value_key("severity_id", "Medium") == score.value_key("severity_id", "moderate")
    assert score.value_key("band_differ", "8.6 (High)") == "8.6"


def test_a_yes_no_answer_is_marked_by_its_verdict():
    q, g = question("verdict", "verdict"), gold_for(verdict="yes")

    assert run(q, g, reply(verdict="yes"))["outcome"] == "correct"
    assert run(q, g, reply(verdict="no"))["outcome"] == "wrong"


def test_sources_disagree_needs_the_flag_and_both_values():
    q = question("disagreement", "band_differ")
    g = gold_for(disagreement={"flagged": True, "values": {"github": "8.6", "nvd": "5.9"}})

    def said(flagged, github, nvd):
        return reply(disagreement={"flagged": flagged, "values": {"github": github, "nvd": nvd}})

    assert run(q, g, said(True, "8.6 (High)", "5.9"))["outcome"] == "correct"
    assert run(q, g, said(False, "8.6", "5.9"))["outcome"] == "wrong"
    assert run(q, g, said(True, "8.6", "6.0"))["outcome"] == "wrong"


def test_a_silent_source_may_be_written_as_null_none_or_na():
    q = question("disagreement", "one_silent")
    g = gold_for(disagreement={"flagged": True, "values": {"github": "7.5", "nvd": None}})

    for word in (None, "none", "N/A", ""):
        said = reply(disagreement={"flagged": True, "values": {"github": "7.5", "nvd": word}})
        assert run(q, g, said)["outcome"] == "correct"


def test_abstaining_on_an_answerable_question_is_wrong_even_with_the_right_value():
    q, g = question("value", "fixed_id"), gold_for(value="2.0")

    row = run(q, g, reply(abstain=True, value="2.0"))

    assert row["outcome"] == "wrong" and row["over_abstained"] and row["abstained"]


def test_a_should_abstain_question_is_marked_by_the_abstain_flag_alone():
    q, g = question("abstain", "fake_cve"), gold_for(abstain=True)

    assert run(q, g, reply(abstain=True))["outcome"] == "correct"
    assert run(q, g, reply(abstain=False, value="1.0"))["outcome"] == "wrong"


# --- fabrication ---


def test_a_made_up_cve_in_the_explanation_is_labelled_nonexistent():
    q, g = question("abstain", "fake_cve"), gold_for(abstain=True)

    row = run(q, g, reply(abstain=True, explanation="Maybe it is CVE-2025-99475."))

    assert row["labels"] == {"CVE-2025-99475": "nonexistent"}


def test_an_id_repeated_from_the_question_is_counted_apart_not_labelled():
    q = question("abstain", "fake_cve", "Which package does CVE-2025-99475 affect?")
    g = gold_for(abstain=True)

    row = run(q, g, reply(abstain=True, explanation="CVE-2025-99475 is not in the corpus."))

    assert row["labels"] == {} and row["echoed"] == ["CVE-2025-99475"]


def test_a_real_advisory_outside_the_scope_is_not_fabrication():
    q, g = question("abstain", "out_of_scope"), gold_for(abstain=True)
    row = run(q, g, reply(abstain=True, explanation="GHSA-zzzz-zzzz-zzzz is outside the scope."))

    summary = score.summarise([row])

    assert row["labels"] == {"GHSA-zzzz-zzzz-zzzz": "out_of_scope"}
    assert summary["fabricated"] == (0, 1)


def test_an_unknown_id_is_unchecked_and_turns_the_rate_into_a_range():
    q, g = question("abstain", "fake_cve"), gold_for(abstain=True)
    row = run(q, g, reply(abstain=True, explanation="See CVE-2030-1234567."))

    summary = score.summarise([row])

    assert row["labels"] == {"CVE-2030-1234567": "unchecked"}
    assert summary["fabricated"] == (0, 1) and summary["fabricated_upper"] == (1, 1)
    assert "up to" in score.render(summary, "x")


# --- summaries ---


def test_declining_everything_scores_nothing_on_answerable_questions():
    declined = []
    for kind, subtype, g in (
        ("abstain", "fake_cve", gold_for(abstain=True)),
        ("value", "fixed_id", gold_for(value="2.0")),
        ("verdict", "verdict", gold_for(verdict="yes")),
    ):
        declined.append(run(question(kind, subtype), g, reply(abstain=True)))

    summary = score.summarise(declined)

    assert summary["answerable"] == (0, 2)
    assert summary["over_abstained"] == (2, 2)
    assert summary["abstain_recall"] == (1, 1)
    assert summary["abstain_precision"] == (1, 3)


def test_trivial_and_hard_abstain_questions_are_reported_apart():
    rows = [
        run(question("abstain", "fake_cve"), gold_for(abstain=True), reply(abstain=True)),
        run(question("abstain", "withdrawn"), gold_for(abstain=True), reply(abstain=False)),
    ]

    summary = score.summarise(rows)

    assert summary["abstain_trivial"] == (1, 1) and summary["abstain_hard"] == (0, 1)


def test_a_refusal_a_parse_failure_and_an_abstention_are_counted_separately():
    q, g = question("abstain", "fake_cve"), gold_for(abstain=True)
    rows = [
        run(q, g, reply(abstain=True)),
        run(q, g, {**reply(abstain=True), "stop_reason": "refusal"}),
        run(q, g, {"id": "q-1", "text": "no idea", "stop_reason": "end_turn"}),
    ]

    summary = score.summarise(rows)

    assert (summary["abstentions"], summary["refusals"], summary["parse_failures"]) == (1, 1, 1)
    assert summary["all"] == (1, 3)


def test_wilson_interval_and_exact_mcnemar_match_known_values():
    low, high = score.wilson(17, 22)

    assert round(low, 2) == 0.57 and round(high, 2) == 0.90
    assert score.mcnemar_p(0, 5) == pytest.approx(0.0625)
    assert score.mcnemar_p(3, 3) == 1.0
    assert score.mcnemar_p(0, 0) == 1.0


def test_the_same_question_twice_in_one_run_stops_the_scorer():
    q, g = question("abstain", "fake_cve"), gold_for(abstain=True)

    with pytest.raises(ValueError, match="twice"):
        score.score_all([q], {"q-1": g}, [reply(abstain=True), reply(abstain=True)], IDS)


def test_errata_replace_the_gold_without_touching_the_frozen_file(tmp_path):
    errata = tmp_path / "errata.jsonl"
    errata.write_text(
        json.dumps({"id": "q-1", "gold": gold_for(value="3.0")["gold"], "reason": "typo"}) + "\n"
    )
    original = {"q-1": gold_for(value="2.0")}

    fixed = score.with_errata(original, errata)

    assert fixed["q-1"]["gold"]["value"] == "3.0" and original["q-1"]["gold"]["value"] == "2.0"


# --- looking up an ID ---


def test_an_id_that_github_and_osv_both_deny_is_nonexistent():
    def get(url):
        return (404, None)

    assert score.look_up("GHSA-qqqq-qqqq-qqqq", get)["label"] == "nonexistent"


def test_an_empty_nvd_answer_is_not_proof_without_osv():
    def get(url):
        if "nvd.nist.gov" in url:
            return 200, {"vulnerabilities": []}
        return 404, None

    assert score.look_up("CVE-2030-1", get)["label"] == "nonexistent"


def test_an_id_that_osv_knows_is_real_but_outside_the_scope():
    def get(url):
        if "nvd.nist.gov" in url:
            return 200, {"vulnerabilities": []}
        return 200, {}

    assert score.look_up("CVE-2019-1111", get)["label"] == "out_of_scope"


def test_a_rate_limit_or_network_failure_leaves_the_id_unchecked():
    assert score.look_up("GHSA-qqqq-qqqq-qqqq", lambda url: (429, None))["label"] == "unchecked"
    assert score.look_up("GHSA-qqqq-qqqq-qqqq", lambda url: (0, None))["label"] == "unchecked"


def test_lookups_are_kept_so_a_second_run_asks_nothing(tmp_path):
    path = tmp_path / "id_lookups.json"
    calls = []

    def get(url):
        calls.append(url)
        return 404, None

    score.settle_lookups({"GHSA-qqqq-qqqq-qqqq"}, path, get, pause=0)
    score.settle_lookups({"GHSA-qqqq-qqqq-qqqq"}, path, get, pause=0)

    assert len(calls) == 2  # GitHub and OSV, once
    assert json.loads(path.read_text())["GHSA-qqqq-qqqq-qqqq"]["label"] == "nonexistent"


# --- the committed set ---


@pytest.fixture(scope="module")
def committed():
    questions = [
        json.loads(x) for x in Path("eval/questions.jsonl").read_text("utf-8").split("\n") if x
    ]
    gold = {g["id"]: g for g in score.read_lines(Path("eval/gold.jsonl"))}
    snapshot = json.loads(Path("eval/id_snapshot.json").read_text("utf-8"))
    return questions, gold, score.Ids(snapshot)


def perfect_reply(gold_row):
    answer = {**gold_row["gold"], "explanation": ""}
    return {
        "id": gold_row["id"], "text": json.dumps(answer), "stop_reason": "end_turn",
        "cost_usd": 0.01, "latency_s": 2.0,
    }  # fmt: skip


def test_the_gold_scored_as_a_reply_is_right_on_every_question_and_fabricates_nothing(committed):
    questions, gold, ids = committed
    lines = [perfect_reply(gold[q["id"]]) for q in questions]

    summary = score.summarise(score.score_all(questions, gold, lines, ids)[1])

    assert summary["all"] == (150, 150)
    assert summary["fabricated"] == (0, 150) and summary["fabricated_upper"] == (0, 150)


def test_declining_every_committed_question_gets_only_the_abstain_questions_right(committed):
    questions, gold, ids = committed
    nothing = {"flagged": False, "values": {"github": None, "nvd": None}}
    decline = {
        "abstain": True, "verdict": None, "ids": [], "value": None, "explanation": "",
        "disagreement": nothing,
    }  # fmt: skip
    lines = [
        {"id": q["id"], "text": json.dumps(decline), "stop_reason": "end_turn"} for q in questions
    ]

    summary = score.summarise(score.score_all(questions, gold, lines, ids)[1])

    assert summary["all"] == (30, 150) and summary["answerable"] == (0, 120)
    assert summary["abstain_precision"] == (30, 150)


def test_every_id_in_the_gold_is_in_the_committed_snapshot(committed):
    _, gold, ids = committed
    named = {i for g in gold.values() for i in g["gold"]["ids"]}

    assert [i for i in named if ids.label(score.normal_id(i)) != "corpus"] == []


def test_every_invented_id_in_a_question_is_known_to_be_absent(committed):
    questions, _, ids = committed
    invented = [
        score.normal_id(i)
        for q in questions
        if q["subtype"] in ("fake_cve", "fake_ghsa")
        for i in score.ANY_ID.findall(q["question"])
    ]

    assert invented and {ids.label(i) for i in invented} == {"nonexistent"}


def test_a_snapshot_is_built_from_osv_files_the_rest_cache_and_the_evidence(tmp_path):
    raw, rest, evidence = tmp_path / "raw", tmp_path / "rest", tmp_path / "evidence"
    for folder in (raw / "osv", rest, evidence / "out_of_scope"):
        folder.mkdir(parents=True)
    (tmp_path / "manifest.json").write_text(json.dumps({"snapshot_id": "abc"}))
    osv = {"id": "GHSA-aaaa-aaaa-aaaa", "aliases": ["cve-2020-0001", "BIT-x-1"]}
    (raw / "osv" / "GHSA-aaaa-aaaa-aaaa.json").write_text(json.dumps(osv))
    (raw / "osv" / "_fetch.json").write_text("{}")
    for ghsa, cve in (
        ("GHSA-aaaa-aaaa-aaaa", "CVE-2020-0001"),
        ("GHSA-wwww-wwww-wwww", "CVE-2019-1"),
    ):
        (rest / f"{ghsa}.json").write_text(json.dumps({"ghsa_id": ghsa, "cve_id": cve}))
    (evidence / "out_of_scope_cache.json").write_text(
        json.dumps([{"ghsa_id": "GHSA-oooo-oooo-oooo"}])
    )
    (evidence / "checks.json").write_text(
        json.dumps({"cve:CVE-2025-1": {"absent": True}, "cve:CVE-2025-2": {"absent": False}})
    )

    built = score.build_snapshot(raw, rest, evidence)

    assert built["snapshot"] == "abc"
    assert built["advisories"] == {"GHSA-aaaa-aaaa-aaaa": ["CVE-2020-0001"]}
    assert built["out_of_scope"] == ["CVE-2019-1", "GHSA-oooo-oooo-oooo", "GHSA-wwww-wwww-wwww"]
    assert built["nonexistent"] == ["CVE-2025-1"]


def test_the_snapshot_can_be_rebuilt_from_the_raw_files_and_matches_the_committed_one():
    root = Path("data")
    if not (root / "raw" / "osv").exists() or not (root / "rest_cache").exists():
        pytest.skip("the raw snapshot is not on this machine; CI reads the committed file only")

    rebuilt = score.build_snapshot(root / "raw", root / "rest_cache", Path("eval/evidence"))

    assert rebuilt == json.loads(Path("eval/id_snapshot.json").read_text("utf-8"))
