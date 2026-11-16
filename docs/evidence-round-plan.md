# Plan: a bounded evidence round

Status: approved on 16 November 2026, with the six decisions at the end. Written before anything in it has run, and revised the same day after an independent review. Amended the same day (Amendment 1, listed at the end) to add accuracy targets, a second retrieval candidate and a check for list answers. Nothing in it has run, apart from the free pool count in step 1.

## In short
[ADR 0014](adr/0014-close-the-project-as-a-portfolio-piece-and-record-where-it-misses-the-bar.md) closed Otis as a portfolio piece. I am reopening it for one bounded round, to make the evidence stronger without making the reporting less honest. The aim is that a reader trusts the numbers more afterwards, the negative ones included.

The work is the three things the documents already name, plus the checks a sceptical reader would run first:
1. The retrieval weakness on multi-hop and sources-disagree questions, which ADR 0005 calls the open problem.
2. The live search that [live-search-plan.md](live-search-plan.md) started.
3. The larger run on Test v2, which needs credit.

**The targets.** The round is also aimed at a reliable tool, so I am writing down now what I would call good enough, before I know whether it can be reached. Both are measured once, on the checked system, on Test v2:
- **Coverage:** right on at least 72 of the 89 answerable questions (81%). On Test v1 the checked system was right on 44 of 88 (50%).
- **Reliability:** at most 1 delivered answer in 20 is wrong. On Test v1 it was 8 wrong of 52 delivered (15%), counting every answer shown that was not right.

The targets are not adoption rules and do not change them. A **delivered** answer is any reply shown to the user, not a decline and not a reply the checker refused, counted over all 109 Test v2 questions including the should-abstain ones, where any answer shown is wrong. **Wrong** is any delivered answer scored not right. I do not know how many answers will be delivered. Assuming about 80, 0 wrong would show the rate is below 5% (95% upper limit 4.5%), and 4 wrong would allow up to 12.3%, so the target can be shown only by a near-perfect run and otherwise only approached. The write-up gives the counts, the interval and the words "met" or "not met" on the point figure, with the interval beside it.

The round ends on **30 November 2026** for the steps that cost nothing (0 to 3 and 5). Step 4 depends on credit and may be deferred past that date. Any other extension needs a written amendment to this plan.

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
4. **A pool count for Dev-R.** A committed script that calls no retrieval and no model, and reports for each question type and subtype how many question candidates exist that are disjoint from Test v1 and from Test v2, with and without the advisories only v1 dev used. **Done:** `scripts/count_dev_r_pool.py` and [dev-r-pool.md](dev-r-pool.md). The disjoint pool has 0 KEV-ID, 0 version-set, 0 KEV multi-hop and 1 intersect question. The kinds that need a list or the KEV link are therefore close to empty outside the `seen_dev` slice (6 version-set, 3 KEV multi-hop, 13 intersect).
5. **R1's misses, broken down.** On data already scored (v1 dev and test retrieval), a descriptive table of R1's misses by question type, by number of evidence records, and by whether the question names an ID. It is recorded in the ledger as a look.
6. **Package sizes and the package-naming share.** From `docs/demo/corpus.json` and the question text, with no retrieval and no model: how many records each of the 18 packages has, and what share of the v1 questions name exactly one package. Test v2 question text is not used, so nothing about Test v2 shapes a candidate. The cap for candidate R10 is fixed now at N = 20, so this item only reports sizes and says how many Dev-R questions R10 can be expected to change. Recorded in the ledger as a look at v1 question text only.
7. **A reserve for a later test.** At least 283 advisories are unused by Test v1, Test v1 dev and Test v2 (588 less 127, 48 and 130, before any overlap). Before Dev-R is built, a seeded split (seed 20261116) puts half of them in Dev-R's eligible set and half in a reserve for a future Test v3. The reserve list and its sha256 are committed and the reserve is not read again until Test v3 is planned. Without this, Dev-R would use up the only fresh advisories left. The reserve has the same gap: it will hold few or no KEV multi-hop or version-set questions.

