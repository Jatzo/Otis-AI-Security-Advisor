# Plan: a bounded evidence round

Status: approved on 16 November 2026, with the six decisions at the end. Written before anything in it has run, and revised the same day after an independent review. Nothing in it has run.

## In short
[ADR 0014](adr/0014-close-the-project-as-a-portfolio-piece-and-record-where-it-misses-the-bar.md) closed Otis as a portfolio piece. I am reopening it for one bounded round, to make the evidence stronger without making the reporting less honest. The aim is that a reader trusts the numbers more afterwards, the negative ones included.

The work is the three things the documents already name, plus the checks a sceptical reader would run first:
1. The retrieval weakness on multi-hop and sources-disagree questions, which ADR 0005 calls the open problem.
2. The live search that [live-search-plan.md](live-search-plan.md) started.
3. The larger run on Test v2, which needs credit.

The round ends on **30 November 2026**. Step 4 depends on credit and may be deferred past that date. Any other extension needs a written amendment to this plan.

## What a sceptic attacks first, and what this round does about it
| Weakness | Where it shows | What this round does |
|---|---|---|
| The tuning set is 32 answerable questions, looked at many times. | 9 retrieval rungs, 3 generation runs, a second addendum plan and the checker fixes all used it. The rule in ADR 0005 needs about 6 questions to move one way and none the other. | A new, larger, retrieval-only dev set (Dev-R), so retrieval is tuned on questions I have not studied. A ledger of every look taken so far. |
| Test v2 has no dev part, so there is nowhere safe to develop a fix. | ADR 0009: "tuning stays on the v1 dev split". | Dev-R is that place, and Test v2 stays untouched until step 4. |
| The Test v2 gold has no recorded line-by-line review. | `PROGRESS.md`. v1 had one. | I read all 109 rows before any scoring, and a second person does a blind sample. Corrections are appended as errata. |
| "Retrieval is the limit" is a conditional reading. | Right 52 times in 53 when retrieval hit, 1 in 35 when it missed. Questions that retrieval hits may simply be easier. | An oracle row on Test v2, if I can fund it. Until then the README says "associated with", not "caused by". |
| The system's own version comparator has an open fault. | `test_maven_order_is_transitive` fails on `'0'`, `'b'`, `'0b0'`. The gold does not use that comparator (the real Maven jar has the last word in `eval/build_questions.py`), but the checker does. | It is the first task, checked against the Maven jar, followed by a check of which saved checker results depended on it. |
| README figures are copied by hand. | The 1,164 against 1,174 wording in the GIF. | `scripts/check_claims.py` ties each README figure to the raw results, and CI runs it. |
| One author, one model, one run on test. | `eval/rules.md`, ADR 0009. | The limits stay in "What I would not trust". The flip rate across the three dev runs is reported. |

## Rules that hold for the whole round
- Each frozen system scores a test split once. Nothing under `eval/` or `eval-v2/` changes except under a new freeze tag or as appended errata. No protected tag is moved.
- Every experiment has its plan, candidates, code and adoption rule committed before it runs. A rule changed after I have seen numbers is recorded as an amendment, marked post hoc, and the README says so.
- A result is reported whatever it shows. A null or negative result gets the same place and the same detail as a positive one.
- **Corrections.** A published figure found wrong is corrected in the open: the fix is committed with a line in `docs/corrections.md` saying what was wrong, since when, and the new figure. Old results are not edited silently.
- Nothing that costs money, calls a model or is hard to undo happens without my yes. Each ask states the likely cost and the alternative.
- No secrets, email addresses or example credentials in published data. The README's "What I would not trust" is updated at every checkpoint.
- Pushes only on my yes, spaced out. Commit messages are in first person, short, with the test count.

## Step 0: reopen, and write down every look so far (no cost)
- ADR 0016 reopens the project for this round, names what ends it and what it does not change.
- `docs/ledger.md` lists every look taken at dev data so far, each with its commit: rungs R0 to R8, the three dev generation runs, plan 2, the checker fixes judged on saved dev replies, the ingest-check refinement fitted on real records. It states the number of looks, so a reader can judge how much the dev numbers can bear.
- The README banner changes from "closed" to "reopened until 30 November 2026 for a bounded round (ADR 0016)".
- The live-search ADR is renumbered to 0017.

