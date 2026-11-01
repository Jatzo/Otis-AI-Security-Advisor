"""Retrieval over a small synthetic store. No model is loaded and nothing is downloaded: dense
search and reranking run against fakes."""

import hashlib
import json
import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from advisor import store
from advisor.ingest import raw
from advisor.retrieval import bm25, decompose, dense, metrics, query, rerank, units
from advisor.retrieval.fusion import reciprocal_rank_fusion
from advisor.stats import mcnemar_p, wilson

VECTOR = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
FILLER = "The library keeps a list of values and checks each one in turn. " * 60


def ghsa(record_id, package, aliases, summary, details, events, severity="HIGH"):
    return {
        "id": record_id,
        "aliases": aliases,
        "summary": summary,
        "details": details,
        "published": "2021-04-08T19:24:04Z",
        "database_specific": {"severity": severity},
        "severity": [{"type": "CVSS_V3", "score": VECTOR}],
        "affected": [
            {
                "package": {"ecosystem": "PyPI", "name": package},
                "ranges": [{"type": "ECOSYSTEM", "events": events}],
            }
        ],
    }


MANY_RANGES = [e for n in range(8) for e in ({"introduced": f"{n}.0"}, {"fixed": f"{n}.5"})]
RECORDS = [
    ghsa("GHSA-2222-2222-2222", "pyyaml", ["CVE-2020-0001"], "Example deserialisation flaw",
         "Loading untrusted input runs code.", [{"introduced": "5.1"}, {"fixed": "5.2"}]),
    ghsa("GHSA-3333-3333-3333", "requests", ["CVE-2020-0002"], "Credentials leak on redirect",
         FILLER + " The marker zebrafinch appears only at the very end.", MANY_RANGES),
    ghsa("GHSA-4444-4444-4444", "urllib3", [], "Header parsing slowdown",
         "A long header makes the parser slow.", [{"introduced": "1.0"}, {"last_affected": "1.4"}]),
]  # fmt: skip
NVD = {
    "id": "CVE-2020-0001",
    "vulnStatus": "Analyzed",
    "published": "2021-04-09T00:00:00Z",
    "descriptions": [{"lang": "en", "value": "NVD describes the pyyaml flaw."}],
    "metrics": {"cvssMetricV31": [{"type": "Primary", "cvssData": {"vectorString": VECTOR}}]},
    "configurations": [
        {"nodes": [{"cpeMatch": [{"criteria": "cpe:2.3:a:pyyaml:pyyaml:*:*:*:*:*:*:*:*",
                                  "vulnerable": True}]}]}
    ],
}  # fmt: skip
KEV = {
    "catalogVersion": "2026.10.30",
    "vulnerabilities": [
        {"cveID": "CVE-2020-0002", "vendorProject": "Python", "product": "requests",
         "vulnerabilityName": "Requests credential leak", "dateAdded": "2022-01-01",
         "knownRansomwareCampaignUse": "Unknown"},
        {"cveID": "CVE-2099-0001", "vendorProject": "Other", "product": "thing",
         "vulnerabilityName": "Not in the corpus", "dateAdded": "2022-01-01"},
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def all_units(tmp_path_factory):
    root = tmp_path_factory.mktemp("snapshot")
    for record in RECORDS:
        raw.write_record(root / "raw" / "osv", record["id"], record)
    raw.write_record(root / "raw" / "nvd", NVD["id"], NVD)
    raw.write_record(root / "raw" / "kev", "known_exploited_vulnerabilities", KEV)
    store.build(root / "raw", root / "advisor.db")
    db = sqlite3.connect(root / "advisor.db")
    yield units.build_units(db)
    db.close()


def by_id(all_units):
    return {u.unit_id: u for u in all_units}


# --- units ---


def test_units_are_namespaced_ordered_and_kev_keeps_only_corpus_cves(all_units):
    assert [u.unit_id for u in all_units] == [
        "ghsa:GHSA-2222-2222-2222", "ghsa:GHSA-3333-3333-3333", "ghsa:GHSA-4444-4444-4444",
        "kev:CVE-2020-0002", "nvd:CVE-2020-0001",
    ]  # fmt: skip


def test_each_header_holds_only_its_own_records_facts(all_units):
    found = by_id(all_units)
    github, nvd, kev = (found[i] for i in ("ghsa:GHSA-2222-2222-2222", "nvd:CVE-2020-0001",
                                           "kev:CVE-2020-0002"))  # fmt: skip

    assert "Severity HIGH" in github.header and "KEV" not in github.header
    assert "Status Analyzed" in nvd.header and "Severity" not in nvd.header
    assert "pyyaml:pyyaml" in nvd.header
    assert "Vendor Python" in kev.header and "CVSS" not in kev.header


def test_a_header_is_capped_and_says_how_many_ranges_it_left_out(all_units):
    header = by_id(all_units)["ghsa:GHSA-3333-3333-3333"].header

    assert len(header) <= units.HEADER_LIMIT
    assert "and 2 more" in header and "CVE-2020-0002" in header


def test_range_text_names_the_fix_the_last_affected_version_or_neither():
    assert units.span_text("5.1", "5.2", None) == "from 5.1 before 5.2"
    assert units.span_text("1.0", None, "1.4") == "from 1.0 through 1.4"
    assert units.span_text(None, None, None) == "from the first version, no fix listed"


def test_package_metadata_follows_a_cve_across_sources_for_the_filter_only(all_units):
    found = by_id(all_units)

    assert found["nvd:CVE-2020-0001"].packages == {"pyyaml"}
    assert found["kev:CVE-2020-0002"].packages == {"requests"}
    assert "pyyaml" not in found["nvd:CVE-2020-0001"].header.split("Products")[0]


def test_splitting_cuts_only_long_records_repeats_the_header_and_overlaps(all_units):
    docs = units.split_docs(all_units)
    pieces = [d for d in docs if d.unit_id == "ghsa:GHSA-3333-3333-3333"]

    assert len(pieces) > 1 and {d.header for d in pieces} == {pieces[0].header}
    assert pieces[0].body[-units.OVERLAP :] == pieces[1].body[: units.OVERLAP]
    assert "zebrafinch" in pieces[-1].body
    assert [d.doc_id for d in docs if d.unit_id == "ghsa:GHSA-2222-2222-2222"] == [
        "ghsa:GHSA-2222-2222-2222"
    ]


def test_collapse_counts_records_not_pieces(all_units):
    docs = units.split_docs(all_units)
    ids = ["ghsa:GHSA-3333-3333-3333#0", "ghsa:GHSA-3333-3333-3333#1", "kev:CVE-2020-0002"]

    assert units.collapse(ids, docs) == ["ghsa:GHSA-3333-3333-3333", "kev:CVE-2020-0002"]


# --- keyword search ---


def test_keyword_search_finds_a_word_and_ranks_the_better_match_first(all_units):
    index = bm25.Bm25Index(units.whole_docs(all_units), with_header=True)

    assert index.search("deserialisation flaw")[0][0] == "ghsa:GHSA-2222-2222-2222"
    assert index.search("zebrafinch")[0][0] == "ghsa:GHSA-3333-3333-3333"


def test_an_id_is_searched_as_a_phrase_so_it_finds_that_advisory(all_units):
    index = bm25.Bm25Index(units.whole_docs(all_units), with_header=True)

    assert index.search("Tell me about GHSA-4444-4444-4444")[0][0] == "ghsa:GHSA-4444-4444-4444"


def test_the_header_makes_a_package_name_findable_that_the_body_never_says(all_units):
    docs = units.whole_docs(all_units)

    assert bm25.Bm25Index(docs, with_header=False).search("urllib3") == []
    assert bm25.Bm25Index(docs, with_header=True).search("urllib3")[0][0].endswith("4444-4444")


@pytest.mark.parametrize(
    "hostile",
    [
        '"',
        "a - b",
        "title:secret",
        "star*",
        "x AND y OR NOT z",
        "NEAR(a b)",
        "'; DROP TABLE docs;--",
        "",
    ],
)
def test_hostile_query_text_never_reaches_fts5_as_syntax(all_units, hostile):
    index = bm25.Bm25Index(units.whole_docs(all_units), with_header=True)

    assert isinstance(index.search(hostile), list)


def test_a_very_long_query_is_cut(all_units):
    expression = bm25.match_expression(" ".join(f"word{i}" for i in range(500)))

    assert expression.count(" OR ") == bm25.MAX_TERMS - 1


# --- fusion ---


def test_fusion_puts_what_both_lists_rank_well_first_and_breaks_ties_by_id():
    assert reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]]) == ["a", "b", "c", "d"]
    assert reciprocal_rank_fusion([["z"], ["y"]]) == ["y", "z"]


