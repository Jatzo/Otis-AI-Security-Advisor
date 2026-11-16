# 0016: Reopen the project for a bounded evidence round

- Status: accepted
- Date: 2026-11-16

## Context
[ADR 0014](0014-close-the-project-as-a-portfolio-piece-and-record-where-it-misses-the-bar.md) closed Otis on 5 November 2026 and listed what was not done. Since then the replay demo went public ([ADR 0015](0015-publish-the-replay-demo-on-github-pages.md)) and the first step of a live search was built. Reading the project again as a sceptical reviewer would, four weaknesses stand out:
- The set I tune on is 32 answerable questions, and I have looked at it many times.
- Test v2 has no development part, so there is nowhere safe to develop a fix, and its gold has no recorded line-by-line review.
- "Retrieval is the limit" is a conditional reading, not a test of cause.
- The numbers in the README are copied by hand, and nothing checks them.

The retrieval weakness on multi-hop and sources-disagree questions is also the open problem [ADR 0005](0005-keyword-search-over-headed-records.md) names. About $0.74 of credit is left, so the part that costs money stays unfunded.

## Decision
Reopen the project until **30 November 2026** for one bounded round, run as [the plan](../evidence-round-plan.md) sets out. The plan was committed (`b3efca4`) before anything in it ran.
- **In scope:** a ledger of every look taken at development data, a check of the Maven comparator and the Test v2 gold, a script that ties README figures to raw results, a retrieval study on a new development set with one candidate, the live search, and the Test v2 run if credit arrives.
- **Not changed:** the v1 numbers, the protected tags, the rule that each frozen system scores a test split once, and the limits ADR 0014 recorded. ADR 0014 stays as the record of the closing.
- **Ends** when steps 0 to 3 and 5 are written up, or on 30 November 2026, or when I stop it. Step 4 may be deferred past that date if there is no credit.

## Alternatives not taken
- **Leave it closed.** The four weaknesses stay, and a reviewer will find them before I do.
- **Run the Test v2 rows first with the current system.** It is the cheapest fresh number, but it spends the one clean set before the instrument is checked and before the gold is reviewed.
- **Develop the retrieval change on Test v2.** It would turn the only fresh set into a development set.
- **Reopen with no end date.** The README would say "work in progress" indefinitely, which ADR 0014 rejected.

## Consequences
- The README says the project is reopened until 30 November 2026, and links this record and the plan.
- Reopening can look like moving the goalposts. The plan, the candidate, the adoption rule and the ledger are written before any run, and a rule changed after I have seen numbers is recorded as an amendment and marked post hoc.
- A published figure found wrong is corrected in the open, in [corrections.md](../corrections.md).
- The live-search decision record is renumbered to 0017.
- No defence has been tested with the model, and Test v2 is unscored. This record changes neither.
