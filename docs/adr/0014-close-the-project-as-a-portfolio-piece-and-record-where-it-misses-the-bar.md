# 0014: Close the project as a portfolio piece and record where it misses the bar

- Status: accepted
- Date: 2026-11-05

## Context
[PLAN.md](../../PLAN.md) sets a bar for the end of the project. Two things in it will not be met, and the repository has said "work in progress" about them for two days. The credit that would pay for the rest is spent.

- **The bar asks for a deployed, clickable demo, "not only something runnable locally".** The deliverables ask for a deployed demo link, and the brief for a link to the live demo. The Phase 7 plan was superseded on 3 November 2026 ([demo-plan.md](../demo-plan.md)): a live page needs a server, a hosted space and money for the model, and Otis is a portfolio project and not a product.
- **PROGRESS.md added a weekly drift job to Phase 8.** `PLAN.md` does not ask for one. It asks for one paragraph on a staleness strategy.
- **About $0.74 of API credit is left.** The roadmap's remaining stages cost about $3.55 (retrieval on dev), about $7 (the clean run on Test v2) and about $9.5 (red team round 2).

Everything that needs no model call is now done: Test v2 is written and frozen, the checker faults are fixed and judged on saved replies ([ADR 0012](0012-fix-three-checker-faults-and-accept-them-on-saved-replies.md)), the records scan and the ingest check are measured ([ADR 0011](0011-check-fixed-versions-against-release-lists-and-a-second-source.md)), and a replay of the saved dev answers runs on a static page ([replay-demo.md](../replay-demo.md)).

## Decision
Close the project here, and say where each part of the bar stands.

| The bar | Where it stands |
|---|---|
| A real baseline | Met. The model with no retrieval is a row in every results table. |
| An honest, rigorous eval | Met, with a limit. The set and gold were frozen under a tag before any result. The hand spot-check of 24 replies agreed with the scorer on 24 of 24, but I did not mark it. When I marked the sheet blind I judged 5 of the 24 and said "can't tell" on 19, so there is little independent hand marking. Test v2 is written and frozen and has not been scored. |
| Citation that is verified | Met, with limits. The checker is fail closed. It refused 9 right replies on test, passed 6 wrong list answers of 66 passed on dev, and cannot catch a record that lies. |
| Red-teamed as a target | Met for the attacks: 168 model calls, with what held and what did not. **No defence has been tested with the model.** One, the ingest check, was measured on saved evidence. |
| Production signals | Met. Cost and latency per query are in the results tables. |
| A current retrieval approach | Met. Nine rungs were measured. Keyword search with a header won on dev, and dense, hybrid, reranking, splitting and decomposition did not beat it. |
| **A deployed, clickable demo** | **Not met.** Replaced by a replay of the saved dev answers that runs locally from a static page. It is clickable. It is not deployed, and it answers only the 40 saved questions. |
| Two honest write-ups | Met. |

- **The deliverable "a deployed demo link" is dropped**, and so is the link to a live demo in the brief. The replay is the demo. Publishing it, for example on GitHub Pages, is a separate decision and has not been made.
- **The weekly drift job is dropped.** The staleness strategy is the README's snapshot paragraph: the corpus is dated 1 November 2026, it is not refreshed, and an answer does not record which snapshot it used. That paragraph is thin and I am saying so here.
- **The rate limit, spend cap and topic gate stay as built and unit-tested code.** They were never met by real traffic, because nothing is public. The constraint "rate-limit the public demo" applies if a demo is ever made public.
- **Phases 6, 7 and 8 are closed in PROGRESS.md** with these limits named, and no longer say "partly done".
- **Stale lines are corrected.** PROGRESS.md and [red-team-plan.md](../red-team-plan.md) said the tag ruleset covers only `eval-freeze-*` and `phase5-*`. It covers `eval-freeze-*`, `phase5-*`, `redteam-freeze-*` and `phase6-*` (read from the API on 4 November 2026, with no bypass). Lines that said work was "not committed" or "not pushed" are updated.
- **Left open on purpose:** [ADR 0013](0013-move-the-default-system-tag-under-redteam-freeze-v3.md) is still proposed. Nothing runs against the model without credit, and a run can pass `--system-tag phase6-system-v1`.

## Alternatives not taken
- **Deploy a live demo.** It needs credit, a hosted space, a secret and my accounts. The plan for it is kept in [demo-plan.md](../demo-plan.md) in case that changes.
- **Leave the phases open.** The repository would keep reading as unfinished, and the missing parts are not coming without credit. A named list of limits is more honest than a banner that says "work in progress" indefinitely.
- **Soften the wording of the bar in PLAN.md.** `PLAN.md` is the source of truth and is left as written. This ADR records where the project falls short of it, and I did not edit the bar to match.
- **Fund Stage 2 first.** Scoring Test v2 would give the only fresh accuracy number. It costs about $7 and the credit is not there. If it arrives, that is the first step, from the tag `phase6-system-v1`.

## Consequences
- The project cannot claim a deployed demo, a defence tested with the model, a Test v2 score, or an adaptive attacker. The README says each of these plainly.
- What remains unmeasured is listed once, in the README's status table and in the limits below, so a reader does not have to find it.
- Closing is not final. Each unfunded stage keeps its spend cap and its adoption rule in the [roadmap](../roadmap.md), and any new result goes under a new tag.
- No defence has been tested with the model.
