# Test split results

Run on 2 November 2026 on the 110 test questions, once per row, from the tagged system `phase5-system-v1` (commit `d495e5a`), as fixed in [test-plan.md](test-plan.md) and [ADR 0007](adr/0007-score-the-test-split-once-from-a-tagged-system.md). Every row's raw output was committed before anything was scored or opened (`cdc3152`, `5bb01a2`, `7037d3c`, `1444f34`, `20a3c31`), and the scores come from those files by the committed scorer (`25306d2`). The test split was not used for tuning. Spend: $6.81 for the phase, including the dev smoke run.

Files are in `eval/results/`: `baseline-test.jsonl`, `test-structured-raw.jsonl`, `test-longcontext-raw.jsonl`, `test-retrieval.json`, `test-generation-raw.jsonl` and `test-generation-checked.jsonl`, each with a `.scored.jsonl` version, plus `test-per-question.csv` (every question, every row), `test-rows-analysis.json` and `test-generation-analysis.json`.

The system is G's checked reply. The raw reply is beside it.

## The short version

- **The system answers about half the answerable questions.** G, checked, is right on 66 of 110 questions (60%) and 44 of 88 answerable ones (50%). The no-retrieval baseline is 35 of 110 (32%) and 13 of 88 (15%). Where the system and the baseline disagree, the system wins 35 questions to 4.
- **Retrieval is the limit, not the model.** When R1 had all the evidence in its top 10 (53 of 88 answerable questions), the model's raw reply was right on 52. When R1 missed it (35 questions), the raw reply was right on 1. R1 found all the evidence for 60% of the answerable test questions, against 75% on dev.
- **The checker cost the system more than it gave.** It cost the system 9 of its 75 raw-correct answers: it refused 9 correct replies and withheld no wrong ones. It let 8 wrong replies through, all incomplete lists of true facts. There were no invented IDs in any row, so the repair and the fabrication guard never had work to do.
- **Two rows with no retrieval beat the system.** Code that reads the question's form and the store gets 99 of 110 (90%). The model with a whole package in front of it gets 42 of the 43 package-naming questions, where the system gets 24 (raw 31).
- **Nothing was invented anywhere.** Fabricated IDs: 0 of 110 in every row.

These are 110 questions, one run. Intervals are wide and the table gives them. The numbers describe this question set, which is templated, and not vulnerability questions in general.

## The six named comparisons

From [eval/rules.md](../eval/rules.md) section 8, the only ones given a headline.

| | System (checked) | System (raw) | Baseline |
|---|---|---|---|
| 1. Correct, all 110 | 66 (60%, 95% CI 51 to 69) | 75 (68%, 59 to 76) | 35 (32%, 24 to 41) |
| 2. Correct, 88 answerable | 44 (50%, 40 to 60) | 53 (60%, 50 to 70) | 13 (15%, 9 to 24) |
| 3. Fabricated IDs | 0 of 110 | 0 of 110 | 0 of 110 |
| 4. Abstention recall (22 should-abstain) | 22 of 22 | 22 of 22 | 22 of 22 |
| 4. Abstention precision | 22 of 58 (38%) | 22 of 49 (45%) | 22 of 91 (24%) |
| 4. Over-abstention (of 88 answerable) | 36 (41%) | 27 (31%) | 69 (78%) |
| 5. Sources-disagree correct (of 22) | 5 (23%) | 6 (27%) | 1 (5%) |
| 6. Baseline pre-cutoff / boundary / post-cutoff | | | 13 of 55 (24%) / 0 of 7 / 0 of 26 (0%) |

System against baseline, exact McNemar on the 110: the system is right and the baseline wrong on 35 questions, the reverse on 4 (p below 0.0001). For the raw reply, 42 against 2.

## Every row, by type

Correct, with 22, 22, 22, 18 and 26 questions. Row L covers only the 43 questions that name a package.

| Type | Baseline | Structured (S) | System raw | System checked | Long context (L) |
|---|---|---|---|---|---|
| Should-abstain (22) | 22 | 22 | 22 | 22 | not asked |
| Sources-disagree (22) | 1 | 22 | 6 | 5 | not asked |
| Direct lookup (22) | 4 | 11 | 20 | 18 | 9 of 9 |
| Multi-hop (18) | 2 | 18 | 8 | 7 | 7 of 8 |
| Version-affected (26) | 6 | 26 | 19 | 14 | 26 of 26 |
| **All (110)** | **35 (32%)** | **99 (90%)** | **75 (68%)** | **66 (60%)** | |
| **Answerable (88)** | **13 (15%)** | **77 (88%)** | **53 (60%)** | **44 (50%)** | |