Checkpoint 1 shows: the ledger, ADR 0016, the Maven result with the oracle's output, the gold review counts, the pool count, the package sizes, the reserve hash and `check_claims.py` passing.

## Step 2: retrieval study 2 (no model calls, no cost)
**The questions.** Two, one per candidate, each asked on its own.
- Does bringing the linked records with a retrieved advisory (R9) raise how often all the needed evidence reaches the model, on questions that need two or more records, without hurting the questions that need one?
- Does handing the model the records of the package the question names (R10) do the same, at a depth that costs no more than twice R1's?

**What it can and cannot show.** The question generator builds the gold evidence from the same GitHub and NVD links that R9 follows. On template questions that name an ID, a candidate that follows those links will mostly measure that the link exists. So a gain on Dev-R is an upper bound on what the links can do for real questions, and only a generation run shows whether answers improve. Results are split by whether the question names an ID.

R10 helps most where a question names a package and asks for a list, and Dev-R has almost none of those (step 1, item 4). So R10 may show little on Dev-R even if it would help on real list questions. I am saying so now. A null on Dev-R is reported as "not shown on the questions available", not as "does not work". The `seen_dev` slice is where the few list questions are, and it carries no adoption claim.

**Dev-R, the new development set.**
- It lives in `eval-retrieval/` under its own tag, `eval-freeze-retrieval-v1`, held by a guard like the Test v2 one. The tag name matches the repository ruleset for `eval-freeze-*` and does not match the v1 guard's pattern.
- It is built by `eval-retrieval/build_questions.py`, a wrapper like `eval-v2/build_questions.py` that reuses the generators in `eval/` unchanged. It has its own `SLOTS`, fixed after the pool count in step 1 and before the build, a new seed (20261116), and no fallback to reuse.
- **Eligible subjects.** Advisories that no Test v1 question and no Test v2 question is about, and that the reserve split (step 1, item 7) did not put in the reserve. The pool count in `docs/dev-r-pool.md` was taken before that split, so it is re-run on the post-split pool before `SLOTS` are fixed. The 140-question minimum below is judged on the post-split pool, and the split halves the advisories, so I expect it to be harder to reach and say so now. Advisories used only by v1 dev are eligible, flagged `seen_dev` and reported as their own slice. Primary analysis uses unflagged questions only, if that stratum has enough questions (see the rule below). Otherwise it uses both, and the flagged slice is reported separately.
- **Types.** Lookup, version-affected, multi-hop and sources-disagree. No should-abstain questions, because nothing is retrieved for them. Wording is the v1 template wording, so Dev-R does not test reworded questions. Test v2's free-form questions do that, in step 4.
- **Gaps stated in advance.** Test v2 already ran out of fresh advisories for some kinds (it reused v1 advisories for 8 questions and was one KEV set question short). So Dev-R may have few or no KEV multi-hop questions and few version-set questions. If so, the KEV link cannot be tested on Dev-R, no KEV claim is made, and the do-no-harm slices are reported with their counts.
- **Built once.** One committed commit holds the build script, the seed, `SLOTS`, the reserve split, the candidate code and the run script. Dev-R is then built once and its output hash is recorded. All candidates run in one committed script. Nothing is run on Dev-R before that commit.

**The candidate and the controls.**
- **Control, R1:** keyword search over records with a header, top 10.
- **Candidate, R9, linked records within 10.** Walk R1's ranking from the top. Append each unit if it is not already in the output. Then append its linked units, if not already in the output, in sorted ID order: for a GitHub advisory, the NVD record of each CVE in its aliases, then the KEV entry for those CVEs. For an NVD record, the GitHub advisories that alias its CVE. For a KEV entry, the NVD record and those advisories. Stop at 10 records.
- **Candidate, R10, package-scoped records.** If the question text names exactly one of the 18 packages (whole-word, case-insensitive match on the package name as it appears in the corpus), the list is the records of that package, ordered by R1's ranking and then by ID for any R1 did not match, cut at N = 20 records. If the question names no package, or more than one, the list is R1's top 10, unchanged. The share of questions R10 scopes is reported.
- **Control for R10, R1 at depth 20.** An R10 list never holds more records than R1's top 20 (fewer where the package has fewer than 20), so R10 is credited only for choosing better ones and not for reading deeper. R10 is judged on the questions it scopes only, with both lists scored at their own length. Questions it does not scope are R1's top 10 by construction and cannot change.
- **The common yardstick.** To pick between candidates, each is also compared with R1 at depth 10 on the whole primary stratum.
- **Descriptive only, no adoption:** R1 at depths 10, 15 and 25 with input tokens, and R9x, which appends linked units beyond 10 up to 20. They show what a deeper list buys and costs. They cannot lose a question, so a test of them would prove nothing.

