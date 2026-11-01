"""The rungs of the ladder, as one configurable pipeline.

A Spec says which parts are on. The same Pipeline serves every rung, so a rung differs from the
one below it by the parts it switches on and nothing else.
"""

from collections.abc import Callable
from dataclasses import dataclass

from advisor.retrieval.bm25 import Bm25Index
from advisor.retrieval.dense import DenseIndex, Embedder
from advisor.retrieval.fusion import reciprocal_rank_fusion
from advisor.retrieval.query import Hints
from advisor.retrieval.rerank import Scorer, rerank
from advisor.retrieval.units import Unit, collapse, split_docs, whole_docs

DEPTH = 100  # how many units each stage hands on
RERANK_TOP = 30
RRF_K = 60
SPLIT_OVERFETCH = 4  # split units fill the list with pieces of one record, so fetch more pieces


@dataclass(frozen=True)
class Spec:
    name: str
    bm25: str | None = None  # "body" or "header"
    dense: str | None = None  # the key of an embedder
    rerank: bool = False
    soft_filter: bool = False
    split: bool = False
    decompose: bool = False


class Pipeline:
    def __init__(
        self,
        units: list[Unit],
        embedders: dict[str, Embedder] | None = None,
        scorer: Scorer | None = None,
        decomposer: Callable[[str, int], list[str]] | None = None,
        cache_dir=None,
    ) -> None:
        self.units = units
        self.hints = Hints(units)
        self.text_of = {d.unit_id: d.text for d in whole_docs(units)}
        self.embedders = embedders or {}
        self.scorer = scorer
        self.decomposer = decomposer
        self.cache_dir = cache_dir
        self.docs = {False: whole_docs(units), True: split_docs(units)}
        self.indexes: dict[tuple, object] = {}

    def index(self, kind: str, split: bool):
        """Builds an index the first time a rung asks for it."""
        key = (kind, split)
        if key not in self.indexes:
            if kind in ("body", "header"):
                self.indexes[key] = Bm25Index(self.docs[split], with_header=kind == "header")
            else:
                self.indexes[key] = DenseIndex(
                    self.docs[split], self.embedders[kind], self.cache_dir
                )
        return self.indexes[key]

    def rank_one(self, spec: Spec, query: str) -> list[str]:
        fetch = DEPTH * (SPLIT_OVERFETCH if spec.split else 1)
        lists = []
        for kind in (spec.bm25, spec.dense):
            if kind:
                hits = self.index(kind, spec.split).search(query, fetch)
                lists.append(collapse([doc_id for doc_id, _ in hits], self.docs[spec.split]))
        if not lists:
            return []
        ranked = lists[0] if len(lists) == 1 else reciprocal_rank_fusion(lists, RRF_K)
        ranked = ranked[:DEPTH]
        if spec.rerank:
            ranked = rerank(ranked, query, self.text_of.__getitem__, self.scorer, RERANK_TOP)
        if spec.soft_filter:
            ranked = self.hints.soft_filter(ranked, query)
        return ranked

    def rank(self, spec: Spec, query: str, run: int = 1) -> list[str]:
        """The ranked unit ids for a question. With decomposition, each sub-query is ranked on its
        own and the lists are merged into one ranking before anything is cut."""
        queries = self.decomposer(query, run) if spec.decompose else [query]
        lists = [self.rank_one(spec, q) for q in queries]
        if len(lists) == 1:
            return lists[0]
        return reciprocal_rank_fusion(lists, RRF_K)[:DEPTH]