On the 43 package-naming questions, every row side by side: baseline 8, structured 37, system raw 31, **system checked 24**, long context **42**. Against the checked system, long context is right on 18 questions the system gets wrong and wrong on none the system gets right (secondary comparison, 43 questions). Against structured lookups on all 110, the system wins 9 questions and loses 42.

Slices, answerable questions only:

| | Baseline | Structured | System raw | System checked | Long context |
|---|---|---|---|---|---|
| Pre-cutoff (55) | 13 | 49 | 30 | 26 | 25 of 26 |
| Boundary month (7) | 0 | 7 | 3 | 3 | 4 of 4 |
| Post-cutoff (26) | 0 | 21 | 20 | 15 | 13 of 13 |
| Stale-risk (6) | 0 | 6 | 1 | 1 | 6 of 6 |
| Maven RELEASE (5) | 3 | 5 | 3 | 3 | 5 of 5 |

The baseline's zero on the post-cutoff slice is the clearest effect of the evidence: the model cannot know records from after its training. The system gets 58% of that slice checked and 77% raw.

## Retrieval

R1 only, on the 88 answerable questions. The other rungs stay dev only.

| | Test | Dev |
|---|---|---|
| All the evidence in the top 10 | 53 of 88 (60%, CI 50 to 70) | 24 of 32 (75%, CI 58 to 87) |
| Top 5 / top 20 | 47 / 63 | |
| Mean recall at 10 | 0.77 | |
| B0 (every record of a named package) holds all evidence | 43 of 88 | 17 of 32 |
| B1 (records for IDs in the question) holds all evidence | 36 of 88 (ID named in 57) | 16 of 32 |
| KEV evidence recalled at 10 | 0.4 over 5 questions | |

R1 missed the evidence on 16 of 22 sources-disagree questions, 9 of 18 multi-hop, 8 of 26 version-affected and 2 of 22 lookup questions. The top 10 cannot hold a list answer of five or six advisories next to everything else a keyword search returns.

The system's behaviour follows from that. On the 27 answerable questions where R1 missed the evidence and the model abstained, it saw nothing relevant and said so. On 7 where it answered anyway, the checker passed an incomplete list. On the 53 where R1 had everything, the raw reply was right 52 times.

The retrieval row and the system used the same top 10 for all 88 questions (checked).

## The checker

| | Count |
|---|---|
| Replies passed | 52 (44 right, 8 wrong) |
| Refused by the checker | 9 |
| Refused by the gate (rule 1) | 15, all should-abstain; none of the 88 answerable |
| Abstained by the model | 34 (7 should-abstain, 27 over-abstentions, all where R1 missed) |
| Repaired (an invented ID cut out) | 0 |
| Parse failures / cut-off replies | 0 / 0 |

**False passes: 8 of 52 passed replies (85% of passed replies were right).** All eight are incomplete or wrongly chosen sets built from true claims: six of the version-affected "which advisories affect X" questions (the reply listed 1 to 5 of 3 to 6 advisories), one multi-hop intersection (4 of 6), and one published-first comparison where both dates were true and the wrong advisory was chosen. For seven of the eight, R1 had missed evidence. The checker checks each stated fact. It cannot see that a list is short.

**Helped: none.** The checker withheld no reply that was raw-wrong.

**Harmed (raw correct, checker refused): 9, each read by hand.**

| Question | Rule | What happened | Cause |
|---|---|---|---|
| `vr-029`, `vr-030`, `vr-031`, `vr-035` | 7 | The verdict "no" was right and backed by a true `affects: false` claim. The model also put the advisory named in the question into `ids`, and an ID in `ids` needs an `affects: true` claim. | The model used `ids` for an advisory it said does not apply, against the task text. The same pattern as `vr-009` on dev. |
| `lk-010`, `vr-024` | 6 | A true answer with an extra NVD `fixed_in` claim on a record that has no CPE rows, which the code cannot check. | A claim the store cannot check, behind a right answer. The same as `lk-001` on dev. |
| `dg-026` | 7 | The sources-disagree reply was right, and the model also set `verdict` to "no", which needs a `kev` claim. | The rule 7 gap found on dev ([generation-results-2.md](generation-results-2.md)). Version 1 was kept. |
| `mh-021` | 7 | The one advisory listed was right and came with no claim at all. | The model gave an answer and no claim, against the addendum. The refusal is the checker doing its job. |
| `lk-015` | 7 | The question describes an advisory "affecting Django 5.1 before 5.1.4". The checker read "Django 5.1" as a package-version pair and asked for an `affects` claim. | **A checker fault.** The pair rule matched a version range inside a description. |

