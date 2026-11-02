# 0005: Retrieval is keyword search over records with a header, for now

- Status: accepted
- Date: 2026-11-02

## Context
Phase 3 asked which retrieval choices help on the dev questions. The ladder, its measures and its adoption rule were written and committed in [the retrieval plan](../retrieval-plan.md) before any retrieval code or result existed. A rung is adopted only if it adds at least 4 net questions to all-evidence@10 over the best rung so far, with an exact McNemar p below 0.05. Dev gives 32 scored questions, so p below 0.05 needs about 6 questions to move one way and none the other.

Questions about advisories are full of exact strings: advisory and CVE IDs, package names, version numbers. That favours keyword search. The ladder tested whether dense search could still beat it.

## Decision
- **Retrieval is BM25 (SQLite FTS5) over one unit per GitHub advisory, NVD record and linked KEV entry.** Each unit has a header built only from its own record: ID, package, dates, the source's own severity or score, affected ranges and aliases. Rung R1.
- **The header stays.** It is worth 17 questions over the same search without it (24 against 7, none lost).
- **No dense model, reranker, hybrid, record splitting or decomposition is adopted.** Each is reported in full in [the results](../retrieval-results.md). R6, the soft ID and package filter, is one question ahead of R1, short of the 4 the rule needs.
- **The 8 dev questions R1 misses are the open problem.** They are 5 multi-hop and 3 where GitHub and NVD disagree. They need two or more linked records, and two need a KEV entry that was never retrieved.

## Evidence
- R1 holds all the evidence in the top 10 for 24 of 32 (58 to 87%). All 8 lookups and all 9 version checks are met. Multi-hop is 2 of 7 and sources-disagree 5 of 8.
- Dense search was worse than keyword search: Qwen3-Embedding-0.6B got 12 and bge-small 13, and each lost 12 questions R1 got right. Joining bge-small to R1 with reciprocal rank fusion (R4) got 20 and lost 4.
- The reranker (R5) matched R1 on count and moved one question each way. It took a median of 11.4 s a query at 12 threads, against a budget of 3 s at 2.
- Splitting long records (R7) changed no question at 10. Decomposition by a model (R8) got 20, 22 and 21 over three runs and lost 4 questions by majority, for $0.10.
- R1 answers in a p95 of 6 ms at the demo's 2 threads.

## Alternatives not taken
- **Dense or hybrid retrieval as the default.** It is the common choice and it lost here. The result holds for this corpus, where the questions carry exact identifiers.
- **A reranker.** It added nothing on dev and takes thousands of times longer per query than keyword search.
- **Splitting long records.** About 1 in 10 GitHub records is over 6,000 characters, but splitting changed no question at 10. A likely reason is that the facts questions ask for are in the header, which was not tested. It improved all-evidence@20 by one question (26 against 25), which the rule does not count.
- **Model-written sub-queries.** They cost money on every question and scored lower. Why was not investigated.
- **A change to the plan after the numbers.** Trying other prompts, token caps or models until dense search wins would turn the ladder into tuning on 32 questions. The plan's rule is kept, and any further experiment gets its own plan written first.

## Consequences
- The checker and the generator in Phase 4 get their evidence from R1. Test is scored once in Phase 5 for R1, and the write-up reports the dense and reranked rungs only as dev results.
- The multi-hop and sources-disagree questions are where retrieval is weakest. A retrieved advisory could bring its linked NVD record and KEV entry with it. That is not on the ladder, so it needs its own plan, fixed before it is run, and it would be reported as a new rung.
- Only 4 dev lookups describe the advisory in words other than its own, and R1 found all 4. If the test split shows dense search matters for reworded questions, that is reported as it comes, and this decision is revisited.
- The Qwen3 index took 105 minutes to build on 12 threads. Nothing in the demo needs it, so it is not shipped.
- Revisit if R1's test score is far below its dev score, which would mean dev was too easy, or if linked-record retrieval changes the multi-hop picture.
