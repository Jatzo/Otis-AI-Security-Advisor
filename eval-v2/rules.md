# Test v2 rules

Status: frozen with the questions and the gold under the tag `eval-freeze-test-v2` ([ADR 0009](../docs/adr/0009-test-v2-lives-in-its-own-folder-under-its-own-tag.md)). Nothing here was written after seeing how any system performs on these questions.

Everything in [eval/rules.md](../eval/rules.md) applies to Test v2 unless this file says otherwise: the scope the system is told, the answer schema, the scoring, the slices, the statistics and the errata rule. The snapshot is the same (`2d04b933ea7b`, data fetched 1 November 2026) and so is the generator under test.

## What differs

- **One split.** All questions are in one split, `v2`, and every question is scored once per system. There is no dev part: tuning stays on the v1 dev split.
- **Size and mix.** 109 questions: 24 lookup, 22 version-affected, 23 multi-hop, 20 should-abstain, 20 sources-disagree. The ids are `v2-lk-001` and so on. The seed is 20261102.
- **No v1 advisory** is the subject of a question, unless a kind of question had run out. Those questions have `reuses_v1: true` in `questions.jsonl` and are reported as their own slice.
- **Wording.** Each question has a `form`. `v1` means it uses a wording from a v1 template. `free` means it is worded in a way the structured row's patterns do not match, or is a description written in other words. At least 45 are free, checked by a test (`tests/test_eval_v2.py`). Should-abstain questions all use v1 wordings.
- **Descriptions.** The 13 description lookups use hand-written paraphrases in `paraphrases.json`, picked by `pick_descriptions.py` (seed 20261102) from advisories no v1 question used. Three of the 16 picks were dropped by hand, before any system ran, because other advisories for the same package could not be told apart from them in one sentence.
- **Headline comparisons.** The six comparisons in section 8 of the v1 rules are named again here for v2 and are the only ones given a headline. They are reported beside the v1 results, never in place of them. A change is claimed only on v2, and the v1 test result is not recomputed.
- **The structured row is reported on the free-form and v1-form questions separately**, because the point of the free-form questions is to show how much of its v1 score came from the wording.

## Freeze

Frozen: every file under `eval-v2/` except `eval-v2/results/` and `eval-v2/errata.jsonl`. `scripts/check_eval_v2_frozen.py` compares git blobs with the tag and runs in CI. The runner and scorer are not frozen here: they still read `eval/`, and the change that lets them read `eval-v2/` is made under its own tag before any scoring.
