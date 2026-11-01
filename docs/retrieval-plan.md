# Retrieval ladder: the plan, fixed before the first run

Written 1 November 2026, before any retrieval code exists and before any retrieval result has been seen. The git history is the receipt: this file is committed first, and the results are committed after it.

The question is which retrieval choices help on the dev questions, with the fewest moving parts. The test split is not used here. Phase 5 reports retrieval on test once, for the rung chosen below and for rung R1.

## What is indexed

- **Units.** One unit per GitHub advisory and one per NVD record, plus one per KEV entry whose CVE a corpus advisory names. IDs carry a namespace: `ghsa:GHSA-...`, `nvd:CVE-...`, `kev:CVE-...`. A hit on one namespace never counts for another, and an alias earns no credit.
- **Header.** Each unit starts with a header built only from its own record: ID, source, package and ecosystem (at most 3 packages), published date, the source's own severity label or score, the affected ranges as introduced and fixed pairs (at most 6, then "and N more"), the first fixed version, and the CVE aliases. The header is capped at 700 characters. It never holds a fact from another source, and it holds no KEV flag.
- **Body.** The summary and the details. BM25 indexes all of it. A dense model embeds the header and body cut at the model's limit: 512 tokens for bge-small, 2,048 for Qwen3 (a speed cap, not the model's limit). The number of cut units is reported.
- **Split units (R7 only).** Records over 1,600 characters become windows of about 1,600 characters (about 400 tokens) with 200 characters of overlap and the header repeated. Hits are collapsed to the record before cutting at k, so k always counts unique records.

## What counts as a hit

Gold is the `evidence` object in `eval/gold.jsonl`. A question needs every record in it. Matching is by namespaced ID, exactly.

- Only answerable dev questions are scored (32 of 40). Abstain questions have no evidence, so recall is undefined there. They are left out and the table says so.
- **Recall@k:** the share of a question's evidence records in the top k.
- **All-evidence@k:** 1 if every evidence record is in the top k, else 0. This is the primary metric, at k = 10, because the version-set and multi-hop questions need every record.
- **MRR:** the rank of the first evidence record.
- Where a question has more than k evidence records, all-evidence@k is impossible. The table gives the count of such questions.
- KEV evidence is reported on its own line.
- Ties break by record ID, ascending.
- Latency per query and index build time are recorded for every rung.
- Reported by question type, and by template, with counts and 95% Wilson intervals.

## The ladder

Baseline rows, so the ladder has something to beat:

- **B0, package filter only.** Every record of the package the question names, ordered by record ID. Reported as all-evidence at "all of them" and the median list length. It answers: how much would reading the whole package cost?
- **B1, exact ID match only.** Records whose ID or alias appears in the question. Reported with coverage (the share of questions that name an ID at all).

Rungs, each adding one thing to the one before. Retrieval depth is 100 for fusion and reranking.

| Rung | Adds |
|---|---|
| R0 | BM25 on the body, no header |
| R1 | BM25 with the header |
| R2 | Dense search, embedding model A, with header |
| R3 | Dense search, embedding model B, with header |
| R4 | Hybrid: BM25 (R1) and the dense model that did better of R2 and R3, joined by reciprocal rank fusion with k = 60 |
| R5 | R4, then a cross-encoder reranks the top 30 |
| R6 | R5, with a soft filter: exact ID matches go first, and records of a package named in the question rank above the rest. No version ranges are read |
| R7 | Splitting long records, applied to the highest rung adopted so far |
| R8 | Query decomposition: a model writes up to 4 sub-queries, each runs through the rung adopted so far, the lists are merged by reciprocal rank fusion into one ranking, then cut at k |

The soft filter reads only ID formats, the 18 package names and their short forms. It never reads a version or a range, because deterministic code answering version questions would break [ADR 0001](adr/0001-retrieval-answers-code-checks.md). Version-range lookup is a separate comparison row for the final tables, not a rung.

## Models and settings, fixed now

- **Embedding A:** Qwen3-Embedding-0.6B. Queries use the prefix `Instruct: Given a question about a software vulnerability, retrieve the advisory record that answers it\nQuery: ` and documents use none.
- **Embedding B:** bge-small-en-v1.5. Queries use `Represent this sentence for searching relevant passages: ` and documents use none. Its 512-token limit confounds R2 against R3, and the write-up says so.
- **Reranker:** bge-reranker-v2-m3, with a small cross-encoder as the fallback if the latency budget below is missed.
- **Pins:** each model is pinned to the repository commit that is current when it is first downloaded. The commit hashes are written into every result line and into ADR 0005. The embedding cache is keyed on model commit, text hash and library versions.
- **Licences** are read from each model card when the model is added. A model that is not usable in a public repository is replaced and the replacement is written here.
- **R8 model:** `claude-sonnet-5-5`, effort `medium`, 2,000 output tokens, no fallback. It runs 3 times and the spread is shown. A spend cap is passed on the command line and the sub-queries are saved in `eval/results/`. R8 never runs in CI.

## How a rung is adopted

- A rung is adopted over the best earlier rung it builds on only if it adds at least 4 net questions to all-evidence@10 and the exact McNemar test gives p < 0.05. Otherwise the simpler rung stays and the rung is reported as not adopted.
- With 32 questions, p < 0.05 needs about 6 questions to move one way and none the other. A small gain is therefore reported but not adopted. This is intended.
- The R2 against R3 fork goes to the model with the higher all-evidence@10, then the higher recall@10, then the smaller model. R7 is applied to the highest adopted rung before R8.
- Every rung is reported, whatever its result.
- The shipped rung also needs a p95 query latency of 3 seconds or less on 2 CPU threads, with the index built offline. If the reranker misses that, the fallback reranker is used and the change is reported.

How the chain runs, written down so it cannot change after the numbers are seen:

1. R0 is the starting point. R1 is compared with R0. Then the winner of R2 and R3 (by the fork rule) is compared with the best rung adopted so far.
2. R4, R5 and R6 are each compared with the best rung adopted so far. Their definitions do not change if an earlier rung is not adopted: R4 always joins R1 with the dense winner.
3. R7 takes the pipeline of the best rung adopted so far and splits long records. R8 does the same, after R7.
4. R8 runs 3 times. It counts as a hit on a question if it gets all the evidence into the top 10 in at least 2 of the 3 runs. That majority is what goes into the comparison. Each run is shown.
5. A rung that is not adopted is still reported in full.

## Guards

- The ladder script drops every question that is not in the dev split before anything else, and refuses to run if the frozen files differ from the freeze tag.
- The filter's patterns are written from the ID formats, the 18 package names and the version grammar, not from the question wordings. Results are shown per template so a fit to a wording would show.
- No file under `eval/` changes. Results go to `eval/results/`.

## Not covered

- Answer quality. That is Phase 4 and Phase 5.
- A long-context row and a structured-lookup row. They belong to the Phase 5 tables.
- Hand-written wording check. If the owner supplies 15 to 20 questions in their own words with the advisory expected for each, they are added as a separate small table, and not used for tuning.