**Measures.** Primary: all-evidence at 10 on the primary stratum, which is the questions that need two or more records (multi-hop, sources-disagree and version-set). Secondary: lookups (one record), mean recall, and each figure by question type and by whether the question names an ID.

**Adoption rule for R9 and R10, fixed now.** There are two tests, so the family is 2 and the Holm correction applies. R9 is tested against R1 at depth 10. R10 is tested against R1 at depth N.
1. The primary stratum has at least 140 questions. If it has fewer, the result is descriptive and the rule below is not applied. R10 is also judged only if it scopes at least 40 primary-stratum questions. If it scopes fewer, R10 is descriptive. The 40 is a judgement made before any data, not a computed figure.
2. A candidate beats its control by at least the larger of 5 percentage points and 6 questions, with exact two-sided McNemar p below the Holm limit: the smaller of the two p-values must be below 0.025, and the larger below 0.05. If only one candidate is judged, the limit is 0.05 and six questions moving one way and none the other is the least that can reach it (p = 0.031). If both are judged, the smaller p must be below 0.025, so the least is seven to none (p = 0.016).
3. Do no harm: on each slice, the candidate loses at most 1 question against its control, and at most 1 percentage point on the whole set. R10 is also held to this against R1 at depth 10 on the questions it scopes, because a package list could crowd out an NVD or KEV record that R1's top 10 held.
4. A candidate that passes earns the dev generation check and nothing more. The check runs the whole system as it would be tagged: the candidate's retrieval plus the completeness check below, with its spec committed and tagged first. It enters a system only if the check passes: three runs on the 40 v1 dev questions with checked correct at least 30 of 40 in each run (the Phase 6 figure), no parse failure, no more wrong answers shown than `phase6-system-v1` had on the same 40 summed over the runs, and mean input tokens at most 1.3 times R1's for R9 and at most 2.0 times for R10. R9's check costs about $3.55 and R10's about $7.4. Each needs my yes.
5. If both pass, only the one with the larger gain against R1 at depth 10 on the whole primary stratum goes into the system. They are not stacked, because the stack was not tested. The other is reported as passed and not combined.
6a. If neither passes, the completeness check may still form a new system on its own, with R1 as the retrieval, after the same dev generation check (about $3.55, my yes). Otherwise there is no new-system arm.
6. A candidate that fails is reported in full as a negative result, and the README lists it as tested and not adopted.

Checkpoint 2 shows: the committed build, Dev-R's size and counts, and the run script before it runs. Checkpoint 3 shows the results table, whichever way it goes.

**A completeness check for list answers (no model calls, no cost).** All 8 wrong answers shown on Test v1 were incomplete lists of true facts. I know that from `docs/test-results.md`, so it is a look at test data, and it goes in the ledger as one. The check does not use those replies and is not tuned on them. It is a rule I write from the problem alone:
- For a question that asks for a set (which advisories, which versions, all of them), the checker withholds the reply unless the retrieved records include every record in the question's scope, which for a package question is every record of that package within N. A reply that says plainly it covers only part of the list is shown.
- The exact rule is committed as a short spec and tagged `completeness-spec-v1` before it is run on anything. A later change to it is a post hoc amendment, marked as such. It is run on the saved dev replies (3 runs of 40), where it is descriptive: the dev set holds few list questions, so I report the counts and no adoption claim. Its real test is the new-system arm in step 4.
- It goes into the system that step 4 scores, once the spec is committed. The system is one tagged build, not variants.
- Cost to coverage: any list question whose package is larger than N becomes a decline. That trade, fewer wrong lists for more declines, is the point, and the write-up reports both numbers.

