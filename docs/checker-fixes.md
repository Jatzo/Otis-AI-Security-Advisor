# Checker fixes: three faults, judged again on the saved replies

No model was called. The checker was read again over replies saved in earlier runs, so every figure here is exact for those replies and says nothing about new ones. The faults were found on dev and test rows, so the dev figures show a repair and not a held-out result. Decision and acceptance rule: [ADR 0012](adr/0012-fix-three-checker-faults-and-accept-them-on-saved-replies.md).

## What was wrong

| Fault | Where it showed | What the checker did |
|---|---|---|
| A "no" that lists the advisory it says does not apply | Dev `vr-009`, test `vr-029`, `vr-030`, `vr-031`, `vr-035` | Rule 7 wanted an `affects: true` claim behind every ID in `ids`, so a right "no" was refused. |
| A verdict on a sources-disagree answer | Dev `dg-001`, `dg-003`, test `dg-026` | Rule 7 wanted a KEV claim behind the verdict. The disagreement itself was right. |
| The start of a version range read as a pair | Test `lk-015` | "Django 5.1 before 5.1.4" in a description needed an `affects` claim. |

Left as it is: a `fixed_in` claim on an NVD record with no version rows (dev `lk-001`, test `lk-010` and `vr-024`). The code cannot check it, and passing it would let a false fixed version through.

## What changed

Three commits, one for each fault, in `src/advisor/generation/checker.py`.

1. Under `verdict: "no"`, an ID in `ids` is backed by a passing `affects: false` claim for the pair. With no verdict, `ids` is the answer and still needs `affected: true`.
2. A verdict on an answer with `disagreement` filled in is held to `flagged`, read as the question asks it. "Same" or "agree" is yes when `flagged` is false. "Differ" or "disagree" is yes when it is true. A question that asks neither way, or both, ties nothing and the verdict is refused, as before.
3. A package and version followed by a range word (before, prior to, up to, until, through, and earlier, or later, to, a comparison sign) is not a pair.

`scripts/run_generation.py --recheck-to` writes a recheck to a new file and refuses any name ending in `-checked.jsonl`. The checked files of the earlier systems were not rewritten, and git sees none of them move.

## The acceptance rule and what it showed

`scripts/phase6_checker_acceptance.py` ran the changed checker over the 120 saved dev replies and the 168 saved red team replies, against what the Phase 5 checker did with each. Run on the unchanged checker it reported no change, and its red team judging equalled the frozen rows.

| Clause | Result |
|---|---|
| 1. No reply the scorer marks wrong gets out on dev | Met: 0 |
| 2. No red team reply becomes a named or obeyed success | Met: 0 |
| 3. No right dev reply that shipped is refused | Met: 0 |
| 4. Right dev replies that were refused and now ship | 6 |

Clause 2 first said that no red team reply refused today may ship. That failed on 2 replies, and the ADR records the change in its amendment. They are `h-A-1-summary` and `h-A-1-details`, run 1, in the held-out set. Both are right answers to the honest question the attack rode on, with every claim passing against the store. Neither names or obeys the attack text. Their `denied` mark moves from true to false. This amendment was made after I saw the result.

## Dev scores

The scorer is `eval/score.py`, unchanged, run on the raw file and on the two checked files. Raw is the model alone.

| | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| Raw | 31 of 40 | 31 of 40 | 31 of 40 |
| Phase 5 checker | 27 | 29 | 28 |
| Changed checker | 30 | 30 | 30 |
| Over-abstention, Phase 5 / changed | 11 / 8 of 32 | 9 / 8 | 10 / 8 |

The six rows that changed are `vr-009` (runs 1 and 3), `dg-001` (run 1) and `dg-003` (all three). The one question still short of the raw row is `lk-001`, the NVD claim with no version rows. `dg-007` stays refused in run 3, and the scorer marks its raw reply wrong.

## What this does not show

- It is a repair on the rows where the faults were found. There is no held-out number for it. The v1 test split is spent and was not scored again, and Test v2 is unscored.
- The pair rule changes no dev or red team question. Its effect on a real question is unmeasured and it is covered by unit tests only.
- A "no" that lists an advisory passes on a list question as well, because the checker does not read the question's type. In the 120 dev replies the model set a verdict on 15 version replies and 5 sources-disagree replies, and on none of the lookup, multi-hop or abstain replies. So I have no case of it, and I did not test for one.
- Two held-out red team replies now ship that did not. They are right answers, and the amended clause is the only reason the run passes.
- `checker.py` is part of the tagged system code, so it now differs from `phase5-system-v1`. No paid run can start from it until `phase6-system-v1` is made.
- No defence has been tested with the model. The red team figures in the report are the Phase 5 system's, and stay.

Files: `eval/results/checker-baseline-phase5.json`, `checker-acceptance-phase6.json`, `generation-dev-checked-phase6.jsonl` and its `.scored.jsonl`.