def test_fusion_rewards_agreement_over_one_high_rank():
    assert reciprocal_rank_fusion([["x", "a", "b"], ["y", "a", "b"]])[0] == "a"


# --- what a question names ---


def test_ids_are_read_from_a_question_in_any_case():
    found = query.named_ids("Is cve-2021-44228 fixed, and what about GHSA-2222-3333-4444?")

    assert found == {"CVE-2021-44228", "GHSA-2222-3333-4444"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Which advisories affect requests 2.25.0?", {"requests"}),
        ("Which flaw lets requests made over HTTP/2 skip the proxy?", set()),
        ("The requests library leaks headers", {"requests"}),
        ("Which advisories apply to ws 1.1.5?", {"ws"}),
        ("What does the news say?", set()),
        ("Which versions of django-sentinel-core are affected?", set()),
        ("Which versions of aiohttp-shield are affected?", set()),
        ("Does log4j-core 2.3.1 have any?", {"org.apache.logging.log4j:log4j-core"}),
        ("org.springframework:spring-webmvc 5.2.20.RELEASE", {"org.springframework:spring-webmvc"}),
        ("A Django flaw in Flask and Jinja2 templates", {"django", "flask", "jinja2"}),
    ],
)
def test_a_package_counts_only_when_the_question_really_names_it(text, expected):
    assert query.named_packages(text) == expected