## Step 3: the live search (no cost)
Steps 2 to 5 of [live-search-plan.md](live-search-plan.md), with these changes:
- Rule 3 is amended as proposed there: the live list equals the saved list for 38 of 40 dev questions, and `vr-001` and `ab-005` are named exceptions.
- The page says plainly that it is retrieval only, shows dev questions only, and shows the snapshot date and which search it runs.
- If R9 or R10 is adopted into a system, the page offers it beside R1. Otherwise it shows R1 only.

## Step 4: the Test v2 run (costs money, one yes per spend)
**First, before any v2 question is scored,** `docs/test-v2-plan.md` is written and committed. It fixes the arms, the predictions, the analysis and the spend cap. The runner and scorer change to read `eval-v2/` under their own freeze tag, with the reason recorded, as ADR 0009 says. I do not look at which v2 questions R1 misses before the predictions are committed.

**Arms.** Each is scored once, in this order.
1. **Base rows:** the baseline, structured lookups, long context, retrieval alone (R1 on Test v2) and `phase6-system-v1`. About $7.
2. **Oracle row, open until funded.** R1's list is kept. Any gold evidence record it is missing replaces the lowest-ranked record that is not gold. For should-abstain questions the list is R1's, unchanged. The analysis is on the questions where R1 missed evidence, about 35 of the 89 answerable. About $3.3. It tests how much of the gap is retrieval, without moving the evidence to the top of the prompt.
3. **New-system arm,** only if R9 or R10 passed step 2 and its dev generation check, or if the completeness check passed its own (step 2, rule 6a). A tagged system with that retrieval and the completeness check, paired with `phase6-system-v1` on the same questions. About $3.3 with R9 or R1, and up to about $6.8 with R10. With 109 questions it can show a direction and an interval, not proof of a small gain, and the plan says so in advance. This arm is where the two targets are measured. If there is no such arm, the targets go unmeasured for a new system, and the README reports `phase6-system-v1`'s Test v2 base row against them as where the existing system stands.

**One shot.** Test v2 scores each frozen system once, and this is the only new-system arm. If the targets are missed, I do not adjust the system and score it again on Test v2. Further work needs a new test, Test v3, built from the reserve in step 1, item 7. Building it costs nothing, and it would be planned and frozen the same way. Test v3 is not part of this round.

**Headline comparisons.** The six named in `eval/rules.md` section 8, as `eval-v2/rules.md` says. Two more are pre-registered as secondary, and an ADR records them as added after the freeze: the system against the baseline on the answerable questions (replication on fresh data), and the system against structured lookups on the 54 free-form questions. The rule that the retrieval ladder is compared on dev only still holds. Retrieval on Test v2 appears only as a row of the system arms.

**Spend.** A hard cap for the whole step, an ask before each row, retries off as now, and the provider's own spend limit set to the cap. Spend is written into a committed ledger.

**Not planned:** red team round 2 ($9.5). It is the README's largest open limit and it is the next round.

**Not in this round: a hosted tool.** A reliable tool people can use needs a funded live endpoint. That is about $0.03 a question for R1 and more for R10, plus hosting, abuse limits and a spend cap, which ADR 0014 dropped. I decide that after the targets are measured, in its own ADR. Until then the live page is retrieval only.

## Step 5: write-up
The README, the results documents and "What I would not trust" are updated with every result, null and negative ones included, and the ledger count is shown. The LinkedIn post is updated to match, and the README banner is set to its final wording.