## Step 1: make the instrument checkable (no cost)
1. **The Maven order failure.** Reproduce it. Check what Maven 3.9.9's own `ComparableVersion` returns for the three strings, using the jar and Java 17 as ADR 0003 does. If Maven gives the same result, the port is faithful and the test's property is too strong, so I narrow it and say why. If Maven differs, I fix the port with a regression test. Then check which saved checker results, if any, depended on the ordering. `docs/debug-log.md` gets the entry. Frozen files are not touched. If one is affected, I report it.
2. **The Test v2 gold review.** I read all 109 rows of `eval-v2/review.md` against the records. A second person, who must be a person and not a model, reviews 30 rows picked by a seeded draw, stratified by type, with sources-disagree and Maven over-sampled. They are shown the question and the record extracts first and write their own answer. Then the gold is shown, and they mark agree, disagree or can't tell, with a reason. This avoids both weaknesses of the v1 spot-check: a sheet that hid the gold, and marks that were not mine. Zero disagreements in 30 still allows an error rate of about 10%, and the write-up says so. If no second person is available, the item is dropped and the write-up says so. Corrections are appended to `eval-v2/errata.jsonl` before any system sees the questions. The scorer reports every figure twice, as frozen and with errata, as `eval/rules.md` section 9 says.
3. **`scripts/check_claims.py`.** A list, kept outside the frozen folders, of every figure in the README and the results documents that states a count, with the source file and the computation behind it. Each source is pinned by blob hash or commit, because `eval/results/` is not frozen. Counts that need the ignored store are computed from committed files, for example the unit counts from `docs/demo/corpus.json`, or marked local only. A coverage check fails if any number in the README is missing from the list. Images, such as the GIF, cannot be checked, so they are listed as manual. CI runs the script.
4. **A pool count for Dev-R.** A committed script that calls no retrieval and no model, and reports for each question type and subtype how many question candidates exist that are disjoint from Test v1 and from Test v2, with and without the advisories only v1 dev used.
5. **R1's misses, broken down.** On data already scored (v1 dev and test retrieval), a descriptive table of R1's misses by question type, by number of evidence records, and by whether the question names an ID. It is recorded in the ledger as a look.

Checkpoint 1 shows: the ledger, ADR 0016, the Maven result with the oracle's output, the gold review counts, the pool count and `check_claims.py` passing.

## Step 2: retrieval study 2 (no model calls, no cost)
**The question.** Does bringing the linked records with a retrieved advisory raise how often all the needed evidence reaches the model, on questions that need two or more records, without hurting the questions that need one?

**What it can and cannot show.** The question generator builds the gold evidence from the same GitHub and NVD links that the candidate follows. On template questions that name an ID, a candidate that follows those links will mostly measure that the link exists. So a gain on Dev-R is an upper bound on what the links can do for real questions, and only a generation run shows whether answers improve. Results are split by whether the question names an ID.

**Dev-R, the new development set.**
- It lives in `eval-retrieval/` under its own tag, `eval-freeze-retrieval-v1`, held by a guard like the Test v2 one. The tag name matches the repository ruleset for `eval-freeze-*` and does not match the v1 guard's pattern.
- It is built by `eval-retrieval/build_questions.py`, a wrapper like `eval-v2/build_questions.py` that reuses the generators in `eval/` unchanged. It has its own `SLOTS`, fixed after the pool count in step 1 and before the build, a new seed (20261116), and no fallback to reuse.
- **Eligible subjects.** Advisories that no Test v1 question and no Test v2 question is about. Advisories used only by v1 dev are eligible, flagged `seen_dev` and reported as their own slice. Primary analysis uses unflagged questions only, if that stratum has enough questions (see the rule below). Otherwise it uses both, and the flagged slice is reported separately.
- **Types.** Lookup, version-affected, multi-hop and sources-disagree. No should-abstain questions, because nothing is retrieved for them. Wording is the v1 template wording, so Dev-R does not test reworded questions. Test v2's free-form questions do that, in step 4.
- **Gaps stated in advance.** Test v2 already ran out of fresh advisories for some kinds (it reused v1 advisories for 8 questions and was one KEV set question short). So Dev-R may have few or no KEV multi-hop questions and few version-set questions. If so, the KEV link cannot be tested on Dev-R, no KEV claim is made, and the do-no-harm slices are reported with their counts.
- **Built once.** One committed commit holds the build script, the seed, `SLOTS`, the candidate code and the run script. Dev-R is then built once and its output hash is recorded. All candidates run in one committed script. Nothing is run on Dev-R before that commit.

**The candidate and the controls.**
- **Control, R1:** keyword search over records with a header, top 10.
- **Candidate, R9, linked records within 10.** Walk R1's ranking from the top. Append each unit if it is not already in the output. Then append its linked units, if not already in the output, in sorted ID order: for a GitHub advisory, the NVD record of each CVE in its aliases, then the KEV entry for those CVEs. For an NVD record, the GitHub advisories that alias its CVE. For a KEV entry, the NVD record and those advisories. Stop at 10 records.
- **Descriptive only, no adoption:** R1 at depths 10, 15, 20 and 25 with input tokens, and R9x, which appends linked units beyond 10 up to 20. They show what a deeper list buys and costs. They cannot lose a question, so a test of them would prove nothing.

**Measures.** Primary: all-evidence at 10 on the primary stratum, which is the questions that need two or more records (multi-hop, sources-disagree and version-set). Secondary: lookups (one record), mean recall, and each figure by question type and by whether the question names an ID.

