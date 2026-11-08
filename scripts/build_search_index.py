"""Builds the files behind the live search on the replay page.

It writes two files from the local store, with no model call and no key:

  docs/demo/corpus.json
      every unit's text, as it is published, and the fold table the page needs to split that
      text into the same words SQLite does
  tests/fixtures/search-tokens.json
      for each unit, how many words SQLite FTS5 finds in it and a hash of them, so the page's
      splitting is checked without the store

Email addresses (with the rule the replay build uses) and quoted example credentials are replaced
first, so the text published is the text indexed here. The words come from the real FTS5 index
over that text, not from a copy of its rules. docs/live-search-plan.md says why.

Usage:
    python scripts/build_search_index.py
"""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from build_replay import EMAIL  # noqa: E402

from advisor.generation.reading import normal_id  # noqa: E402
from advisor.retrieval.bm25 import Bm25Index  # noqa: E402
from advisor.retrieval.units import Doc, build_units, whole_docs  # noqa: E402
from advisor.web.view import link_for  # noqa: E402

CORPUS = ROOT / "docs" / "demo" / "corpus.json"
TOKENS = ROOT / "tests" / "fixtures" / "search-tokens.json"
PROBE = "q"  # a letter put either side of a character, to see what SQLite does with it
# Fixed statements, so no SQL is built from a variable. The tokenizer is the one in
# src/advisor/retrieval/bm25.py, and a test holds the two to the same string.
CREATE_PROBE = (
    "CREATE VIRTUAL TABLE probe USING fts5(text, tokenize = 'unicode61 remove_diacritics 2')"
)
VOCAB = {
    "docs": "CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main, docs, 'instance')",
    "probe": "CREATE VIRTUAL TABLE temp.vocab USING fts5vocab(main, probe, 'instance')",
}


# Example code in an advisory often sets a password or key to a sample value. The page has no use
# for the value, and a secret scanner cannot tell it from a real one, so it is replaced. The name
# and the quotes stay, so the line still reads as code.
CREDENTIAL = re.compile(
    r"((?:api[_-]?key|secret|token|passw(?:or)?d)\w*[\"']?\s*[:=]\s*[\"'])[^\"'\s]{12,}([\"'])",
    re.IGNORECASE,
)


def scrub(text: str) -> str:
    """Email addresses and quoted example credentials replaced, as the page publishes the text."""
    return CREDENTIAL.sub(r"\1[example value removed]\2", EMAIL.sub("[email removed]", text))


def published_docs(db: sqlite3.Connection) -> list[Doc]:
    """The documents as the page publishes them: the units, with email addresses replaced."""
    return [
        Doc(d.doc_id, d.unit_id, scrub(d.header), scrub(d.body))
        for d in whole_docs(build_units(db))
    ]


def instances(db: sqlite3.Connection, table: str) -> dict[int, list[str]]:
    """Every word SQLite found in each row of a full-text table, in order, by row number."""
    db.execute(VOCAB[table])
    try:
        found: dict[int, list[str]] = {}
        rows = db.execute('SELECT doc, term FROM temp.vocab ORDER BY doc, "offset"')
        for row, term in rows:
            found.setdefault(row, []).append(term)
        return found
    finally:
        db.execute("DROP TABLE temp.vocab")


def tokens_of(docs: list[Doc]) -> dict[str, list[str]]:
    """The words FTS5 finds in each document of the real index, by doc id."""
    index = Bm25Index(docs, with_header=True)
    by_row = instances(index.db, "docs")
    ids = dict(index.db.execute("SELECT rowid, doc_id FROM docs"))
    return {ids[row]: by_row.get(row, []) for row in ids}


def probes(characters: list[str]) -> dict[str, list[str]]:
    """What FTS5 makes of each character when it sits between two letters."""
    db = sqlite3.connect(":memory:")
    db.execute(CREATE_PROBE)
    db.executemany(
        "INSERT INTO probe (rowid, text) VALUES (?, ?)",
        [(i, f"{PROBE}{c}{PROBE}") for i, c in enumerate(characters, start=1)],
    )
    by_row = instances(db, "probe")
    return {c: by_row.get(i, []) for i, c in enumerate(characters, start=1)}


def fold_table(docs: list[Doc]) -> dict[str, str | None]:
    """For each non-ASCII character in the corpus: the text it becomes inside a word (empty when
    it is a diacritic that is dropped), or None when it ends a word."""
    characters = sorted({c for d in docs for c in d.text if ord(c) > 127})
    table: dict[str, str | None] = {}
    for character, words in probes(characters).items():
        if words == [PROBE, PROBE]:
            table[character] = None
        elif len(words) == 1 and words[0].startswith(PROBE) and words[0].endswith(PROBE):
            table[character] = words[0][1:-1]
        else:
            raise SystemExit(f"Unexpected tokens {words!r} for U+{ord(character):04X}.")
    return table


def fingerprint(tokens: list[str]) -> str:
    return hashlib.sha256("\n".join(tokens).encode("utf-8")).hexdigest()


def corpus_file(docs: list[Doc], fold: dict[str, str | None]) -> str:
    units = [
        {
            "id": d.doc_id, "source": d.doc_id.split(":", 1)[0], "header": d.header,
            "body": d.body, "url": link_for(normal_id(d.doc_id.split(":", 1)[1]))["url"],
        }
        for d in docs
    ]  # fmt: skip
    data = {"fold": fold, "units": units}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def token_file(tokens: dict[str, list[str]]) -> str:
    data = {doc_id: [len(words), fingerprint(words)] for doc_id, words in tokens.items()}
    return json.dumps(data, separators=(",", ":"), sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "data" / "advisor.db"))
    parser.add_argument("--corpus", default=str(CORPUS))
    parser.add_argument("--tokens", default=str(TOKENS))
    args = parser.parse_args()
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    docs = published_docs(db)
    corpus = corpus_file(docs, fold_table(docs))
    tokens = token_file(tokens_of(docs))
    for path, text in ((args.corpus, corpus), (args.tokens, tokens)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8", newline="\n")
        print(f"Wrote {path} ({len(text.encode('utf-8')) / 1024:.0f} KB).")
    print(f"{len(docs)} units.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
