# Generation and checker: dev results

Run on 2 November 2026 on the 40 dev questions, 3 runs, as fixed in [generation-plan.md](generation-plan.md). Commit `c48742b` with a clean tree, `eval-freeze-v1` unchanged. Task and addendum are hashed on every result line (`task.md` `cfcd4c7`, `addendum.md` `b668665`). Model `claude-sonnet-5-5`, effort high, 16000 output tokens, evidence from R1 (top 10 units, whole). 120 calls, 120 attempts, $3.55. The test split was not touched.

The plan's rules were not changed after seeing a score. Amendments: none. One finding below needs a new plan, and that is Joe's call.

Files: `eval/results/generation-dev-raw.jsonl` (the reply as it came), `generation-dev-checked.jsonl` (after the checker), their `.scored.jsonl` versions from `eval/score.py`, and `generation-dev-analysis.json` from `scripts/analyse_generation.py`. A smoke run on 5 questions came first ($0.22, `generation-smoke-dev-*`) and found no plumbing fault.

## The short version

- The evidence is what moved the score. Raw replies are right on 31 of 40 questions in all three runs, and on 23 of 32 answerable ones. The no-retrieval baseline was 15 of 40 and 7 of 32.
- The checker did not add to that on dev. Checked replies are right on 27, 29 and 28 of 40 (19, 21 and 20 of 32 answerable). It withheld 3 wrong replies and let 6 wrong ones through. It also refused 9 replies that were right. The raw model invented no ID in 120 replies, so the checker's cut-out repair never ran on real data, and its fabrication guarantee was not tested by it.
- All 6 wrong replies it let through are multi-hop, where every claim was true and the answer was incomplete. That is the blind spot the plan named.
- 4 of the 9 right replies it refused come from a rule that does not fit questions that are not about KEV or a version pair (below).

These are counts on 40 questions from one run of three that gave almost identical results. They show what happened here. They are not a rate for the test split.

## Correct, by type

Each cell is the count in runs 1, 2 and 3. Intervals from `eval/score.py` are wide: for example raw 31/40 is 78% (95% CI 62 to 88), checked run 1 is 27/40 (52 to 80).

| Type | Questions | Raw | Checked | Baseline |
|---|---|---|---|---|
| Direct lookup | 8 | 8, 8, 8 | 7, 7, 7 | 0 |
| Version-affected | 9 | 9, 9, 9 | 8, 9, 8 | 4 |
| Multi-hop | 7 | 2, 2, 2 | 2, 2, 2 | 1 |
| Should-abstain | 8 | 8, 8, 8 | 8, 8, 8 | 8 |
| Sources-disagree | 8 | 4, 4, 4 | 2, 3, 3 | 2 |
| **All** | 40 | 31, 31, 31 | 27, 29, 28 | 15 |
| **Answerable** | 32 | 23, 23, 23 | 19, 21, 20 | 7 |

Same outcome in all three runs: 40 of 40 questions raw, 38 of 40 checked (`dg-001` and `vr-009` changed).

Expected before the run, and it held: multi-hop and sources-disagree did worst. R1 had all the evidence in its top 10 for 2 of 7 multi-hop and 5 of 8 sources-disagree questions, so those two lines are retrieval-limited.

The raw row differs from the baseline in four things at once: the evidence, the addendum, the claims field and (for the checked row) the checker. The cost of asking for claims is not separated from the effect of the evidence.

## Retrieval against the answer

Each row is one question in one run. The checked reply is the one scored.

| | Checked correct | Checked wrong |
|---|---|---|
| R1 had all the evidence (24 questions, 72 rows) | 60 | 12 |
| R1 missed evidence (8 questions, 24 rows) | 0 | 24 |

The 24 rows with a retrieval miss are `dg-002`, `dg-005`, `dg-008`, `mh-001` to `mh-005`. The model abstained on six of those eight questions in every run, which is the over-abstention in the next table, and gave an incomplete answer on `mh-004` and `mh-005`. Of the 12 wrong rows with all the evidence in hand, 3 are a wrong raw answer (`dg-007`) and 9 are replies the checker refused although they were right.

## Abstention

Counts are per run for the first two rows, then rows pooled over the three runs for the routes.

| | Raw | Checked |
|---|---|---|
| Abstention recall (8 should-abstain) | 8/8 each run | 8/8 each run |
| Abstention precision | 8/14 each run | 8/19, 8/17, 8/18 |
| Over-abstention (32 answerable) | 6/32 each run | 11, 9, 10 of 32 |

| Route | Rows | Should have abstained | Questions |
|---|---|---|---|
| Gate (rule 1) | 12 | 12 | `ab-001`, `ab-002`, `ab-005`, `ab-008` |
| Model | 30 | 12 | 4 should-abstain, 6 over-abstentions on retrieval misses |
| Checker | 12 | 0 | `dg-001`, `dg-003`, `dg-007`, `lk-001`, `vr-009` |

The gate fired on 4 of the 8 should-abstain questions and none of the 32 answerable ones, as the plan said. It changed no score on dev, because the model also abstained on all four. `ab-006` and `ab-007` (a real ID, a field the corpus lacks) were met by the model alone in every run. None of the checker's 12 refusals was on a should-abstain question.

## False passes, harmed and helped

**False passes: 6 of 66 passed replies (91% of passed replies were right).** All six are multi-hop, `mh-004` and `mh-005` in each run. Both are "of the advisories that apply to this version, which does GitHub rate critical or high". The model listed 1 of 3 and 2 of 3 gold advisories. Every claim was true (`package`, `affects`, `severity`), so the checker passed them. R1 had missed evidence on both. The raw model did not abstain, and nothing in the checker can see that a list is incomplete.

