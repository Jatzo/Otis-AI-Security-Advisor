# Evidence round, step 2: the dev generation check for R9

Run on 24 November 2026 on the 40 v1 dev questions, 3 runs, as rule 4 of [the evidence round plan](evidence-round-plan.md) sets out. The system was R9 retrieval (the linked records within 10) with the completeness check of [the spec](completeness-spec-v1.md), tagged `completeness-spec-v1`. Commit `1e2eb59` with a clean tree. Same model (`claude-sonnet-5-5`), settings, task text, addendum and checker as the Phase 6 system, plus rule 9. 120 calls, $2.81. The test splits were not touched.

Files: `eval/results/generation-r9-dev-raw.jsonl` and `generation-r9-dev-checked.jsonl`. The Phase 6 reference is `generation-dev-checked-phase6.jsonl`. The same replies with rule 9 on and R1 retrieval are `generation-dev-checked-completeness.jsonl`.

## In short
R9 with the completeness check passes all four conditions of rule 4. It scored 33, 33 and 32 of 40 checked correct, against 30 in every run for Phase 6. Under the plan, that means it enters the system the Test v2 run scores. The result is on 40 questions I have now looked at 12 times, and I would not read more into it than that.

## The four conditions
| Condition (rule 4) | Result |
|---|---|
| Checked correct at least 30 of 40 in each run | 33, 33 and 32. Phase 6 had 30, 30 and 30. |
| No parse failure | 0 in all three runs. |
| No more wrong answers shown than Phase 6, summed over the runs | 6 against 6 (`mh-004` and `mh-005` in every run, under both systems). |
| Mean input tokens at most 1.3 times R1's | 9,874 against 12,880, which is 0.77. |

## What moved
Four questions went from a decline to a correct answer in every run: `dg-002`, `dg-005` (both sources-disagree), `mh-002` and `mh-003` (both multi-hop). Each needs a record that R1's top 10 does not hold together with the one it links to, which is what R9 adds. Wrong replies that were declines or refusals fell from 24 to 13, summed over the runs.

Two questions got worse.
- `vr-002` (which advisories affect struts2-core 6.3.0.2) was withheld by the completeness rule in all three runs. The package holds 126 records, so no list of 10 can pass. It was a correct answer under Phase 6. This is the cost the spec states.
- `vr-005` (a yes or no on one CVE and Django 3.0.4) was refused by rule 7 in run 3 only. It passed in runs 1 and 2, so I read it as the model varying between runs, not as R9 or rule 9.

## Where it is not clean
- **A new refusal.** In all three runs the model refused `mh-001` (the NVD score for the CVE one advisory covers), with the stop category `cyber`. Under R1 it declined the same question in all three runs, so it was already wrong and nothing was lost. The refusal is a new way to fail: 3 of 120 replies never reached the checker. The plan counts parse failures, not refusals, so it does not fail the rule. I would still call it a finding.
- **Where the gain comes from.** Rule 9 only removes replies, so all of the gain is R9's retrieval. The four questions it won are the kind R9 was built for, and the Dev-R result already said the linked-records score is an upper bound, because that gold is built from the same links. These four are on questions written for v1 dev, so they are better evidence than Dev-R, but they are four questions.
- **What it did not fix.** `mh-004` and `mh-005` are still wrong in every run, so the 6 wrong answers shown are unchanged. R9 did not make the checker's job easier on those.
- **The completeness cost.** 13 of the 18 packages hold more than 10 records, so the rule can pass only for 5. On this set that cost one question. A list question about a big package is a decline by design.

## What I would not trust
- 40 questions, 32 of them answerable, run 3 times. The three runs are not independent: they share the same questions, so the gain is 4 questions, not 12.
- These questions have been looked at 12 times (the ledger counts them), so a pass here is weaker than a pass on fresh data. The plan keeps the real test for Test v2.
- I have no confidence interval on the difference. The runs agree closely, so the model is steady. That does not show the gain would hold on other questions.

## Spend
$2.81 for 120 calls, $0.0234 a query, against $3.55 for the Phase 6 system. The phase now stands at $10.12 of the $12 cap.
