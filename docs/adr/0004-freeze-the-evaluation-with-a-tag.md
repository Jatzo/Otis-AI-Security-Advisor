# 0004: The evaluation is frozen by a git tag and held to it by a blob check, and the baseline runs after the tag

- Status: proposed, accepted when `eval-freeze-v1` is pushed
- Date: 2026-11-01

## Context
The write-up claims the 150 questions, their gold answers, the scoring rules and the scorer were fixed before any system was run against them. Nothing in a repository proves that by itself: files can be edited and the history tidied. A reader needs a receipt that does not rely on trusting the author.

There is a second way to weaken the claim. If the dev baseline is run before the freeze, its outputs can shape how the scorer reads replies (what counts as a parse failure, how a score is written), and the freeze then follows the results instead of preceding them. The first plan for Phase 2 ran the baseline before the tag. A review of that plan before any code was written named this.

## Decision
- **Freeze with a tag.** `eval-freeze-v1` points at the commit that holds the questions, gold, rules, answer schema, scorer, runner, prompt text and ID snapshot. Frozen means every file under `eval/` except `eval/results/` and `eval/errata.jsonl`.
- **Hold HEAD to the tag with `scripts/check_eval_frozen.py`.** It compares git blobs, offline. It fails if the tag is missing, if a freeze tag is no longer an ancestor of HEAD (history rewritten), if a frozen file was changed, added or deleted, or if `errata.jsonl` was edited instead of appended to. CI runs it with full history and tags. `.gitattributes` fixes line endings under `eval/` so the same file has the same blob everywhere.
- **Protect the tag.** GitHub tag protection on `eval-freeze-*` stops anyone moving or deleting the tag. The guard is only as strong as this.
- **Run the baseline after the tag.** `eval/run_baseline.py` refuses a real run unless the frozen files match the tag, and writes the commit and the blob id of each frozen file into every result line.
- **Fix a fault under a new tag.** A fault found in the scorer or runner after the freeze is fixed under `eval-freeze-v1.1`, with the reason and the changed files added to this record. The earlier tag stays, and each reported score names the tag it was produced under.
- **Fix the baseline's settings in the file.** Model `claude-sonnet-5-5`, effort `high` (the model's default), 16000 output tokens, adaptive thinking, no fallback model. Sampling settings cannot be changed on this model, so the dev baseline is run 3 times and shown as a spread, not a single number.

## Alternatives not taken
- **A hash manifest committed in the repository.** Whoever can edit the files can edit the manifest in the same commit. A tag on a commit, with protection, is anchored outside the files it vouches for, and git already holds the blobs.
- **Branch protection or code owners alone.** They control merges. They do not show a reader what was fixed, or when.
- **Running the baseline before the tag.** It was the first plan. It saves nothing and lets results shape the scorer. The cost of tag first is that a runner fault found afterwards needs a v1.1.
- **A lower effort for the baseline.** Cheaper, but a baseline run below its model's default invites the charge that it was made weak. The saving is a few dollars.
- **Constrained decoding for the baseline's JSON.** It would hide parse failures, which the rules count in their own column.

## Consequences
- Editing any file under `eval/`, including a typo in the scorer, now needs a new freeze tag. That is intended, and it is slow on purpose.
- The guard compares committed state. The runner has its own working-tree check, so an uncommitted edit also stops a real run.
- CI fails on the guard job until the tag exists and has been pushed. Push the tag with the branch.
- What the freeze shows is "before any system was run", not "blind". The questions and the gold were written by the same person before any system was run, and the gold's facts come from the same advisory database the corpus uses. Both limits go in the write-up.
- Revisit this if the tag is ever moved, or if a fault in the scorer is found after the test split has been scored: the test split is scored once, so such a fault would be fixed through errata and a second report, not by rerunning.
