# Ledger: every look at development data

A reader judging a number on development data needs to know how many times I looked at that data before settling on it. This is the count. It starts on 16 November 2026 and covers the work before that date from the commit history. New entries are added when they happen, before the result is used.

A look is a run or analysis on development data whose outcome informed a decision. The development data is the 40 v1 dev questions (32 of them answerable) and, from the evidence round on, Dev-R. The test splits are listed separately.

## Looks at v1 dev data
| # | Date | Look | What it informed | Commits |
|---|---|---|---|---|
| 1 | 1 Nov 2026 | Baseline, 3 runs of the 40 questions, 120 calls, $0.70 | The size of the gap to look for. The baseline prompt stayed as written. | `092fc73` |
| 2 | 2 Nov 2026 | Retrieval ladder, rungs R0 to R8 on the 32 answerable questions. R8 ran three times, $0.10 for 96 calls. | Chose R1 and rejected the other eight rungs. Eight comparisons against R1. | `23a3e43`, `291733f`, `c604022` |
| 3 | 2 Nov 2026 | Generation smoke test, 5 questions, $0.22 | Plumbing only. No plan change. | `6af21f4` |
| 4 | 2 Nov 2026 | Generation plan 1, 3 runs of the 40 questions, $3.55 | The Phase 5 system and the checker's first known faults. | `d4c825b`, `266099a` |
| 5 | 2 Nov 2026 | Generation plan 2, 3 runs of the 40 questions, $3.55 | Tried one addendum bullet and did not adopt it. | `8e76c61`, `2ae2cc2`, `00495cf` |
| 6 | 2 Nov 2026 | Long-context smoke test, 5 questions | Plumbing for the long-context row. | `873a049` |
| 7 | 5 Nov 2026 | Checker fixes judged on the saved dev replies, with the red team replies | Three fixes accepted. Six dev rows recovered (30 of 40 in each run, was 27, 29 and 28). | `8fcde7e`, `060a8a8`, `d7aab24`, `f2866b1`, `b2f942c` |
| 8 | 8 Nov 2026 | Top 10 over the published text compared with the unreplaced text, for the 40 questions | Two questions differ (`vr-001`, `ab-005`). This led to the proposed amendment of live-search rule 3. | `466527b` |
| 9 | 8 Nov 2026 | Scan of every answerable dev question for how much of its evidence reached the top 10, to pick one for a demo GIF | Picked `vr-002`, where all 3 needed records are found. It was chosen to show a success, so it is not typical. The GIF says it is one dev question. | `f55f94f` |
| 10 | 16 Nov 2026 | R1's misses on the 32 answerable dev questions and the 88 answerable test questions, by type, by number of records, by whether the question names an ID and by whether it names one package, and the share of v1 questions that name a package. Descriptive, from saved results, no model. | Nothing chosen from it yet. It shows depth 20 holds all the evidence for 63 of 88 test questions against 53 at depth 10, and that sources-disagree questions gain nothing from depth. It led to Amendment 2 of the plan (post hoc): R1 at depth 20 became a candidate. | `docs/retrieval-descriptives.md` |
| 11 | 24 Nov 2026 | The completeness rule (`docs/completeness-spec-v1.md`) on the saved Phase 6 dev replies, 3 runs of 40. Descriptive, no model. | Nothing chosen from it. It withheld 3 of 120 replies, all the same question (`vr-002`, struts2-core, 126 records) in each run, and each one was a correct answer. Checked correct fell from 30 to 29 of 40 in every run, and no wrong answer was removed. 13 of the 18 packages hold more than 10 records, so the rule can pass only for the other 5. | `58f87d6` |
| 12 | 24 Nov 2026 | The dev generation check for R9 with the completeness rule, 3 runs of the 40 questions, 120 calls, $2.81 (`docs/generation-results-3.md`). | R9 passed rule 4: 33, 33 and 32 of 40 checked correct against 30 in each run, no parse failure, 6 wrong answers shown against 6, input tokens 0.77 of R1's. Four questions went from a decline to a correct answer, `vr-002` was withheld by the completeness rule, and the model refused `mh-001` in every run. R9 goes into the system the Test v2 run scores. | `1e2eb59` |

**Twelve looks at the v1 dev questions.** The model calls in them cost at least $10.93 (rows 1 to 5 and 12, without the long-context smoke test, whose cost is not in this sum). The other looks used no model.

## Looks at Dev-R
Dev-R is the retrieval-only dev set built for the evidence round (243 questions, tag `eval-freeze-retrieval-v1`). Apart from one count of question text, set out below, nothing on it was looked at before the run.

| # | Date | Look | What it informed | Commits |
|---|---|---|---|---|
| 1 | 17 Nov 2026 | Every candidate on Dev-R, once, with no model: R1 at depths 10, 15, 20 and 25, R9, R9x and R10, on all 243 questions. | Nothing adopted. R9 passed rules 1 to 3, on gold built from the links it follows, so its 179 of 179 is an upper bound. R11 gained 3 and failed the floor of 9. R10 was not judged, because 1 of the 179 main questions names a package. The dev generation check for R9 is not run and needs my yes and credit. | `64e826d`, `80bf709` |

**One look at Dev-R.** Before the run I counted, from the question text alone, how many Dev-R questions name one package (44 of 243, and 8 of the 191 in the main group). That is not a retrieval result, and it is why R10 was expected to be descriptive. The results file was reformatted to fit the 1 MB limit on committed files. Its content is the same.

## Other choices fitted on data I had already seen
These are not on the v1 dev questions, but they are choices made after looking at results, so a reader should know.
| Date | Choice | Why it is listed | Where |
|---|---|---|---|
| 3 Nov 2026 | The check that decides whether a reply obeyed an attack was changed after I read red team round 1. | The held-out set was the test of the change. | `7b0c66f` |
| 4 Nov 2026 | The poison builder gave npm records the wrong range type, and was fixed. A free replay of saved replies then moved one held-out row (`h-B2-2`). | Fixing after seeing a result. | `5445b54`, ADR 0010 |
| 5 Nov 2026 | The ingest check was refined on the real records: 16 of 588 flagged at first, 5 after the refinement. | Fitted on the real corpus, with no held-out set. | `57a78ed`, ADR 0011 |
| 5 Nov 2026 | A rule in ADR 0012 was amended for two held-out red team replies after I had seen them. | A rule changed after seeing numbers. | ADR 0012 |

## Test splits
- **Test v1 (110 questions)** was scored once, on 2 November 2026, from the tagged system `phase5-system-v1`. The faults I then read in the results (the pair rule, rule 7 and the `ids` use on a "no") were fixed afterwards and judged on saved dev and red team replies, not on test. That is why the split cannot be scored again.
- **Test v1 retrieval at depth 20.** I read R1's saved results on the test split at depth 20 (63 of 88 against 53 at depth 10, `eval/results/test-retrieval.json`), and it led to Amendment 2 of the plan (post hoc): R1 at depth 20 became a candidate to be judged on Dev-R. The numbers were published from the start. No test result decides the outcome.
- **Test v2 (109 questions)** is frozen and has not been scored by any system. Nothing here has been used to tune on it.

## What this ledger does not show
It does not show how many ideas I rejected before running them, or any look I forgot to record. The commit history is the check on it.