def test_a_cve_in_a_question_reaches_every_unit_that_names_it(all_units):
    hints = query.Hints(all_units)

    assert hints.exact_matches("What about CVE-2020-0001?") == [
        "ghsa:GHSA-2222-2222-2222", "nvd:CVE-2020-0001",
    ]  # fmt: skip
    assert hints.exact_matches("No id here") == []


def test_the_whole_package_row_lists_every_unit_of_the_named_package(all_units):
    hints = query.Hints(all_units)

    assert hints.whole_packages("requests 2.0") == [
        "ghsa:GHSA-3333-3333-3333", "kev:CVE-2020-0002",
    ]  # fmt: skip


def test_the_soft_filter_orders_exact_matches_then_the_package_then_the_rest(all_units):
    hints = query.Hints(all_units)
    ranked = ["ghsa:GHSA-4444-4444-4444", "nvd:CVE-2020-0001", "ghsa:GHSA-3333-3333-3333",
              "ghsa:GHSA-2222-2222-2222"]  # fmt: skip

    result = hints.soft_filter(ranked, "pyyaml GHSA-3333-3333-3333")

    assert result == ["ghsa:GHSA-3333-3333-3333", "nvd:CVE-2020-0001", "ghsa:GHSA-2222-2222-2222",
                      "ghsa:GHSA-4444-4444-4444"]  # fmt: skip


def test_the_soft_filter_changes_nothing_when_the_question_names_nothing(all_units):
    hints = query.Hints(all_units)
    ranked = ["ghsa:GHSA-4444-4444-4444", "ghsa:GHSA-2222-2222-2222"]

    assert hints.soft_filter(ranked, "a flaw that is slow") == ranked


def test_the_filter_never_reads_a_version(all_units):
    hints = query.Hints(all_units)
    ranked = ["ghsa:GHSA-4444-4444-4444", "ghsa:GHSA-2222-2222-2222"]

    assert hints.soft_filter(ranked, "pyyaml 99.0") == hints.soft_filter(ranked, "pyyaml 5.1")


# --- dense search ---


class FakeEmbedder:
    """A bag of hashed words, so texts that share words score higher. Counts its own calls."""

    def __init__(self, key="fake-1"):
        self.cache_key = key
        self.calls = 0

    def encode(self, texts, *, query):
        self.calls += 1
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.lower().split():
                out[row, int(hashlib.sha256(word.encode()).hexdigest(), 16) % 64] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1, norms)


def test_dense_search_returns_the_closest_doc_first(all_units):
    index = dense.DenseIndex(units.whole_docs(all_units), FakeEmbedder())

    assert index.search("deserialisation flaw loading untrusted input")[0][0] == (
        "ghsa:GHSA-2222-2222-2222"
    )


def test_equal_scores_break_by_doc_id():
    docs = [units.Doc(i, i, "h", "same words") for i in ("a", "b", "c")]

    index = dense.DenseIndex(docs, FakeEmbedder())

    assert [d for d, _ in index.search("same words")] == ["a", "b", "c"]


def test_embeddings_are_cached_by_model_and_text_and_rebuilt_when_either_changes(
    all_units, tmp_path
):
    docs = units.whole_docs(all_units)
    first, same, other_model = FakeEmbedder(), FakeEmbedder(), FakeEmbedder("fake-2")

    dense.DenseIndex(docs, first, tmp_path)
    dense.DenseIndex(docs, same, tmp_path)
    dense.DenseIndex(docs, other_model, tmp_path)
    dense.DenseIndex(docs[:-1], FakeEmbedder(), tmp_path)

    assert (first.calls, same.calls, other_model.calls) == (1, 0, 1)
    assert len(list(tmp_path.glob("*.npy"))) == 3


