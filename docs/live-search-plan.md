# Plan: a live keyword search on the replay page

Status: draft, not approved. Nothing here is built.

## In short
I want the demo page to do one thing live: search the corpus. A visitor types a query and sees the 10 records the shipped retrieval would hand to the model, ranked, in milliseconds, with no server, no key and no model call. The answers on the page stay a replay. A live answer needs a model and money, and [ADR 0014](adr/0014-close-the-project-as-a-portfolio-piece-and-record-where-it-misses-the-bar.md) closed that.

This shows the project's main finding where a reader can try it: retrieval decides how many answers can be right. On the 32 answerable dev questions the shipped search puts all the evidence in the top 10 for 24 of them ([ADR 0005](adr/0005-keyword-search-over-headed-records.md)). It costs $0 to build and to run.

## What the visitor gets
- A search box. Typing a query, or picking one of the 40 dev questions, shows the top 10 records: ID, source, header, a short excerpt, the score and a link to the source.
- For a dev question, each result is marked if the question needs it, and any needed record that did not make the top 10 is listed.
- A plain label: the search is live and runs in the browser, and the answers below it are saved.
- `#search=django%203.0.4` in the address opens a search, so a link or a screenshot script can show one. It must work beside the existing `#dg-003` question link, and a malformed hash must not throw.
- A query over 500 characters is refused with the same message the full app gives (`question_chars` in `src/advisor/web/limits.py`). An empty query shows nothing.

## What is searched
The rung the system ships: R1, keyword search over each record's header and body, top 10, no soft filter (`src/advisor/web/service.py` fetches 100 and sends 10). Not the reranker and not the embedding models, which did not beat R1. The soft filter was one dev question ahead and was not adopted (ADR 0005). The page says "keyword search over 1,174 units (1,164 records and 10 KEV entries) for 18 packages", and that R1 is one rung of nine.

## How it is built
1. **`scripts/build_search_index.py`** writes `docs/demo/corpus.json` from the local store: for each of the 1,174 units, its ID, source, header, body and link. It reads no key and calls no model, as `build_replay.py` does. Email addresses are replaced with the replay build's rule, so the published text is not the indexed text for one record (see "Email replacement and parity" below). It adds the dev gold evidence IDs for the 40 dev questions to `data.json`. No test or Test v2 question ID, question text or question-to-evidence mapping goes in `docs/demo`.
2. **`docs/demo/search-core.js`** is the search, with no page code, so Node can load it for tests. It ports:
   - the tokeniser of SQLite FTS5 `unicode61 remove_diacritics 2`. SQLite uses its own Unicode tables for case folding and accents, and keeps the Co category as token characters, so NFD plus stripping marks is not enough. The port is checked on the whole corpus, not assumed;
   - `match_expression` in `src/advisor/retrieval/bm25.py`: ID phrases first (not de-duplicated, so a repeated ID counts twice), then ASCII words (de-duplicated, case-insensitively), cut at 64 terms after the ID phrases, joined by OR. The words inside an ID are also scored as separate words. Python's `\d` and its ignore-case `[0-9a-z]` match some non-ASCII characters, so the port reproduces that or the plan records the difference;
   - FTS5's `bm25()` with its defaults: k1 1.2, b 0.75, IDF = log((N - n + 0.5) / (n + 0.5)) floored at 1e-6 when it is zero or below, where n is the number of documents holding the phrase and tf is how many times it occurs in the document. Document length is its token count in the indexed `text` column (the UNINDEXED `doc_id` adds none), and avgdl is the total tokens over N = 1,174. Results sort by exact score, then by the prefixed unit ID in byte order (`ghsa:` before `kev:` before `nvd:`), as the SQL does. There is no tolerance in the sort, because a tolerance comparator is not transitive. I confirm each of these against the FTS5 documentation and source before step 2, because I am working from the project's code and the documented formula.
3. **The page** (`index.html`, `app.js`, `style.css`) gets the search box and the result list. It reads `corpus.json` on the first search and builds the index in the browser. Typing runs on input events, not a form submit, because the policy sets `form-action 'none'`.
4. **Text only.** Results are made with `textContent`. Links are built only from an ID that matched the GHSA or CVE pattern, and only to the two hosts the page already allows. The content security policy does not change: `script-src` and `connect-src 'self'` cover the two new files. No `eval`, no WebAssembly. The regexes are linear and a query has at most 64 terms, so a long query is not a CPU risk.

## Why not real SQLite in the browser
SQLite compiled to WebAssembly would give the same ranking for free. It needs `wasm-unsafe-eval` in the policy and about 1 MB of vendored library, and it makes the security story longer. A corpus of about 1.7 MB does not need it, and a ported ranking can be tested against the real one.

## What is replaced, and parity
Two things are replaced in the published text. Email addresses, with the rule the replay build uses, change 10 documents. Quoted example credentials, such as `password = "..."` in an advisory's proof-of-concept code, change 9 more. The second was added after step 1, when the secret scan flagged 27 such strings in 9 advisories. The page has no use for the values, and a scanner cannot tell a sample from a real one.

Replacing text changes a record's tokens, its length and the average length. So the parity target is the real `Bm25Index` built over the **published text** (the same documents `corpus.json` carries), and I measured the top 10 against the unreplaced index for the 40 dev questions. Two differ, each by one record at the edge of the top 10: `vr-001` (score 7.373 against 7.389 at the cut) and `ab-005` (6.806 against 6.794). A store-gated test pins those two, so a change in the data shows up.

