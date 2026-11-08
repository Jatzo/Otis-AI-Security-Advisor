"""The live search on the replay page must find the same words as the real search does.

The ranking is only the real one if the words are. The expected words come from SQLite FTS5 itself,
dumped into tests/fixtures/search-tokens.json by scripts/build_search_index.py, so these tests need
no database and run in CI. The Node test in tests/js runs the page's own splitting code against
them. Rebuilding the files from the store skips where the store is not present.

Nothing here calls a model.
"""

import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from advisor.retrieval.bm25 import Bm25Index
from advisor.retrieval.units import build_units, whole_docs
from advisor.web.view import GITHUB, NVD

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "docs" / "demo" / "corpus.json"
TOKENS = ROOT / "tests" / "fixtures" / "search-tokens.json"

_loaded = importlib.util.spec_from_file_location(
    "build_search_index", ROOT / "scripts" / "build_search_index.py"
)
build_search_index = importlib.util.module_from_spec(_loaded)
sys.modules["build_search_index"] = build_search_index
_loaded.loader.exec_module(build_search_index)


def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


def test_the_page_splits_every_unit_into_the_words_fts5_finds():
    node = shutil.which("node")
    assert node, "Node is needed for this test. Install it, or add it to the CI job."
    files = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.js"))
    done = subprocess.run(  # noqa: S603 - Node, and test files from this repository
        [node, "--test", *files], capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-1000:]


def test_the_corpus_has_one_entry_per_shipped_unit_and_no_email_address():
    data = corpus()
    units = data["units"]
    ids = [u["id"] for u in units]
    assert ids == sorted(ids) and len(set(ids)) == len(ids) == 1174
    assert {s: sum(u["source"] == s for u in units) for s in ("ghsa", "kev", "nvd")} == {
        "ghsa": 588, "kev": 10, "nvd": 576,
    }  # fmt: skip
    for unit in units:
        assert set(unit) == {"id", "source", "header", "body", "url"}
        assert unit["id"].startswith(unit["source"] + ":")
        assert unit["url"].startswith((GITHUB, NVD))
        text = unit["header"] + unit["body"]
        assert not build_search_index.EMAIL.search(text), unit["id"]
        assert not build_search_index.CREDENTIAL.search(text), unit["id"]


def test_scrub_replaces_emails_and_quoted_example_credentials_and_leaves_other_text_alone():
    scrub = build_search_index.scrub
    assert (
        scrub("Credits: A. Person (a.person@example.com)") == "Credits: A. Person ([email removed])"
    )
    assert scrub('password = "hunter2hunter2"') == 'password = "[example value removed]"'
    assert scrub("apiKey: 'abcdefghijkl'") == "apiKey: '[example value removed]'"
    for untouched in (
        'token = "short"',
        "reset the password for lodash@4.17.21 or spring-webmvc@5.2.20.RELEASE",
        "secret scanning is on by default",
    ):
        assert scrub(untouched) == untouched


def test_the_fold_table_holds_only_non_ascii_characters_and_text_or_null():
    fold = corpus()["fold"]
    assert fold and all(len(c) == 1 and ord(c) > 127 for c in fold)
    assert all(v is None or isinstance(v, str) for v in fold.values())


def test_the_token_fixture_has_a_count_and_a_hash_for_every_unit():
    expected = json.loads(TOKENS.read_text(encoding="utf-8"))
    assert set(expected) == {u["id"] for u in corpus()["units"]}
    for count, digest in expected.values():
        assert isinstance(count, int) and count > 0
        assert len(digest) == 64


def test_the_page_rule_for_ascii_is_what_fts5_does_with_each_ascii_character():
    characters = [chr(i) for i in range(1, 128)]
    found = build_search_index.probes(characters)
    for character in characters:
        if character.isascii() and character.isalnum():
            expected = [f"q{character.lower()}q"]
        else:
            expected = ["q", "q"]
        assert found[character] == expected, repr(character)


def test_the_build_script_uses_the_tokenizer_the_real_search_uses():
    wanted = "unicode61 remove_diacritics 2"
    real = (ROOT / "src" / "advisor" / "retrieval" / "bm25.py").read_text(encoding="utf-8")
    assert wanted in real and wanted in build_search_index.CREATE_PROBE


def test_the_replacements_move_the_top_ten_of_exactly_two_dev_questions():
    """A record that loses an email or a sample password has fewer words, which can swap two
    records that score almost the same at the edge of the top 10. This pins the two that move
    (docs/live-search-plan.md), so a change in the data or the rule shows up."""
    store = ROOT / "data" / "advisor.db"
    if not store.exists():
        pytest.skip("The local store is not here.")
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    original = Bm25Index(whole_docs(build_units(db)), with_header=True)
    published = Bm25Index(build_search_index.published_docs(db), with_header=True)
    lines = (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    dev = [q for q in map(json.loads, lines) if q["split"] == "dev"]
    moved = [
        q["id"]
        for q in dev
        if [d for d, _ in original.search(q["question"], 100)[:10]]
        != [d for d, _ in published.search(q["question"], 100)[:10]]
    ]
    assert len(dev) == 40
    assert sorted(moved) == ["ab-005", "vr-001"]


def test_rebuilding_from_the_local_store_reproduces_the_committed_files(tmp_path, monkeypatch):
    store = ROOT / "data" / "advisor.db"
    if not store.exists():
        pytest.skip("The local store is not here, so the files cannot be rebuilt.")
    corpus_out, tokens_out = tmp_path / "corpus.json", tmp_path / "tokens.json"
    monkeypatch.setattr(
        sys, "argv",
        ["build_search_index.py", "--corpus", str(corpus_out), "--tokens", str(tokens_out)],
    )  # fmt: skip
    assert build_search_index.main() == 0
    assert corpus_out.read_text(encoding="utf-8") == CORPUS.read_text(encoding="utf-8")
    assert tokens_out.read_text(encoding="utf-8") == TOKENS.read_text(encoding="utf-8")