# --- reranking ---


class FakeScorer:
    cache_key = "fake"

    def __init__(self, scores):
        self.scores = scores

    def score(self, query_text, texts):
        return [self.scores[t] for t in texts]


def test_rerank_reorders_only_the_head_and_leaves_the_tail():
    scorer = FakeScorer({"a": 0.1, "b": 0.9, "c": 0.5})

    assert rerank.rerank(["a", "b", "c", "d", "e"], "q", lambda u: u, scorer, top=3) == [
        "b", "c", "a", "d", "e",
    ]  # fmt: skip


def test_rerank_keeps_the_earlier_order_for_equal_scores():
    scorer = FakeScorer({"a": 1.0, "b": 1.0, "c": 1.0})

    assert rerank.rerank(["c", "a", "b"], "q", lambda u: u, scorer, top=3) == ["c", "a", "b"]


# --- scoring a ranking ---


GOLD = {"evidence": {"ghsa": ["GHSA-2222-2222-2222"], "nvd": ["CVE-2020-0001"], "kev": []}}


def test_evidence_is_namespaced_so_an_nvd_hit_does_not_stand_in_for_an_advisory():
    needed = metrics.evidence_ids(GOLD)

    assert needed == {"ghsa:GHSA-2222-2222-2222", "nvd:CVE-2020-0001"}
    assert metrics.recall_at(["nvd:CVE-2020-0001", "x"], needed, 2) == 0.5
    assert not metrics.all_evidence_at(["nvd:CVE-2020-0001", "x"], needed, 2)


def test_all_evidence_needs_every_record_inside_the_cut_off():
    needed = metrics.evidence_ids(GOLD)
    ranked = ["x", "ghsa:GHSA-2222-2222-2222", "y", "nvd:CVE-2020-0001"]

    assert not metrics.all_evidence_at(ranked, needed, 3)
    assert metrics.all_evidence_at(ranked, needed, 4)
    assert metrics.reciprocal_rank(ranked, needed) == 0.5
    assert metrics.reciprocal_rank(["x"], needed) == 0.0


def test_interval_and_exact_test_match_known_values():
    low, high = wilson(17, 22)

    assert (round(low, 2), round(high, 2)) == (0.57, 0.90)
    assert mcnemar_p(0, 6) == pytest.approx(0.03125)
    assert mcnemar_p(0, 5) == pytest.approx(0.0625)


# --- decomposition ---


def reply(text, tokens_in=500, tokens_out=100):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out),
        model="claude-sonnet-5-5",
    )


class FakeClient:
    def __init__(self, text):
        self.requests = []
        self.text = text
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.requests.append(request)
        return reply(self.text)


def test_decomposition_is_asked_once_costed_and_then_read_from_the_saved_file(tmp_path):
    client = FakeClient('Sure: {"queries": ["pyyaml 5.1 advisories", " ", "pyyaml fixed 5.2"]}')
    path = tmp_path / "decompositions.json"

    first, cost = decompose.decompose("Which pyyaml 5.1 flaws?", 1, client, path)
    second, again = decompose.decompose("Which pyyaml 5.1 flaws?", 1, client, path)
    other_run, _ = decompose.decompose("Which pyyaml 5.1 flaws?", 2, client, path)

    assert first == second == other_run == ["pyyaml 5.1 advisories", "pyyaml fixed 5.2"]
    assert cost == pytest.approx(0.002) and again == 0.0
    assert len(client.requests) == 2  # run 1 once, run 2 once


def test_decomposition_settings_are_fixed_and_carry_no_sampling_or_fallback(tmp_path):
    client = FakeClient('{"queries": ["q"]}')

    decompose.decompose("q", 1, client, tmp_path / "d.json")

    (request,) = client.requests
    assert request["model"] == "claude-sonnet-5-5" and request["max_tokens"] == 2000
    assert request["output_config"] == {"effort": "medium"}
    assert not {"temperature", "top_p", "top_k", "fallbacks", "betas", "tools"} & set(request)


@pytest.mark.parametrize("text", ["no json", '{"queries": 5}', '{"other": []}', '{"queries": []}'])
def test_an_unreadable_reply_falls_back_to_the_question_itself(text):
    assert decompose.parse_queries(text, "the question") == ["the question"]


def test_at_most_four_queries_are_kept():
    text = json.dumps({"queries": [f"q{i}" for i in range(9)]})

    assert decompose.parse_queries(text, "x") == ["q0", "q1", "q2", "q3"]