**Helped (raw wrong, checked refused): 3 rows, all `dg-007`.** The question is whether GitHub and NVD agree on the first fixed version of CVE-2014-0112. The model took the "before 2.3.20" in NVD's description as NVD's fixed version and said they agree, with a `fixed_in` claim for NVD of 2.3.20. NVD's own CPE data says 2.3.16.2, so the claim failed rule 6. The score did not change (a refusal on an answerable question is wrong), but a wrong answer was withheld.

**Harmed (raw correct, checked refused): 9 rows over 4 questions.** Each read by hand.

| Question | Rows | Rule | What happened | Cause |
|---|---|---|---|---|
| `lk-001` | 3 | 6 | The value 3.14.4 was right and backed by a passing GitHub claim. The model added a second `fixed_in` claim for the NVD record of CVE-2026-111749, which is still "Undergoing Analysis" and has no CPE rows. | A claim the store cannot check, behind a right answer. Not a wrong claim. |
| `dg-003` | 3 | 7 | Scores 8.6 and 5.9, flagged true, all claims passed. The model also set `verdict` to "no". | Rule 7 gap (below) |
| `dg-001` | 1 | 7 | Same, with `verdict` "yes". In runs 2 and 3 the model left `verdict` null and the reply passed. | Rule 7 gap (below) |
| `vr-009` | 2 | 7 | Verdict "no", correct, with a true `affects` claim of `affected: false`. The model also listed the advisory in `ids`, and an ID in `ids` needs an `affects` claim of true. In run 2 `ids` was empty and the reply passed. | The model used `ids` for an advisory it named only to explain, against the task text. The refusal is defensible. |

**The rule 7 gap.** For a `verdict` with no package-version pair in the question, the plan asks for a passing `kev` claim. That assumes the question is about KEV. A question about whether two sources put a CVE in the same band has no pair and no KEV claim, so a `verdict` the model adds beside a correct `disagreement` is refused. The scored field was right. This is how the rule is written, not a coding fault, so I did not change it. A change would be a new plan. The choices I can see: leave the rule and report it; have the checker ignore a `verdict` unless the question has a pair or mentions KEV (the checker would then read a word of the question, which the plan rules out); or tell the model in the addendum to leave `verdict` null on those questions (a prompt change, and it needs a paid rerun). None is made.

Nothing was fixed with `--recheck`, because no checker fault was found.

## Fabricated IDs

| | Replies with a nonexistent ID |
|---|---|
| Raw, scored fields and explanation (as the baseline was scanned) | 0 of 120 |
| Raw, claims included | 0 of 120 |
| Checked, claims included | 0 of 120 |
| Baseline, for comparison | 1 of 120 |

IDs cut out by the repair: 0. The repair, the grounding rule and the "text inside a record grounds nothing" rule are covered by the tests and not by these runs. The invariant that a checked reply holds no ID the evidence did not is held by a test and by this result.

## Claims

Counted over the replies that reached the claim rules (answers, and refusals at rules 4 to 7). Abstentions carry no claims that were read.

| Kind | Passed | Failed | Unverifiable |
|---|---|---|---|
| `affects` | 71 | 0 | 0 |
| `alias` | 34 | 0 | 0 |
| `fixed_in` | 20 | 3 | 3 |
| `package` | 77 | 0 | 0 |
| `published` | 6 | 0 | 0 |
| `score` | 24 | 0 | 0 |
| `severity` | 12 | 0 | 0 |
| `kev` | 0 | 0 | 0 |

- Refusals by rule: rule 6, 6 rows (3 failed, 3 unverifiable); rule 7, 6 rows. None at rules 2, 3, 4, 5 or 8 on real replies.
- The model made no `kev` claim in 120 replies. The KEV questions (`mh-002`, `mh-003`) were abstained on, because R1 had not retrieved them. So the KEV check, and the finding that a KEV claim can pass with no KEV unit shown, are tested by the suite only.
- Every `score` claim passed, so the difference between the store's computed GitHub score and the REST score the gold reads did not show up.
- Verdicts whose polarity is not held to the claim (wording other than "affected" or "vulnerable"): 0.
- Parse failures 0, replies cut by the token limit 0, refusals by the model 0. Every stop reason was `end_turn`.

## Cost and time

| | Value |
|---|---|
| Spend | $3.55 for 120 calls, $0.0296 a query. Phase 4 so far $3.77 of the $12 cap. |
| Tokens a query | about 12,900 in and 380 out (the plan guessed 9,000 and 1,500) |
| Latency, retrieval included | median 2.8 s, p95 6.9 s |
| Baseline | $0.0058 a query, median 2.4 s |

## What the checker cannot see, and what this run says about it

- It checks that each stated fact is true of the record cited. It cannot see that a list is incomplete. That is the six false passes.
- It cannot see that the claims, taken together, give the conclusion, or that the record cited is the one a worded question meant. None of the wrong replies here came from that.
- A true claim it cannot check is refused (3 rows), and a true answer with one extra claim of that kind is lost with it.

## Not done

- Test split, long-context and structured-lookup rows: Phase 5.
- A run with evidence and no `claims` field.
- Linking an advisory to its NVD record and KEV entry, which would target the multi-hop and sources-disagree misses. It needs its own plan.
- Attacks through advisory text: Phase 6.
