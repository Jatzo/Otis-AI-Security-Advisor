"""Keyword search over the docs, with SQLite FTS5.

Queries come from users and from the model, so they are never passed to FTS5 as written: only
letters and digits survive, each word is quoted, and a long query is cut. Hyphenated IDs are
searched as phrases, so GHSA-aaaa-bbbb-cccc finds that advisory and not every advisory with
"aaaa" somewhere in it.
"""

import re
import sqlite3

from advisor.retrieval.units import Doc

WORDS = re.compile(r"[A-Za-z0-9]+")
IDS = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}|CVE-\d{4}-\d{4,}", re.IGNORECASE)
MAX_TERMS = 64


def match_expression(query: str) -> str:
    """An FTS5 query that matches any word or any ID phrase in the text, and nothing else."""
    terms = [f'"{found.replace("-", " ")}"' for found in IDS.findall(query)]
    seen = set()
    for word in WORDS.findall(query):
        if word.lower() not in seen:
            seen.add(word.lower())
            terms.append(f'"{word}"')
    return " OR ".join(terms[:MAX_TERMS])


class Bm25Index:
    def __init__(self, docs: list[Doc], with_header: bool) -> None:
        self.db = sqlite3.connect(":memory:")
        self.db.execute(
            "CREATE VIRTUAL TABLE docs USING fts5(doc_id UNINDEXED, text,"
            " tokenize = 'unicode61 remove_diacritics 2')"
        )
        self.db.executemany(
            "INSERT INTO docs (doc_id, text) VALUES (?, ?)",
            [(d.doc_id, d.text if with_header else d.body) for d in docs],
        )

    def search(self, query: str, limit: int = 100) -> list[tuple[str, float]]:
        """Best first. FTS5's bm25() is lower for better matches, so the score is negated."""
        expression = match_expression(query)
        if not expression:
            return []
        rows = self.db.execute(
            "SELECT doc_id, bm25(docs) AS rank FROM docs WHERE docs MATCH ?"
            " ORDER BY rank, doc_id LIMIT ?",
            (expression, limit),
        ).fetchall()
        return [(doc_id, -rank) for doc_id, rank in rows]
