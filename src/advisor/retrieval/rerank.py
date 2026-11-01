"""Reranking: a cross-encoder reads the question and one candidate together."""

from collections.abc import Callable
from typing import Protocol


class Scorer(Protocol):
    cache_key: str

    def score(self, query: str, texts: list[str]) -> list[float]:
        """One relevance score per text, higher is better."""


class CrossEncoderScorer:
    def __init__(self, model: str, revision: str, max_length: int = 512) -> None:
        import sentence_transformers  # noqa: PLC0415

        self.model = sentence_transformers.CrossEncoder(
            model, revision=revision, max_length=max_length
        )
        self.cache_key = f"{model}@{revision}|{max_length}"

    def score(self, query: str, texts: list[str]) -> list[float]:
        return [float(s) for s in self.model.predict([(query, t) for t in texts], batch_size=8)]


def rerank(
    ranked: list[str], query: str, text_of: Callable[[str], str], scorer: Scorer, top: int = 30
) -> list[str]:
    """Reorders the first `top` candidates by the scorer. Equal scores keep their earlier order.
    Everything after them stays where it was."""
    head, tail = ranked[:top], ranked[top:]
    scores = scorer.score(query, [text_of(unit_id) for unit_id in head])
    order = sorted(range(len(head)), key=lambda i: (-scores[i], i))
    return [head[i] for i in order] + tail
