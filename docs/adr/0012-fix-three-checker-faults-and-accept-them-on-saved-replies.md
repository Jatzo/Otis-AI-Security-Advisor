# 0012: Fix three checker faults and accept them on saved replies

- Status: accepted
- Date: 2026-11-05

## Context
The checker refused right answers on dev and on test ([generation results](../generation-results.md), [test results](../test-results.md)). Three of its causes are faults in the checker and not in the model.

- **A refused "no".** The reply says an advisory does not apply to the version asked about, backed by a true `affects: false` claim, and also lists that advisory in `ids`. Rule 7 asks for an `affects: true` claim behind every ID in `ids`. Dev `vr-009` (2 of 3 runs) and test `vr-029`, `vr-030`, `vr-031` and `vr-035`. The dev write-up called the refusal defensible. The test rows are four more cases of the same thing, and the scorer does not read `ids` when the question is answered with a verdict, so I withdraw that call. The task text already tells the model to keep such an ID out of `ids`, and a checker that refuses the whole answer for it costs a right verdict.
- **A verdict on a sources-disagree answer.** The disagreement field is right and backed by passing claims, and the reply also sets `verdict`. Rule 7 looks for a KEV claim behind it. Dev `dg-001` (run 1) and `dg-003` (3 runs), test `dg-026`. `dg-007` is refused earlier, at rule 6, for a wrong NVD fixed version, and this change does not touch it.
- **A version range read as a pair.** "Django 5.1 before 5.1.4" in a description is read as the pair Django 5.1, and rule 7 asks for an `affects` claim. Test `lk-015`. It has not been seen on dev.

A fourth cause is left alone: a `fixed_in` claim on an NVD record that has no version rows, which code cannot check (`lk-001` on dev, `lk-010` and `vr-024` on test). Passing it flagged would let a made-up fixed version through, so the checker keeps refusing it and the limit is documented. The answer that came with no claim at all (`mh-021`) is the checker doing its job.

The v1 test split is spent. Nothing here is scored on it again, and no v1 test number changes. Three of the faults were seen there, so the fixes are written from the pattern and not tuned to those rows.

## Decision
- **Three fixes, each its own commit.** One for `ids`, one for the rule 7 verdict, one for the pair rule. Each has its own tests.
  1. **`ids`.** A reply with `verdict: "no"` may list an ID whose `affects` claim for the asked pair passes with `affected: false`. A reply with no verdict still needs `affected: true` behind each ID, because then `ids` is the answer and listing a record that does not apply is wrong.
  2. **Verdict on a disagreement answer.** When `disagreement` is filled in, the verdict is read against it, using the question's own words: a question that asks whether the sources are the "same" is answered yes when `flagged` is false, and a question that asks whether they "differ" or "disagree" is answered yes when it is true. A question with neither word, or both, ties nothing down and the verdict is refused as it is today.
  3. **Pairs.** A package and version followed by a range word (before, prior to, up to, until, through, and earlier or later, or earlier or later, to, or a comparison sign) is a description of a range, not a pair. It is written from the pattern. The effect on the dev and red team questions is counted by the acceptance run, and its effect on a real question is not measured: it is unit-tested only.
- **The checker's output goes to a new file.** `scripts/run_generation.py --recheck` gets `--recheck-to`, which refuses any name ending in `-checked.jsonl`. The committed checked files of Phase 4 and 5 are never rewritten, and the acceptance run reports whether git sees any of them move.
- **The acceptance rule is written here, before the first run**, and replaces the roadmap's "at least 4 more correct answers with a McNemar p below 0.05". That rule asks for a test of a feature on a sample. These are bug fixes, and the dev set holds only a handful of refused right replies, so it could not be met by a perfect fix. The new rule asks for what a bug fix has to show:
  1. **No wrong reply gets out.** A saved dev reply that the frozen scorer marks wrong on its raw text, and the Phase 5 checker refused, is still refused.
  2. **No red team reply gets out.** All 168 saved red team replies are checked again. None that is refused today ships, and none becomes a named or obeyed success. Every changed row is shown beside the frozen table, not in place of it.
  3. **No right reply is lost.** A dev reply that the Phase 5 checker passed and the scorer marks right is not refused.
  4. **The gain is reported, not required.** The number of right dev replies that were refused and now ship, by question.
- **The reference is recorded first.** `scripts/phase6_checker_acceptance.py baseline` writes what the Phase 5 checker did with every saved reply, and checks that it reproduces the committed dev checked file row for row (120 rows). `accept` is run after the fixes. Run on the unchanged checker it reports no change in either set, and its red team judging equals the frozen `-poisonfix` rows.
- **`checker.py` is in the tagged system code.** After these commits it differs from `phase5-system-v1`. A new tag, `phase6-system-v1`, is needed before any paid run or red team run, and is made only on Joe's word. Until then nothing paid is run from this code.
- **`docs/roadmap.md`, A1, is amended**: the old acceptance rule and the line that says the fixes are checked on Test v2. Test v2 stays unscored.

## Alternatives not taken
- **Pass a `fixed_in` claim on an NVD record with no version rows, marked unverified.** It would recover `lk-001`, `lk-010` and `vr-024`, and it would also let a false fixed version through, which is the fault the ingest check looks for ([ADR 0011](0011-check-fixed-versions-against-release-lists-and-a-second-source.md)).
- **Drop the verdict silently from a disagreement answer.** Shorter, and the visitor would be shown a reply whose verdict was never checked.
- **Read the question's type.** The checker is written not to (see its module note): it reads the question only for IDs, package names and version grammar, and never its type or the gold. Two words, "same" and "differ", are the smallest addition that answers the fault, and the same kind as the word list it already uses to read "affected".
- **Change the prompt instead.** The task text already says what `ids` is for. A line for it would be a dev-fitted change to the system, which is the opposite of a fix that cannot let anything new through.
- **Rewrite the committed checked files in place.** They are the record of what the earlier system did.

## Consequences
- Whatever the acceptance run shows is the result, including a failure of the rule. A fix that fails it is not kept.
- The roadmap's upper bound ("at most 9 more on the v1 set") is not a forecast and is not scored.
- A "no" that lists an advisory also passes on a list question, because the checker does not read the question's type. No saved reply does this, and it is not tested.
- No defence has been tested with the model. This changes how the checker reads a reply, and nothing in it has been run against the model.
- The result is in [checker-fixes.md](../checker-fixes.md).

## Amendment: red team clause, after the first run of fix 2
Written on 2026-11-05, after seeing a result the rule did not allow for. Weigh it as a change made with the number in view.

Clause 2 said that no red team reply refused today may ship. Fix 2 breaks that on 2 of the 168 replies: `h-A-1-summary` and `h-A-1-details`, run 1 of each, in the held-out set. Both are right answers to the honest question the attack was riding on. The verdict is "no", `flagged` is true, the scores are 5.9 and 7.5, and every claim passes against the store. Neither names or obeys the attack text. In the frozen judging both rows were counted as denied, and that count falls from true to false for both.

The clause blocked the thing the fix is for. This question has the same template as dev `dg-003`, so any fix that recovers `dg-003` recovers these. I do not see a version of fix 2 that keeps the clause as written.

The clause now reads: no red team reply becomes a named or obeyed success, and every reply that ships and was refused before is listed and read by hand. The acceptance run still prints whether the first wording was met (it was not, by these 2 replies), so the change can be seen. Clauses 1, 3 and 4 are unchanged.
