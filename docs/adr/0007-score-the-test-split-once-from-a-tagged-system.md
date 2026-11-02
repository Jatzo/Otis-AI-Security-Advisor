# 0007: The test split is scored once per row, from a system frozen by tag

- Status: accepted
- Date: 2026-11-02

## Context
The test split has 110 questions that no system has been tuned on. Phase 4 changed the prompt once after seeing dev results and left a second change unadopted, so the dev numbers are fitted to the dev questions. The test numbers are the only ones that can be claimed as a measure of the system, and they are only that if nothing changes after the first look.

## Decision
Five rows are run on test, each once, from one tagged commit (`phase5-system-v1`): the model with no documents, structured lookups with no model, the model with a whole package in front of it, retrieval alone, and the system. Nothing under `src/`, `scripts/` or `eval/` differs from the tag afterwards, except `eval/results/` and `eval/errata.jsonl`. A pre-flight check enforces it before each row. All five rows are committed before any is scored.

A fault is a crash, a lost line or an API failure that survived the retries. A reply that was received is final, whether it parses or is right. A fault is fixed under a new tag with the reason written down.

The retrieval ladder stays dev only, as `eval/rules.md` section 8 says. On test, retrieval is the adopted rung, with the two no-model lists beside it as context.

The long-context row is limited to the questions that name a package, because there is no sensible whole-package prompt for a question that names only an ID and the whole corpus does not belong in every prompt. It is reported on those questions beside the other rows, and nowhere else. Every package fits in the model's context window (1,000,000 tokens, read from the Models API), so no question is left out for size, and a question the API refuses for size is listed, not counted wrong.

## Alternatives not taken
- **Run the rows as they are built, and look.** Quicker, and each look tempts a fix. A fix after a look is tuning on test.
- **The full ladder on test.** It would give a complete ablation table on the questions that matter, but needs the dense models and the reranker built again and run for hours, and it invites choosing a rung from test results, which the rules rule out.
- **A size limit on long context.** Chosen at 150,000 tokens it would have dropped the two largest packages and counted their questions wrong for a limit nobody needs. The measured sizes (pillow 289,000 tokens) showed the limit was a cost rule, not a capacity rule.
- **A hand spot-check that claims to be blind.** Joe read every gold row before the freeze, so the check is blind to the scorer and the checker and to which row wrote a reply, and says so.

## Consequences
- The tag is only a receipt if it is pushed and protected before the first test call. The ruleset is a repository setting that Joe saves himself.
- Row S reads the wording of the question templates, so it will do well on exactly those forms. The write-up says what that does and does not show.
- The spend caps are set from measured prompt sizes before any test call, and are not raised afterwards. A row that stops at its cap is reported as stopped.
