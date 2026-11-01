"""The ladder's pipeline and scoring, against hand-made units and fakes. No model, no network."""

import json

import numpy as np
import pytest

from advisor.retrieval import ladder
from advisor.retrieval.pipeline import DEPTH, Pipeline, Spec
from advisor.retrieval.units import Unit


def unit(unit_id, header, body, packages=(), aliases=()):
    return Unit(
        unit_id, unit_id.split(":")[0], header, body, frozenset(packages), frozenset(aliases)
    )


UNITS = [
    unit("ghsa:GHSA-2222-2222-2222", "pyyaml advisory", "deserialisation runs code", ["pyyaml"],
         ["GHSA-2222-2222-2222", "CVE-2020-0001"]),
    unit("ghsa:GHSA-3333-3333-3333", "requests advisory", "credentials leak on redirect",
         ["requests"], ["GHSA-3333-3333-3333"]),
    unit("ghsa:GHSA-4444-4444-4444", "urllib3 advisory", "slow header parsing " + "x " * 1000,
         ["urllib3"], ["GHSA-4444-4444-4444"]),
    unit("nvd:CVE-2020-0001", "NVD record", "pyyaml flaw described by NVD", ["pyyaml"],
         ["CVE-2020-0001"]),
]  # fmt: skip


class KeywordEmbedder:
    """Dense vectors from a fixed word list, so a query lands near the docs that share words."""

    WORDS = ["deserialisation", "credentials", "header", "pyyaml", "requests", "urllib3"]

    def __init__(self, key="kw"):
        self.cache_key = key

    def encode(self, texts, *, query):
        out = np.array([[w in t.lower() for w in self.WORDS] for t in texts], dtype=np.float32)
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


class ReverseScorer:
    cache_key = "reverse"

    def score(self, query, texts):
        return [float(i) for i in range(len(texts))]  # prefers the last candidate


def pipeline(**kwargs):
    return Pipeline(
        UNITS, embedders={"a": KeywordEmbedder("a"), "b": KeywordEmbedder("b")}, **kwargs
    )


# --- reading the dev questions ---


