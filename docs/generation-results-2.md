# Generation plan 2: dev results

Run on 2 November 2026 on the 40 dev questions, 3 runs, as fixed in [generation-plan-2.md](generation-plan-2.md). Commit `9625b62` with a clean tree, `eval-freeze-v1` unchanged, same model, settings, evidence and checker as the [first run](generation-results.md). The only difference is the one addendum bullet about `verdict`. 120 calls, $3.55. Phase 4 has now cost $7.32 of the $12 cap. The test split was not touched.

Files: `eval/results/generation-v2-dev-raw.jsonl`, `generation-v2-dev-checked.jsonl`, their `.scored.jsonl` versions and `generation-v2-dev-analysis.json`. Amendments: none.

## Verdict: not adopted

Version 2 does what it was written to do, and fails one of the five conditions the plan set before the run. The plan says that if any condition fails, the first version stays the Phase 5 system. So it does.

| Condition (from the plan) | Result |
|---|---|
| 1. Rule 7 refusals of sources-disagree replies fall from 4 to at most 1 | Met: 0 |
| 2. No question harmed that was not harmed in the first run | Met: none new |
| 3. Raw count at least 31 in each run, every raw flip read by hand | **Not met: 31, 30, 31** |
| 4. False passes stay at 6 or fewer | Met: 6 |
| 5. `verdict` set on all 15 replies to `vr-005` to `vr-009` | Met: 15 of 15 |

The failure is one reply. In run 2, `vr-002` ("which advisories affect struts2-core 6.3.0.2") came back as invalid JSON: a stray `)` after the closing quote of the `explanation` text, so the object does not parse. The three advisories and the three `affects` claims in it were right, and the same question was answered correctly in runs 1 and 3. It is the only raw flip in 120 replies, and it is a parse failure, which the scorer counts as wrong.

I can't say whether the new bullet made that slip more likely. The first run had no parse failure in 120 replies, and neither did the baseline, so this is 1 in 240 across the two prompts, which is too few to tell noise from cause. The plan did not give me room to decide that after the fact, so I haven't.

## Correct, by type

Counts in runs 1, 2 and 3. First run in brackets.

| Type | Questions | Raw | Checked |
|---|---|---|---|
| Direct lookup | 8 | 8, 8, 8 (8, 8, 8) | 7, 7, 7 (7, 7, 7) |
| Version-affected | 9 | 9, 8, 9 (9, 9, 9) | 9, 8, 9 (8, 9, 8) |
| Multi-hop | 7 | 2, 2, 2 (2, 2, 2) | 2, 2, 2 (2, 2, 2) |
| Should-abstain | 8 | 8, 8, 8 (8, 8, 8) | 8, 8, 8 (8, 8, 8) |
| Sources-disagree | 8 | 4, 4, 4 (4, 4, 4) | 4, 4, 4 (2, 3, 3) |
| **All** | 40 | 31, 30, 31 (31, 31, 31) | 30, 29, 30 (27, 29, 28) |
| **Answerable** | 32 | 23, 22, 23 (23, 23, 23) | 22, 21, 22 (19, 21, 20) |

Pooled over the three runs, the checked row is 89 of 120 against 84, and the raw row 92 against 93. The plan expected about 88 pooled, with a little more possible if `vr-009` passed by chance. It did, in all three runs.

## What the change did

- **`verdict` set on a sources-disagree reply: 0 of 24, from 5.** It is still set on all 15 replies to the version-verdict questions. The one dev type with no KEV verdict question could not test the KEV half of the bullet.
- **Rule 7 refusals: 0, from 6.** All 6 remaining checker refusals are at rule 6.
- **Harmed (raw correct, checker refused): 3 rows, from 9.** All three are `lk-001`, the extra NVD `fixed_in` claim on a record with no CPE rows, which the plan listed as not covered.
- **Recovered: 6 rows.** `dg-003` x3 and `dg-001` run 1 are what the bullet was for. `vr-009` x2 passed because the model left `ids` empty in all three runs. The plan expected those two to stay refused, and nothing in the bullet addresses them, so they are luck I can't claim.
- **Helped (raw wrong, checker refused): `dg-007` x3**, as before.
- **False passes: 6**, `mh-004` and `mh-005` in each run, as before. Incomplete lists of true facts, with R1 missing evidence.
- **Raw flips against the first run: one**, the `vr-002` parse failure above. Nothing else moved in either direction.
- **Fabricated IDs:** 0 of 120 raw and 0 of 120 checked. Abstention recall 8 of 8; over-abstention 6 of 32 raw, 8 of 32 checked.
- **Cost and time:** $0.0296 a query, about 13,000 tokens in and 360 out, median 2.8 s and p95 5.8 s with retrieval. Every stop reason was `end_turn`.

## What this says, and does not

- The mechanism worked: the model followed the addendum over `task.md` on the sources-disagree type, in all 24 replies. That was the main risk the plan named.
- The dev gain is real on these 40 questions, and it is fitted to them. The plan said so before the run and it stays true. It says little about the test split.
- One of the five conditions failed on a single reply with a formatting slip. That is a harsh reading, and it is the one the plan set. Changing the reading now, after seeing the result, would be a third look at the same dev set. If it is to be changed, it needs its own plan (a third plan), written with that in the open.
- The KEV half of the bullet is untested until Phase 5. If it hurts, the first sign will be on the test split.

## Not done

Everything the first results listed as not done, and the three items plan 2 left out: `lk-001`, `vr-009` and the six false passes.