## What ends the round
- Steps 0 to 3 and 5 are done and written up by 30 November 2026. Step 4 is done if credit is there. If it is not, it is deferred and named in the README, and the round still counts as complete.
- Or no candidate passes step 2, or Dev-R is too small. Then the result is reported as null or descriptive, and the round ends.
- The round does not end because the targets are met, and does not carry on because they are missed. It reports where it stands against them.
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
| 2, dev generation check, only if R10 passes | 120 calls | about $7.4 (£5.57) |
| 2, dev generation check, completeness check alone, only if neither passes | 120 calls | about $3.55 (£2.66) |
| 4, base rows | the five rows | about $7 (£5.24) |
| 4, oracle row | one system row | about $3.3 (£2.47) |
| 4, new-system arm | one system row | about $3.3 with R9 or R1 (£2.47), about $6.8 with R10 (£5.06) |

The total depends on what passes. With R9 only it is about $17.2 (£12.8). With R10 only it is about $24.5 (£18.3). With both passing, only one goes forward, so the most is the R10 figure plus R9's dev check: about $28.1 (£21.0). My earlier "$17 to $20" was the R9-only figure. R10's higher cost is why this table changed.

About $0.74 (£0.55) of credit is left. Conversions are at 0.748 pounds to the dollar on 9 November 2026. The R10 figures are $0.062 a question (the whole-package row's cost) times 120 calls and times 109 questions, an estimate to be replaced by a measured figure at the first check.

## Decisions taken on 16 November 2026
1. **Step 4 arms.** The base rows first (about $7). Then the oracle row if funded. The new-system arm only if R9 or R10 passes step 2 and its dev generation check (as amended below). Each spend still needs its own yes.
2. **Live-search rule 3.** Amended as proposed: the live list equals the saved list for 38 of 40 dev questions, and `vr-001` and `ab-005` are the named exceptions.
3. **The Maven investigation** starts as soon as step 0 is committed.
4. **The second person for the 30-row gold sample.** Still to be found. If nobody is available by the time step 1 is checkpointed, the item is dropped and the write-up says so.
5. **The end date** is 30 November 2026.
6. **v1 dev advisories** may enter Dev-R as a flagged `seen_dev` slice, as drafted above.

## Amendment 1, 16 November 2026, before anything ran
Made at my request after I asked for the work to aim at a tool people can rely on. Nothing in it has seen a Dev-R or Test v2 number. The changes:
1. **Targets** added (see "In short"). They are not adoption rules.
2. **R10, package-scoped records,** added as a second candidate, with R1 at depth 20 as its control and N fixed at 20. The Holm family is now 2, and the R9 rule is restated for it. This changes the R9 rule's wording, not its thresholds, apart from the Holm limit that applies when both candidates are judged. The dev generation check now runs the whole tagged system, completeness check included.
3. **A completeness check for list answers** added, with a free test on saved dev replies and its real test in step 4. It is motivated by the 8 wrong lists on Test v1, which the ledger records as a look at test data.
4. **Step 1** gains the package sizes (item 6) and the reserve for a later test (item 7). Item 4, the pool count, is done.
5. **Step 4** gains the one-shot statement and Test v3, and the cost table gains R10's check and arm.
6. **Hosted tool** named as not in this round.
7. **Review fixes.** An independent read of this amendment found 11 problems, all accepted and fixed in the text above: R10's control and scope, the Holm minimum (seven to none, not six), a common yardstick for choosing between candidates, the dev check running the whole system, a fallback when nothing passes, Test v2 text removed from the package-share count, N fixed at 20, a tag for the completeness spec, the interval wording and the definition of "delivered", the reserve exclusion and recount, and the R10 cost recomputed from $0.062.

Decisions I still need, none of which change the text above if I accept the defaults written in it:
7. **List questions.** Default as written: they enter Dev-R only through the flagged `seen_dev` slice, with no adoption claim, and no advisory is shared with Test v2. The alternative, sharing advisories with Test v2 so Dev-R has more list questions, would let a fix be tuned on subjects that Test v2 then scores. I recommend against it.
8. **Budget.** Default as written: each spend is a separate yes, and the whole round stays at or below about $28.1 (£21.0). Credit is about $0.74 now.
9. **End date.** Default as written: 30 November 2026 for the free steps, with step 4 and the generation checks deferred until credit exists.
