# 0009: Test v2 lives in its own folder, under its own tag, and is written before any fix

- Status: accepted
- Date: 2026-11-04

## Context
The v1 test split was scored once and is spent ([ADR 0007](0007-score-the-test-split-once-from-a-tagged-system.md)). The plan of action ([roadmap](../roadmap.md)) fixes faults that were seen on it, and any claim that Otis got better needs questions that were not used to find those faults. v1 also has a known weakness: its questions are templated, so a program that reads the wording and queries the store (the structured row) scored 99 of 110 and is close to a ceiling.

Three things had to be decided: where the new set lives, how it is frozen, and when it is written.

## Decision
- **Own folder.** Test v2 is in `eval-v2/`. `eval/` and its guard (`scripts/check_eval_frozen.py`, held to `eval-freeze-v1`) are not touched. The v1 engine (`eval/build_questions.py`) and the gold code (`eval/make_gold.py`) are reused by import, unchanged, so the gold is still made by code that never touches the system.
- **Own tag and guard.** The tag is `eval-freeze-test-v2`, held by `scripts/check_eval_v2_frozen.py`, which runs in CI beside the v1 guard. The name matches the repository ruleset for `eval-freeze-*`, so the tag cannot be moved or deleted. It does not match the v1 guard's pattern (`eval-freeze-v<number>`), so the v1 guard never takes it for a newer version of the v1 freeze. Corrections after the tag are appended to `eval-v2/errata.jsonl`, as in v1.
- **Written before any fix.** The questions and gold are tagged before the checker, the poison builder or retrieval change. The roadmap said so, and the reason is that questions written after the fixes could be shaped around them.
- **What changed from v1.** 109 questions (the plan said about 110; one KEV list question could not be built, because KEV holds ten advisories and a repeated answer set is refused). A new seed and a new mix: 24 lookups (13 described in other words), 22 version, 23 multi-hop, 20 should-abstain, 20 sources-disagree. Every question is one split, called `v2`. No advisory that a v1 question (dev or test) was about is used, unless a kind of question ran out; those 8 questions carry `reuses_v1` and are reported as their own slice. 54 questions are worded where the structured row's patterns do not match (`form: free`), checked by a test against that row's own patterns.
- **The runner and scorer are not in this tag.** They still read `eval/`. Reading `eval-v2/` is a change to frozen v1 code, so it is made under its own tag when the five rows are about to run, with the reason written then, as `eval-freeze-v1.1` was for v1. Nothing is scored in the meantime.

## Alternatives not taken
- **`eval-freeze-v2`.** It matches the same ruleset, and it would also match the v1 guard's pattern, which holds `eval/` to the newest tag by version number. That would silently change what the v1 guard means.
- **Put v2 under `eval/`.** The v1 guard fails on any new file under `eval/`, so v2 would need a v1 tag change and a second look at every v1 result line, which record file hashes from that tag.
- **Write v2 after the checker fixes.** Quicker to build, and the fixes could then be tested on questions that were never seen. It also lets the fixes shape the questions, which is the thing a fresh set is for. The reviewer who read the plan said the same.
- **Draw v2 from the same advisories as v1.** Easier, and 175 of 588 advisories are already used. I have read the v1 failures, so reusing those advisories would leave v2 less independent. The exclusion is the default, with the flagged exceptions above.

## Consequences
- The v1 numbers stay as they are and v2 is reported beside them, not in place of them.
- The gold is independent in code and not in facts, as for v1: GitHub, NVD and OSV overlap.
- v2 is spent as soon as one system is scored on it. A later round needs a v3.
- The 13 description paraphrases are hand-written by me and are the most subjective part. Three picks were dropped by hand before any system ran (see `eval-v2/paraphrases.json`).
