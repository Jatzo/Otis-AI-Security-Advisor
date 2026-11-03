<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/otis-icon.svg">
  <img src="docs/brand/otis-mark.svg" alt="Otis" width="48">
</picture>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/brand/otis-banner.svg">
    <img src="docs/brand/otis-lockup.svg" alt="Otis" width="360">
  </picture>
</p>

# Otis: AI Security Advisor

Otis answers questions about real software vulnerabilities from public advisory data (NVD, GitHub advisories, CISA KEV). Every answer cites what it relied on, says "I don't know" when the sources do not cover the question, and shows where the sources disagree.

Work in progress. The data, the evaluation, the no-retrieval baseline, the retrieval ladder, the answer checker and the one-time test run are done. The red team and the public demo are not built yet.

## What Otis will look like

A design mockup of the planned interface, in light and dark. The wording is sample text, and the interface itself is not built yet.

<p align="center">
  <img src="docs/brand/otis-ui-mockup.png" alt="Mockup of the Otis interface in light and dark. Each answer says what Otis found, lists the facts it confirmed against the advisories, shows the records it read, and shows a No answer card when it cannot confirm a reply." width="900">
</p>

## Otis at a glance

```text
OTIS   security advisor for open-source packages
status    in build: data, evaluation, baseline, retrieval, checker and test run done; red team next
reads     GitHub advisories, NVD records, CISA KEV (snapshot 1 November 2026)
covers    18 packages: 9 PyPI, 6 npm, 3 Maven
answers   with the advisory and CVE IDs it relied on
declines  when the sources do not cover the question
flags     where GitHub and NVD disagree
checks    every ID, package, version and score against the record it cites
```

Otis answers in one pass: retrieve the records, answer, check. It does not pick its own tools or loop on its own. Iterative retrieval was measured in Phase 3 and did not beat plain keyword search, so Otis answers in one pass.

## How an answer is made

```mermaid
flowchart LR
  Q[Question] --> R[Retrieve advisory records]
  R --> A[Model answers, each claim cites a record]
  A --> C{"Checker: does every claim match its record?"}
  C -->|yes| OUT[Answer with citations]
  C -->|no| D[Remove the claim, or decline]
```

This is the design in [ADR 0001](docs/adr/0001-retrieval-answers-code-checks.md). Retrieval and the model answer the question. Deterministic code only checks the answer, and grades the evaluation.

## Where each part stands

| Part | What it is | State |
|---|---|---|
| Data | 588 GitHub advisories, 576 NVD records and the KEV catalogue for 18 packages, with version ordering for PyPI, npm and Maven | Done. [Data report](docs/data-report.md) |
| Evaluation | 150 questions with gold answers from a separate script, frozen under the git tag `eval-freeze-v1` before any system ran | Done. [Rules](eval/rules.md), [ADR 0004](docs/adr/0004-freeze-the-evaluation-with-a-tag.md) |
| Baseline | The model with no retrieval, run on the 40 dev questions | Done. [Results](docs/baseline-results.md) |
| Retrieval | Nine rungs from keyword search to reranking and decomposition, tuned on dev only | Done. Keyword search over headed records won. [Results](docs/retrieval-results.md), [ADR 0005](docs/adr/0005-keyword-search-over-headed-records.md) |
| Checker | Refuses any reply with a claim its cited record does not support | Done. [Results](docs/generation-results.md), [ADR 0006](docs/adr/0006-the-checker-refuses-whole-replies.md) |
| Test run | Five systems scored once on the 110 test questions, from a tagged system | Done. [Results](docs/test-results.md), [ADR 0007](docs/adr/0007-score-the-test-split-once-from-a-tagged-system.md) |
| Red team | Advisory text treated as untrusted input, with what held and what did not | Phase 6 |
| Demo | A public page showing the answer, the evidence and each check | Phase 7 |

The phases, decisions and state of play are in [PROGRESS.md](PROGRESS.md).

## What Otis is held to

The evaluation has 150 questions: 30 direct lookups, 35 version checks, 25 that need more than one record, 30 that should be declined and 30 where GitHub and NVD may disagree. 40 are for tuning (dev) and 110 are scored once (test). Scoring is deterministic code, with no model as judge.

Two dev examples show what is asked:

- "Which package does CVE-2025-99475 affect?" The CVE is invented and absent from NVD, so the right answer is to decline.
- "Do GitHub and NVD put CVE-2021-45105 in the same severity band?" GitHub scores it 8.6 and NVD 5.9, which are different bands, so the right answer says the sources disagree and gives both scores.

GitHub and NVD give a different severity band for 46 of the 275 advisory and CVE pairs that both score.

## What the baseline shows

With no retrieval, the model answers 7 of the 32 answerable dev questions correctly (22%). It declines 23 of the rest, and when it does answer it is right 7 times in 9. In 120 replies it invented one advisory ID. The model knows what it does not know. Retrieval is what lets it answer. The full table is in [docs/baseline-results.md](docs/baseline-results.md).

## What the retrieval ladder shows

On the 32 answerable dev questions, keyword search over records with a header puts every record a question needs into the top 10 for 24 of them (75%, 95% interval 58 to 87%). Without the header it manages 7. Two embedding models, a reranker, splitting long records and question decomposition were each tried on top, and none passed the adoption rule written down before the first run. Both embedding models scored lower than keyword search. The questions are full of exact IDs, package names and versions, which suits keyword search, though I did not test why.

The remaining misses are multi-hop questions and questions where GitHub and NVD disagree, which need two or more linked records. All 8 lookups and all 9 version checks are met. These are dev numbers on a small set. The test split was scored once, in Phase 5: see [the test results](docs/test-results.md). For every rung, see [the results](docs/retrieval-results.md) for every rung.

## Development

```
uv sync
uv run pytest
uv run ruff check .
python scripts/check_eval_frozen.py
```

The last command fails if anything frozen under `eval/` has changed since the tag.

## Why the name Otis?

Otis is my RAGdoll cat. It felt like the perfect name for a RAG project.
