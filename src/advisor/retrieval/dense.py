"""Dense search: an embedding model and an exact cosine scan. No vector database: the corpus
is a few thousand texts."""

import hashlib
from pathlib import Path
from typing import Protocol

import numpy as np

from advisor.retrieval.units import Doc


class Embedder(Protocol):
    cache_key: str  # model, revision and library versions: anything that changes a vector

    def encode(self, texts: list[str], *, query: bool) -> np.ndarray:
        """Unit-length float32 vectors, one row per text."""


class SentenceTransformerEmbedder:
    """A sentence-transformers model. The library is imported only here, so tests and CI never
    load torch."""

    def __init__(
        self,
        model: str,
        revision: str,
        query_prefix: str,
        max_seq_length: int,
        padding_side: str | None = None,
    ) -> None:
        import sentence_transformers  # noqa: PLC0415

        options = {"padding_side": padding_side} if padding_side else {}
        self.model = sentence_transformers.SentenceTransformer(
            model, revision=revision, tokenizer_kwargs=options
        )
        self.model.max_seq_length = max_seq_length
        self.query_prefix = query_prefix
        self.cache_key = (
            f"{model}@{revision}|{max_seq_length}|{query_prefix}"
            f"|st{sentence_transformers.__version__}"
        )

    def encode(self, texts: list[str], *, query: bool) -> np.ndarray:
        prefixed = [self.query_prefix + t for t in texts] if query else texts
        vectors = self.model.encode(
            prefixed, batch_size=16, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


class DenseIndex:
    def __init__(self, docs: list[Doc], embedder: Embedder, cache_dir: Path | None = None) -> None:
        self.doc_ids = [d.doc_id for d in docs]
        self.embedder = embedder
        self.matrix = self.load_or_embed([d.text for d in docs], cache_dir)

    def load_or_embed(self, texts: list[str], cache_dir: Path | None) -> np.ndarray:
        digest = hashlib.sha256(self.embedder.cache_key.encode())
        for text in texts:
            digest.update(hashlib.sha256(text.encode()).digest())
        path = cache_dir / f"{digest.hexdigest()}.npy" if cache_dir else None
        if path and path.exists():
            return np.load(path)
        matrix = self.embedder.encode(texts, query=False)
        if path:
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.save(path, matrix)
        return matrix

    def search(self, query: str, limit: int = 100) -> list[tuple[str, float]]:
        """Best first. Docs are held in doc id order, so equal scores break by id."""
        scores = self.matrix @ self.embedder.encode([query], query=True)[0]
        order = np.lexsort((np.arange(len(scores)), -scores))[:limit]
        return [(self.doc_ids[i], float(scores[i])) for i in order]