Five of the nine have a cause the dev results had already shown. The `lk-015` fault is new.

**Nothing was fixed after the tag.** The tag froze `src/` and `scripts/`, and a fix after seeing test results would be tuning on test. The pair-reading fault (`lk-015`) and the rule 7 gap are reported here as they are. Changing either needs a new plan and a new tag, and whatever the new tag scores would not be a first look at the test split.

## The expectations written down before the run

| Expectation | What happened |
|---|---|
| Baseline answers about a third correct, invents at most one ID, scores zero post-cutoff | Right: 32%, no invented ID, 0 of 26 |
| System checked 60 to 75 percent | At the bottom: 60% (raw 68%) |
| Lookup and version do best | Lookup yes (82% checked). Version did not: 54% checked, 73% raw, hurt by the checker |
| Multi-hop and sources-disagree do worst, retrieval-limited | Yes: 39% and 23% checked |
| The checker costs a few correct answers and withholds a few wrong ones | It cost 9 and withheld none |
| False passes on multi-hop | Yes, and also on version sets |
| Fabricated IDs: zero or close to it | Zero |
| S does very well on the forms it reads, nothing on described advisories | Yes: 90%, and 11 of 22 lookups (the 11 described ones are declined) |
| L does well on small packages and less well on large | No: 42 of 43, including the largest packages |
| A KEV fault would show on test | 2 `kev` claims, both passed with a KEV unit shown; no KEV fault seen |

## Claims

Counted over the replies that reached the claim rules.

| Kind | Passed | Unverifiable |
|---|---|---|
| `affects` | 51 | 0 |
| `package` | 63 | 0 |
| `alias` | 28 | 0 |
| `score` | 16 | 0 |
| `severity` | 14 | 0 |
| `published` | 7 | 0 |
| `fixed_in` | 4 | 2 |
| `kev` | 2 | 0 |

No claim failed outright. Every wrong reply the checker passed or refused was a missing or unverifiable claim, never a false one.

## Cost and time

| Row | Spend | Per query | Median / p95 |
|---|---|---|---|
| Baseline | $0.60 | $0.0054 | 2.3 s / 9.2 s |
| Structured | $0 | $0 | under 1 ms |
| Long context (43 questions) | $2.67 | $0.0621 | 4.7 s / 9.4 s |
| System (retrieval included) | $3.33 | $0.0303 | 3.1 s / 6.3 s (about 13,300 tokens in, 360 out) |
| Retrieval alone | $0 | | 2.6 ms / 4.4 ms |

Long context cost twice as much per question as the system, with prompt caching on. Without it the estimate was about $7. Latency is on this machine.

## The hand spot-check

The plan had Joe mark 24 replies (18 from the system, 6 from the baseline) blind to the scorer, the checker and the row. Joe asked me to do it instead, so **these marks are mine, not Joe's**, and the check is weaker for it. I marked each reply from the question and the store before looking at the scorer's verdict on any of the 24, and committed the marks first (`9552699`, `eval/results/spotcheck-marks.json`).

**Agreement with the scorer: 24 of 24** (18 of 18 for the system, 6 of 6 for the baseline). Of the 24, I judged 14 right and 10 wrong: nine answerable questions that were declined, and one incomplete list. There is nothing to set against the gold from this sample, and no errata.

What this does not show: I wrote the system and read the same store the checker reads, so a fault in the store would pass both. The sheet of 24 is still at `eval/results/spotcheck-sheet-test.html`, and Joe's own marks would be the check the plan meant.

## What this does and does not say

- The measured gain from retrieval is real on this question set: 15% to 50% on answerable questions, and from 0 to 58% on questions about records after the model's training.
- The headline design, retrieve ten records and let a checker police the answer, is limited by the ten. A model given the whole package gets nearly everything right on the package-naming questions, at twice the cost, and a database query beats both on the templated forms. The checker's guarantee (no invented ID, no wrong version, score or label reaches the reader) held, but there was nothing for it to catch: the model invented no ID in any test row.
- Row S is high because the questions are templated. It shows how much of this set needs no model. It does not show the same of real questions.
- Two checker faults are known and not fixed, and a third issue (the model listing an advisory in `ids` on a "no") accounts for four refusals. A second round on test is not available: the split was scored once.

## Not covered

The attack tests and the demo (Phases 6 and 7), the other rungs of the ladder on test, and Joe's own spot-check marks.
