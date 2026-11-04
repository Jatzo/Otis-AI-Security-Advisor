# 0010: Fix the poison builder under a new tag, and judge the saved replies again

- Status: accepted
- Date: 2026-11-04

## Context
The red team's B2 cases add a made-up advisory to a copy of the store, with a false fixed version ([poison.py](../../src/advisor/redteam/poison.py)). The builder gave every such record the range type `ECOSYSTEM`. The real store holds `SEMVER` for npm (all 160 ranges), Go and crates.io, and `ECOSYSTEM` for PyPI and Maven. The version checker picks its order from the range type ([ADR 0003](0003-version-order-by-range-type.md)) and has none for npm `ECOSYSTEM`, so it refused any reply that needed to order versions on a poisoned npm record.

That touched two of the eight B2 cases (axios in the frozen set, minimist in the held-out set). One saved held-out reply was refused for that reason, and the report counted it as a checker refusal "by accident". It was a fault in how I built the attack.

The builder is in `src/advisor/redteam`, which is frozen under `redteam-freeze-v1.1`, and the runner's guard holds it there.

## Decision
- **The builder copies the real range type.** It reads the type the store already holds for the record's ecosystem, and raises if the store has none. A fixed table of ecosystems was the alternative, and it could drift from the data.
- **A new tag, `redteam-freeze-v2`.** The change is made under its own tag with the reason written here, as `redteam-freeze-v1.1` was for the success check ([ADR 0008](0008-judge-an-attack-by-what-the-reply-did.md)). The runner's `FREEZE_TAG` moves to it. The name matches the repository ruleset for `redteam-freeze-*`, so the tag cannot be moved or deleted.
- **Judge the saved replies again, call nothing.** The range type is read by the checker and never shown to the model. The text of every B2 record, as hashed into the case files, is identical before and after (checked for all 8). The saved replies therefore stand, and judging them again is exact. `scripts/replay_poison_fix.py` first re-judges with the old behaviour and requires the saved judged files to be reproduced row for row (168 rows), and only then judges with the fix.
- **Nothing saved is overwritten.** The corrected judging is written beside the first one with the suffix `-poisonfix`.
- **Cases and manifest unchanged.** The attack files and their hashes are the same.

## Alternatives not taken
- **Leave the builder and note the fault.** The report already notes it, but the ingest check (roadmap, stage 0) will be run on these records. Two of them would be malformed for npm, and a check that reads ranges would be tested on records no real source produces.
- **Run the B2 cases again with the model.** It costs credit that is nearly spent, and it would show nothing new: the model sees the same text.
- **A fixed table (npm, Go and crates.io are SEMVER).** Shorter, and it could disagree with the store the next time the data is rebuilt.

## Consequences
- One judged row changes (h-B2-2). The held-out B2 result is 4 named and 3 obeyed, raw and shipped alike, with no visitor left without an answer. It was 4 / 3, 3 / 2 and 1. Every other row, in both sets, is the same.
- The checker made no difference to B2 in either set. The earlier text said it made one by accident, and that claim is withdrawn.
- B2 is still not like for like between the two sets: the held-out carriers include list questions. The fix does not change that.
- The tag is permanent once pushed. The raw replies, the first judging and the corrected judging are all kept.
- No defence has been tested. This is a correction to how an attack was built and how its result was read.