**Adoption rule for R9, fixed now.**
1. The primary stratum has at least 140 questions. If it has fewer, the result is descriptive and the rule below is not applied.
2. R9 beats R1 by at least the larger of 5 percentage points and 6 questions, with exact two-sided McNemar p below 0.05. With one candidate there is no correction. Six questions moving one way and none the other is the least that can reach it.
3. Do no harm: on each slice, R9 loses at most 1 question, and at most 1 percentage point on the whole set.
4. If R9 passes, it earns the dev generation check and nothing more. It enters a system only if the check passes: three runs on the 40 v1 dev questions with checked correct at least 30 of 40 in each run (the Phase 6 figure), no parse failure, and mean input tokens at most 1.3 times R1's. The check costs about $3.55 and needs my yes.
5. If R9 fails, the result is reported in full as a negative one, and the README lists linked-record retrieval as tested and not adopted.

Checkpoint 2 shows: the committed build, Dev-R's size and counts, and the run script before it runs. Checkpoint 3 shows the results table, whichever way it goes.

## Step 3: the live search (no cost)
Steps 2 to 5 of [live-search-plan.md](live-search-plan.md), with these changes:
- Rule 3 is amended as proposed there: the live list equals the saved list for 38 of 40 dev questions, and `vr-001` and `ab-005` are named exceptions.
- The page says plainly that it is retrieval only, shows dev questions only, and shows the snapshot date and which search it runs.
- If R9 is adopted into a system, the page offers it beside R1. Otherwise it shows R1 only.

## Step 4: the Test v2 run (costs money, one yes per spend)
**First, before any v2 question is scored,** `docs/test-v2-plan.md` is written and committed. It fixes the arms, the predictions, the analysis and the spend cap. The runner and scorer change to read `eval-v2/` under their own freeze tag, with the reason recorded, as ADR 0009 says. I do not look at which v2 questions R1 misses before the predictions are committed.

**Arms.** Each is scored once, in this order.
1. **Base rows:** the baseline, structured lookups, long context, retrieval alone (R1 on Test v2) and `phase6-system-v1`. About $7.
2. **Oracle row, open until funded.** R1's list is kept. Any gold evidence record it is missing replaces the lowest-ranked record that is not gold. For should-abstain questions the list is R1's, unchanged. The analysis is on the questions where R1 missed evidence, about 35 of the 89 answerable. About $3.3. It tests how much of the gap is retrieval, without moving the evidence to the top of the prompt.
3. **New-system arm,** only if R9 passed step 2 and its dev generation check. A tagged system with that retrieval, paired with `phase6-system-v1` on the same questions. About $3.3. With 109 questions it can show a direction and an interval, not proof of a small gain, and the plan says so in advance.

**Headline comparisons.** The six named in `eval/rules.md` section 8, as `eval-v2/rules.md` says. Two more are pre-registered as secondary, and an ADR records them as added after the freeze: the system against the baseline on the answerable questions (replication on fresh data), and the system against structured lookups on the 54 free-form questions. The rule that the retrieval ladder is compared on dev only still holds. Retrieval on Test v2 appears only as a row of the system arms.

**Spend.** A hard cap for the whole step, an ask before each row, retries off as now, and the provider's own spend limit set to the cap. Spend is written into a committed ledger.

**Not planned:** red team round 2 ($9.5). It is the README's largest open limit and it is the next round.

## Step 5: write-up
The README, the results documents and "What I would not trust" are updated with every result, null and negative ones included, and the ledger count is shown. The LinkedIn post is updated to match, and the README banner is set to its final wording.

## What ends the round
- Steps 0 to 3 and 5 are done and written up by 30 November 2026. Step 4 is done if credit is there. If it is not, it is deferred and named in the README, and the round still counts as complete.
- Or no candidate passes step 2, or Dev-R is too small. Then the result is reported as null or descriptive, and the round ends.
- Or I stop it. The README says why.

## What this round will not do
- Report a gain on the v1 test split, which was scored once.
- Tune on Test v2, or on any question set I have not frozen first.
- Replace a published number silently. New results go beside the old ones, and corrections follow the rule above.
- Add a defence or a retrieval change because it sounds right.

## Cost
| Step | Model calls | Cost |
|---|---|---|
| 0 to 3 | none | $0 |
| 2, dev generation check, only if R9 passes | 120 calls | about $3.55 (£2.66) |
| 4, base rows | the five rows | about $7 (£5.24) |
| 4, oracle row | one system row | about $3.3 (£2.47) |
| 4, new-system arm | one system row | about $3.3 (£2.47) |

About $0.74 (£0.55) of credit is left. Conversions are at 0.748 pounds to the dollar on 9 November 2026.

## Decisions taken on 16 November 2026
1. **Step 4 arms.** The base rows first (about $7). Then the oracle row if funded. The new-system arm only if R9 passes step 2 and its dev generation check. Each spend still needs its own yes.
2. **Live-search rule 3.** Amended as proposed: the live list equals the saved list for 38 of 40 dev questions, and `vr-001` and `ab-005` are the named exceptions.
3. **The Maven investigation** starts as soon as step 0 is committed.
4. **The second person for the 30-row gold sample.** Still to be found. If nobody is available by the time step 1 is checkpointed, the item is dropped and the write-up says so.
5. **The end date** is 30 November 2026.
6. **v1 dev advisories** may enter Dev-R as a flagged `seen_dev` slice, as drafted above.
