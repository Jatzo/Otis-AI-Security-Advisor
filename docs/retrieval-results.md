# Retrieval ladder: results on dev

Keyword search over records with a header wins. It puts every record a question needs into the top 10 for 24 of the 32 answerable dev questions. Nothing added on top of it, including two embedding models, a reranker, record splitting and question decomposition, passed the adoption rule fixed in [the retrieval plan](retrieval-plan.md) before any result was seen.

These are **dev** results, used for tuning. The test split has not been used for retrieval. Phase 5 reports retrieval on test once, for this rung.

## What was run

- **Questions:** the 32 answerable dev questions. The 8 dev questions that should be declined are left out, as the plan says. Three of them do have evidence records (the CVE exists, the field asked for does not).
- **Target:** every evidence record in the gold for a question, matched by namespaced ID (`ghsa:`, `nvd:`, `kev:`). No credit across aliases.
- **Main measure:** all-evidence@10, which is 1 when every needed record is in the top 10.
- **Models:** Qwen3-Embedding-0.6B (Apache 2.0), bge-small-en-v1.5 (MIT) and bge-reranker-v2-m3 (Apache 2.0). The commit of each model is saved in `eval/results/model_revisions.json`.
- **Rule for adopting a rung:** at least 4 more questions than the best rung so far, and an exact McNemar p below 0.05.

## The ladder

| Rung | What it adds | All-evidence@10 | @5 | @20 | Recall@10 | MRR | Median query time |
|---|---|---|---|---|---|---|---|
| R0 | Keyword search on the record text, no header | 7/32 (11 to 39%) | 6 | 11 | 0.27 | 0.24 | 2 ms |
| **R1** | **Keyword search with the header** | **24/32 (58 to 87%)** | 20 | 25 | 0.88 | 0.84 | 2 ms |
| R2 | Dense search, Qwen3-Embedding-0.6B | 12/32 (23 to 55%) | 9 | 16 | 0.44 | 0.30 | 740 ms |
| R3 | Dense search, bge-small | 13/32 (26 to 58%) | 11 | 14 | 0.44 | 0.26 | 22 ms |
| R4 | R1 and R3 joined by reciprocal rank fusion | 20/32 (45 to 77%) | 14 | 25 | 0.76 | 0.67 | 23 ms |
| R5 | R4, then the top 30 reranked | 24/32 (58 to 87%) | 20 | 24 | 0.87 | 0.87 | 11.4 s |
| R6 | R5, with exact IDs and a named package placed first | 25/32 (61 to 89%) | 22 | 25 | 0.91 | 0.93 | 28 ms (reranker scores reused) |
| R7 | R1, with long records split into windows | 24/32 (58 to 87%) | 20 | 26 | 0.87 | 0.87 | 6 ms |
| R8 | R1, with a model writing sub-queries | 20/32 (45 to 77%), 21/32 by majority of 3 runs | 20 | 23 | 0.74 | 0.79 | 1.7 s |

Two rows for reference, not rungs:

| Row | Result |
|---|---|
| B0: every record of the package the question names | Holds all the evidence for 17 of 32 questions, with a median list of 6 records |
| B1: records whose ID appears in the question | The question names an ID in 21 of 32, and the matches hold all the evidence for 16 |

Rungs R2 and R3 are the two embedding models. R4 uses bge-small because it did better of the two, 13 against 12.

## Against R1

| Rung | Gained | Lost | Exact test p | Result |
|---|---|---|---|---|
| R0 | 0 | 17 | below 0.001 | Worse. The header is worth 17 questions |
| R2 | 0 | 12 | below 0.001 | Worse |
| R3 | 1 | 12 | 0.003 | Worse |
| R4 | 0 | 4 | 0.125 | Worse. Mixing dense results in pushed out 4 questions |
| R5 | 1 | 1 | 1.0 | Level |
| R6 | 1 | 0 | 1.0 | One question ahead. Not adopted: the rule needs 4 |
| R7 | 0 | 0 | 1.0 | Level |
| R8 | 1 | 4 | 0.375 | Worse by majority. The three runs got 20, 22 and 21 |

## Where R1 stands

| Type | All-evidence@10 |
|---|---|
| Direct lookup | 8/8 |
| Version check | 9/9 |
| Multi-hop | 2/7 |
| Sources disagree | 5/8 |

The 8 misses are all multi-hop or sources-disagree. The disagree misses (`dg-002`, `dg-005`, `dg-008`) need both a GitHub advisory and its NVD record, and R1 finds one of the two. Two multi-hop misses need a KEV entry, and KEV recall at 10 is 0.0: R1 never retrieved one. The lookups and version checks are already at the ceiling, so a later rung had nothing to win there.

## Speed and cost

- **R1 at the demo's 2 threads:** p95 of 6 ms over 10 queries, against a budget of 3 s.
- **R5, the reranker:** a median of 11.4 s and a p95 of 16.8 s a query at 12 threads. That is far over the budget, so it could not ship even if it had scored higher.
- **Qwen3 index:** 6,315 seconds (105 minutes) to build on 12 threads. bge-small took 35 seconds. The index is built offline and cached, but that is a real cost for a result that did not help.
- **R8:** $0.10 for 96 calls, about $0.001 each, against a cap of $1.

## What this does not show

- **Dev has 32 questions.** The intervals are wide, and one question is not a finding.
- **Lookups and version checks are at the ceiling,** so they cannot separate the rungs. Only 4 dev lookups describe the advisory in different words from its text, and R1 found all 4. With so few, how well dense search handles a reworded question is untested here. The test split has 11 such lookups, and its result is reported once, whatever it shows.
- **Dense search was run as fixed in the plan,** with the query prefixes and the token caps written down in advance. Other prompts, other models or a longer cap were not tried, and could do better.
- **Linking records was not tested.** A retrieved advisory could bring its NVD record and KEV entry with it. That would target the misses above, but it was not on the ladder and needs its own plan written first.
- **This is retrieval only.** Whether the answers are right is Phase 4 and Phase 5.

Per-question rankings and scores for every rung are in `eval/results/retrieval-dev.json`.
