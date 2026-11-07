# 0013: Move the default system tag to phase6-system-v1 under redteam-freeze-v3

- Status: rejected on 7 November 2026 (see Outcome: the Decision section below is the option I did not take)
- Date: 2026-11-05

## Outcome (7 November 2026)
I rejected this ADR. [ADR 0014](0014-close-the-project-as-a-portfolio-piece-and-record-where-it-misses-the-bar.md) left the question open on 5 November. I am taking the first alternative below: keep passing `--system-tag phase6-system-v1`. The Decision section is the option I did not take, and I have left it as written so the record shows what I weighed.

- The project is closed and no paid run is funded, with about $0.74 of credit left. Nothing will start from the documented command soon.
- A pushed `redteam-freeze-v3` could never be moved or deleted. It would be the fourth red team freeze tag in three days, for one default that a flag already covers.
- The gate already fails safe. If the flag is forgotten it refuses, so the failure is loud and not a wrong run.
- I will revisit this only if the system changes again.
- Nothing was changed, tagged or pushed for this ADR. "Rejected" is not in the [template](0000-template.md) list of statuses. I used it on purpose, because "superseded" would be untrue, and I did not edit the template.

## Context
The red team runner checks before any paid run that the system code matches a named system tag ([run_redteam.py](../../scripts/run_redteam.py), `gate_problems`). Its default is `SYSTEM_TAG = "phase5-system-v1"`. [ADR 0012](0012-fix-three-checker-faults-and-accept-them-on-saved-replies.md) changed `checker.py`, which is system code, and the system tag `phase6-system-v1` was made on `8560454` and pushed. Since then the default fails: the gate says the system code differs from `phase5-system-v1`.

A run can already be started by passing `--system-tag phase6-system-v1`, and the runner's own docstring shows that flag. With the flag, the gate returns no problems (checked on 5 November 2026).

The default cannot be edited under the current freeze. `scripts/run_redteam.py` is in the frozen code that the gate compares with `redteam-freeze-v2`. I changed the default to see, and the gate then refused with "The attack files or their code differ from the tag redteam-freeze-v2". I reverted the edit.

## Decision
- **Change the default and move the freeze tag with it.** `SYSTEM_TAG` becomes `phase6-system-v1`, `FREEZE_TAG` becomes `redteam-freeze-v3`, and the module note that names the old tag is updated to match. The tag goes on the commit that makes the change.
- **Nothing else moves.** The attack files, their manifest, the poison builder, the success checks and the judging are the same as under `redteam-freeze-v2`. Only the runner's two constants and the text that names them change. The check for this is `git diff redteam-freeze-v2 redteam-freeze-v3 -- redteam scripts/make_attack_spec.py src/advisor/redteam`, which must be empty, and the diff of `scripts/run_redteam.py` must be those lines only.
- **The gate tests follow.** `tests/test_run_redteam.py` names `redteam-freeze-v2` in two cases and is updated to the new tag.
- **Pushed on its own.** The commit, then the tag, each on Joe's word, with the push spaced from the push that carried ADR 0012. The tag name matches the repository ruleset for `redteam-freeze-*`, so once pushed it cannot be moved or deleted.
- **No result changes.** No model is called and no saved reply is judged again.

## Alternatives not taken
- **Keep passing `--system-tag phase6-system-v1`.** It costs nothing permanent and the gate already passes with it. If someone forgets the flag the gate refuses, so the failure is safe and loud and not a wrong run. This was the cheaper path. I am choosing the tag because I want a run to start from the documented command with no flag to remember, and I accept the permanent cost below for that.
- **Pick the default from the newest `phase*-system-*` tag in the code.** The gate exists to hold the run to one named system. Code that picks its own system tag removes the name that is written down and reviewed.
- **Remove the default and require the flag.** It still edits the frozen runner, so it needs the same new freeze tag and gives a worse command than the change above.
- **Edit the file and leave the freeze tag at `redteam-freeze-v2`.** The gate refuses, and loosening the gate to allow it would remove the thing it checks.

## Consequences
- **The cost is permanent.** A pushed `redteam-freeze-v3` cannot be moved or deleted. It is the fourth freeze tag for the red team in three days (`v1`, `v1.1`, `v2`, `v3`), and it exists to change one default that a flag already covers. The history reads as churn, and it is.
- **The fix does not last.** The next change to system code needs a new system tag, and the default is wrong again until another freeze tag is made. This ADR moves the default once and does not make it track the system. If the system changes again, the flag is the better answer and I should say so then.
- **Every note that names the current red team tag must be updated.** `docs/README-security.md` (the tags list), `scripts/run_redteam.py` (its note and constant), `tests/test_run_redteam.py`, and the PROGRESS entry. `docs/red-team-report.md` (line 171) gains a line for the new tag. Its statement that the results were run at `phase5-system-v1` stays, and so do the older notes that name `redteam-freeze-v2` as the tag a past result was run under, because they are true.
- **Round 2 and any paid run start from `redteam-freeze-v3`.** The gate then needs that tag to exist, to be pushed with the same object, and to be covered by the ruleset, as it does for `v2` now.
- No defence has been tested with the model. This changes which tag a run is held to and nothing about what a run does.
