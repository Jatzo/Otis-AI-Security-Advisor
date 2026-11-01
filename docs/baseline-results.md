# Baseline: the model with no retrieval

Asked without any documents, the model mostly says it does not know. When it does answer, it is right 7 times in 9.

That is the baseline for this project, and it is a sound one. The model is not guessing its way through 32 answerable questions and failing. It declines 23 of them, because it has nothing to look the answer up in. Retrieval is what lets it answer.

These are **dev** results, 40 questions, used for tuning. The 110 test questions have not been run against any system.

## What was run

- **Model:** Claude Sonnet 5.5 (`claude-sonnet-5-5`), effort `high` (the model's default), up to 16,000 output tokens, no tools, no documents, no fallback model.
- **Prompt:** the scope (18 packages, three sources, the 1 November 2026 snapshot), the answer format, and one instruction: if you are not sure, decline. The text is in `eval/task.md` and `eval/baseline_prompt.md`.
- **Questions:** the 40 dev questions: 8 direct lookups, 9 version checks, 7 multi-hop, 8 where the right answer is to decline, 8 where GitHub and NVD may disagree.
- **Runs:** 3 times, because this model's sampling cannot be set and one run is noisy.
- **Order:** the questions, gold, rules, scorer and runner were fixed and tagged (`eval-freeze-v1`) before the first call. Every result line records the commit and the git blob id of each frozen file ([ADR 0004](adr/0004-freeze-the-evaluation-with-a-tag.md)).
- **Scoring:** deterministic code, no model judge. Details are in `eval/rules.md`.

## Results

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Correct, all 40 questions | 15 (38%) | 15 (38%) | 15 (38%) |
| Correct, the 32 answerable questions | 7 (22%) | 7 (22%) | 7 (22%) |
| Declined, of the 32 answerable | 23 | 23 | 23 |
| Answered, of the 32 answerable | 9 | 9 | 9 |
| Right, of those answered | 7 | 7 | 7 |
| Declined correctly, of the 8 that should be declined | 8 | 8 | 8 |
| Invented IDs | 1 | 0 | 0 |
| Refusals, and replies that did not parse | 0 | 0 | 0 |
| Cost | $0.24 | $0.23 | $0.23 |

The answerable figure is **7 of 32, 22%** (95% interval 11% to 39%), and it is the same in all three runs. Three questions changed outcome between runs: `lk-003`, `lk-005` and `dg-004`. Each was right in one run and wrong in the other two. The other 37 had the same outcome every time.

By type, on the answerable questions:

| Type | Questions | Answered (3 runs) | Right (3 runs) |
|---|---|---|---|
| Direct lookup | 8 | 0, 1, 1 | 0, 1, 1 |
| Version check | 9 | 5, 4, 4 | 4, 4, 4 |
| Multi-hop | 7 | 1, 1, 1 | 1, 1, 1 |
| Sources disagree | 8 | 3, 3, 3 | 2, 1, 1 |

Each type has 7 to 9 questions, so a difference of one question is not a finding. The table is there to show where the model answers at all.

## What the 22% is, and is not

It is the share of answerable questions the model got right when it was told to decline if unsure. Most of the gap is declining, not being wrong.

- It answered 9 of the 32 and got 7 right.
- It answered none of the 8 questions about advisories published in or after June 2026, which is where its training ends.
- It answered at most one of the 8 direct lookups: the first patched version, the advisory ID for a description, the severity label. It does not carry those facts for this corpus, and it said so.
- Declining everything would also score 8 of 8 on the questions that should be declined. That is why every table in this project shows over-abstention (here 23 of 32) beside accuracy.

The figures belong to this prompt. A version told to answer every question would answer more and might be wrong more often. That row is not measured yet.

## The one invented ID

In 120 replies, the model named one advisory that does not exist. In run 1, asked which known vulnerabilities pyyaml 3.12 has (`vr-003`), it listed three advisory IDs. Two are real. The third, `GHSA-6757-jp84-gxfp`, is not in GitHub's REST API or in OSV. It differs by its last character from `GHSA-6757-jp84-gxfx`, a real pyyaml advisory in the corpus.

It was caught because the scorer checks every ID in a reply, in the explanation text as well as the ID list, against the corpus and then against GitHub, NVD and OSV. This is the kind of error the checker in Phase 4 has to remove.

## What this sets for retrieval

- Answer more of the 32 answerable questions than 7, on the test split, scored once.
- Keep declining the questions that should be declined, and report over-abstention beside accuracy.
- Keep invented IDs at zero.
- Report the post-cutoff slice apart: the baseline answered none of it.

## Limits

- 40 questions, so the intervals are wide. Dev is for tuning. The number that counts is the test split in Phase 5.
- The gold comes from a separate script, but its facts come from the same advisory database the corpus uses. Agreement with it is not independent confirmation that the database is right.
- One prompt, one model, one effort level.

Per-question replies, scores and costs are in `eval/results/` (`baseline-dev.jsonl` and `baseline-dev.scored.jsonl`). Cost for all 120 calls: $0.70. Median latency 2.4 to 2.7 seconds a question.