That breaks rule 3 as first written, which asked for the browser top 10 to equal the `shown` list saved in `data.json` for all 40. I propose to amend it: equal for the 38 where the replacements move nothing, and for `vr-001` and `ab-005` the page shows the live list and says the saved run was shown a slightly different one. I settle this before step 2.

## Decisions taken, open to change
- **Ship full record text.** The index needs it, and shipping postings instead needs word positions for the ID phrases and saves little. GitHub advisory text is CC BY 4.0 and NVD text is public domain. The footer now says records are cut to a short excerpt, which would become false, so it changes to say the full text is published with email addresses replaced, and the CC BY "changes made" line in `data/ATTRIBUTION.md` gets a matching line for `corpus.json`.
- **Raise the size cap** in `tests/test_replay_demo.py` from 2 MB to 5 MB, on purpose. The page will be about 2 MB, and the transfer is smaller because Pages compresses it.
- **Run gitleaks on `corpus.json`** before its first commit. Advisory bodies can hold example keys and tokens, and the CI secret scan could trip.

## The adoption rule, fixed now
It ships only if all of these hold:
1. **Tokeniser parity.** For all 1,174 documents the browser tokens match the FTS5 tokens in count and order. A committed fixture holds one line per document: its token count and a sha256 of its token list, dumped from an `fts5vocab` table of type `instance`.
2. **Ranking parity.** A committed golden file, `tests/fixtures/search-golden.json`, holds the real index's top 100 (unit ID, score) for each query: the 40 dev questions plus at least 50 made-up queries (IDs, package names with versions, non-ASCII text, an empty query, 70 words, a repeated word, a repeated ID). The browser top 10 must match by ID and order. Scores are compared with a relative tolerance of 1e-12 in the test only, since floored IDF scores sit near 1e-6.
3. **Free check with no store.** For the 40 dev questions, the browser top 10 must equal the `shown` list already in `data.json`. Amendment proposed after step 1, not yet approved: this holds for 38 of the 40, and `vr-001` and `ab-005` are the two named exceptions (see above).
4. **Hostile text.** The existing 30 payloads, in the corpus fields, the hash and the search box, produce no markup, script or link except the two allowed hosts, in a real browser, as the replay tests do.
5. **No leakage.** The page holds only dev questions. A test checks that `docs/demo` carries no test or Test v2 question ID or text and no question-to-evidence mapping. The gold files are already public in the repository, so this is about what the page ships.
6. **Existing tests updated on purpose,** each named in the commit: `fetch(` appears exactly once and is `data.json` (it becomes two, and the rule says which); the exact key set per question gains the evidence field; the allowed tags and attributes gain the input, label and `value` the search needs; the ban-list scan covers `search-core.js` too; the size cap; and the browser harness loads both scripts.
7. **CI can enforce it.** The CI job gains a pinned Node setup and a `node --test` step, and the test fails if Node is missing instead of skipping. The store is gitignored, so the fixtures above are what CI checks. The Python test that builds the fixtures from the real index skips where the store is absent, as the rebuild test does.
8. **The whole suite, ruff and both freeze guards are green,** and nothing under `eval/` or `eval-v2/` changes. It runs from `python -m http.server -d docs/demo` and from the published page.

If 1 or 2 fails and I cannot fix it, I do not ship a search that claims to be the real one. I would then label it an approximation or drop it.

## What it will not do
- It will not answer a typed question. There is no model behind it.
- It will not run the checker on a typed query.
- It will not search outside the 18 packages. A query about another library finds nothing, and the page says so.
- It does not make Otis more accurate. It shows how the existing retrieval behaves.

## Files
New: `scripts/build_search_index.py`, `docs/demo/search-core.js`, `docs/demo/corpus.json`, `tests/test_search_parity.py`, `tests/fixtures/search-golden.json`, a token fixture, a small Node test file, `docs/adr/0016-search-the-corpus-in-the-browser.md`. Changed: `docs/demo/index.html`, `app.js`, `style.css`, `data.json`, `tests/test_replay_demo.py`, `data/ATTRIBUTION.md`, `.github/workflows/ci.yml`, `docs/replay-demo.md`, `README.md`, `PROGRESS.md`, and `scripts/make_replay_gif.py`.

## Steps, each ending at a gate
1. Index builder, `corpus.json`, the token fixture and the tokeniser parity test. Gate: rule 1.
2. The search port, the golden file and the ranking parity test. Gate: rules 2 and 3.
3. The page, the hash link and the hostile-text tests, with the existing tests updated. Gate: rules 4 to 6.
4. The Node step in CI, ADR 0016, the footer and attribution, the docs and the README line. Gate: rules 7 and 8.
5. The GIF script gets a search scene. Its fixed pixel offsets (`CARDS`, `RECORDS`) are measured again, because a search box moves the layout.

One commit per step, each with its tests. Pushes are spaced out, and I push each one on my own word.

## Cost and risk
No model calls and no credit. The risk is ranking parity, which the golden file and the token fixture are there to catch, with the FTS5 details confirmed before step 2. The other risk is weight: about 2 MB of text on the page, which the size cap decision covers.