def write_lines(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_test_questions_are_dropped_as_the_file_is_read_and_abstain_ones_left_out(tmp_path):
    questions = [
        {"id": "a", "split": "dev", "type": "lookup", "template": "L1", "question": "qa",
         "answers_with": "ids"},
        {"id": "b", "split": "test", "type": "lookup", "template": "L1", "question": "qb",
         "answers_with": "ids"},
        {"id": "c", "split": "dev", "type": "abstain", "template": "T2", "question": "qc",
         "answers_with": "abstain"},
        {"id": "d", "split": "dev", "type": "abstain", "template": "T3", "question": "qd",
         "answers_with": "abstain"},
    ]  # fmt: skip
    empty = {"ghsa": [], "nvd": [], "kev": []}
    gold = [
        {"id": "a", "evidence": {**empty, "ghsa": ["GHSA-2222-2222-2222"]}},
        {"id": "b", "evidence": {**empty, "ghsa": ["GHSA-3333-3333-3333"]}},
        {"id": "c", "evidence": empty},
        {"id": "d", "evidence": {**empty, "nvd": ["CVE-2020-0001"]}},  # abstain, but has a record
    ]
    write_lines(tmp_path / "q.jsonl", questions)
    write_lines(tmp_path / "g.jsonl", gold)

    items, left_out = ladder.load_dev_items(tmp_path / "q.jsonl", tmp_path / "g.jsonl")

    assert [i.question_id for i in items] == ["a"]
    assert left_out == ["c", "d"]  # both should be declined, whether or not they have evidence


def test_a_ranking_is_scored_at_each_cut_off_with_set_questions_flagged_when_k_is_too_small():
    needed = frozenset(f"ghsa:G{i}" for i in range(6))
    item = ladder.Item("q", "version", "V2", "text", needed)

    row = ladder.score_ranking(item, [f"ghsa:G{i}" for i in range(6)])

    assert row["all@5"] is False and row["all@10"] is True and row["impossible@5"] is True
    assert row["recall@5"] == pytest.approx(5 / 6) and row["rr"] == 1.0


def test_kev_recall_is_reported_only_for_questions_that_need_a_kev_entry():
    plain = ladder.Item("q1", "lookup", "L1", "t", frozenset({"ghsa:G1"}))
    kev = ladder.Item("q2", "multihop", "A3", "t", frozenset({"ghsa:G1", "kev:CVE-1"}))

    rows = [ladder.score_ranking(plain, ["ghsa:G1"]), ladder.score_ranking(kev, ["ghsa:G1"])]
    summary = ladder.summarise(rows)

    assert rows[0]["kev_recall@10"] is None and rows[1]["kev_recall@10"] == 0.0
    assert summary["kev_recall@10"] == {"questions": 1, "mean": 0.0}
    assert summary["all@10"]["hits"] == 1 and summary["all@10"]["of"] == 2


# --- the adoption rule ---


def hits(wins, losses, same=20):
    candidate = [True] * wins + [False] * losses + [True] * same
    current = [False] * wins + [True] * losses + [True] * same
    return candidate, current


def test_six_wins_to_none_is_adopted_and_five_to_none_is_not():
    assert ladder.adopt(*hits(6, 0))["adopted"] is True
    assert ladder.adopt(*hits(5, 0))["adopted"] is False  # p = 0.0625


def test_a_net_gain_that_is_not_significant_is_not_adopted():
    result = ladder.adopt(*hits(7, 3))

    assert result["net"] == 4 and result["p"] > 0.05 and result["adopted"] is False


def test_a_rung_that_wins_and_loses_the_same_questions_changes_nothing():
    assert ladder.adopt(*hits(0, 0))["adopted"] is False
    assert ladder.adopt(*hits(4, 4))["net"] == 0


def row(all10, recall10):
    return {"all@10": all10, "recall@10": recall10}


def test_the_dense_fork_goes_to_more_full_hits_then_more_recall_then_the_smaller_model():
    assert ladder.pick_dense([row(True, 1)], [row(False, 1)]) == "a"
    assert ladder.pick_dense([row(False, 0.5)], [row(False, 0.9)]) == "b"
    assert ladder.pick_dense([row(False, 0.5)], [row(False, 0.5)]) == "b"  # tie: the smaller


# --- the pipeline ---


def test_each_rung_turns_on_one_more_part_and_a_spec_with_nothing_on_returns_nothing():
    p = pipeline()

    assert p.rank(Spec("none"), "pyyaml") == []
    assert p.rank(Spec("r0", bm25="body"), "credentials")[0] == "ghsa:GHSA-3333-3333-3333"
    assert p.rank(Spec("r2", dense="a"), "deserialisation")[0] == "ghsa:GHSA-2222-2222-2222"


def test_hybrid_joins_keyword_and_dense_rankings():
    p = pipeline()

    ranked = p.rank(Spec("r4", bm25="header", dense="a"), "pyyaml deserialisation")

    assert ranked[0] == "ghsa:GHSA-2222-2222-2222"
    assert set(ranked) <= {u.unit_id for u in UNITS}


def test_rerank_reorders_the_fused_candidates_and_the_filter_runs_after_it():
    p = pipeline(scorer=ReverseScorer())
    base = p.rank(
        Spec("r4", bm25="header", dense="a"), "pyyaml requests deserialisation credentials"
    )

    reranked = p.rank(
        Spec("r5", bm25="header", dense="a", rerank=True),
        "pyyaml requests deserialisation credentials",
    )
    filtered = p.rank(
        Spec("r6", bm25="header", dense="a", rerank=True, soft_filter=True),
        "GHSA-3333-3333-3333 deserialisation",
    )

    assert reranked == list(reversed(base))
    assert filtered[0] == "ghsa:GHSA-3333-3333-3333"


def test_split_docs_still_rank_unique_records():
    p = pipeline()

    ranked = p.rank(Spec("r7", bm25="header", split=True), "slow header parsing urllib3")

    assert ranked[0] == "ghsa:GHSA-4444-4444-4444"
    assert len(ranked) == len(set(ranked))


def test_decomposition_merges_the_sub_query_lists_into_one_ranking():
    calls = []

    def decomposer(question, run):
        calls.append((question, run))
        return ["credentials redirect", "deserialisation pyyaml"]

    p = pipeline(decomposer=decomposer)

    ranked = p.rank(Spec("r8", bm25="header", decompose=True), "two facts please", run=2)

    assert calls == [("two facts please", 2)]
    assert set(ranked[:2]) == {"ghsa:GHSA-3333-3333-3333", "ghsa:GHSA-2222-2222-2222"}
    assert len(ranked) <= DEPTH


def test_an_index_is_built_once_however_many_rungs_use_it():
    p = pipeline()

    p.rank(Spec("r1", bm25="header"), "pyyaml")
    p.rank(Spec("r4", bm25="header", dense="a"), "pyyaml")

    assert set(p.indexes) == {("header", False), ("a", False)}


# --- the script's two small helpers ---


def load_script():
    import importlib.util
    import sys
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "retrieval_ladder", Path("scripts/retrieval_ladder.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["retrieval_ladder"] = module
    spec.loader.exec_module(module)
    return module


def test_the_memo_scorer_asks_the_model_once_for_a_pair_it_has_seen():
    script = load_script()
    seen = []

    class Counting:
        cache_key = "c"

        def score(self, query, texts):
            seen.append(list(texts))
            return [float(len(t)) for t in texts]

    memo = script.MemoScorer(Counting())

    first = memo.score("q", ["aa", "b"])
    second = memo.score("q", ["b", "cccc"])

    assert first == [2.0, 1.0] and second == [1.0, 4.0]
    assert seen == [["aa", "b"], ["cccc"]]


def test_the_baseline_rows_count_what_a_package_filter_and_an_id_match_would_have_found():
    script = load_script()
    from advisor.retrieval.query import Hints

    pyyaml, both, none = (
        frozenset({"ghsa:GHSA-2222-2222-2222"}),
        frozenset({"ghsa:GHSA-2222-2222-2222", "nvd:CVE-2020-0001"}),
        frozenset({"ghsa:GHSA-3333-3333-3333"}),
    )
    items = [
        ladder.Item("1", "lookup", "L1", "pyyaml 5.1 flaws", pyyaml),
        ladder.Item("2", "lookup", "L1", "tell me about CVE-2020-0001", both),
        ladder.Item("3", "lookup", "L1", "a flaw with no names", none),
    ]

    result = script.baselines(Hints(UNITS), items)

    assert result["B0"] == {"all_in_whole_package": 1, "median_list_length": 0, "questions": 3}
    assert result["B1"] == {"coverage": 1, "all_in_exact_matches": 1, "questions": 3}
