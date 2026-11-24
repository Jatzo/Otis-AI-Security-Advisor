# Completeness check, spec v1

## In short
When a question asks for a whole list about one package, the checker withholds the reply unless the model was shown every record of that package. A reply that says plainly it covers only part of the list is shown. Nothing else changes, and the check is off unless it is asked for.

I am writing this from the problem alone, before the code exists and before it runs on anything. It is tagged `completeness-spec-v1` at this commit. Any later change is a post hoc amendment and will be marked as one, with the reason.

## Why
On Test v1, the wrong answers that were shown to the user were incomplete lists of true facts. That is a look at test data and the ledger records it as one. I have not reread those replies to write this rule, and the rule is not tuned on them. The motivation and the trade are in [the evidence round plan](evidence-round-plan.md), in the section on the completeness check.

## The rule
All of these are fixed here and none is a setting.

**N is 10.** It is the largest number of records the model is shown, which is R1's top 10 and R9's limit of 10. The plan's N of 20 belongs to R10's cut and is not used here. A package with more than 10 records can therefore never pass, and that is the stated cost.

**Which questions it covers.** A question is covered when both of these hold.
1. It does not start with is, are, does, do, was, were, can, has or have (case-insensitive, after leading spaces).
2. It matches this expression, case-insensitive: `\b(?:which|what)\s+(?:\w+\s+){0,2}?(?:advisories|versions)\b|\b(?:list|name)\s+(?:all|every)\b|\ball\s+(?:the\s+)?(?:advisories|versions)\b`

and it names exactly one of the 18 packages by `names_one_package` in `src/advisor/retrieval/candidates.py`, the same whole-word, case-insensitive match R10 uses. Questions that name no package, or more than one, are not covered. I accept that this misses wordings such as "Log4j Core" and will not widen it.

**What is in scope.** Every unit in the store whose `packages` include that package, of any source: GitHub advisories, NVD records and KEV entries. This is the set R10 builds.

**When the reply is withheld.** The reply is withheld when all of these hold.
1. The question is covered.
2. The model did not abstain, and rules 1 to 8 of the checker let the reply through (verdict `passed` or `repaired`). A reply with no IDs in it is still covered.
3. At least one unit in scope was not among the units shown to the model.
4. The reply's `explanation` text contains none of the partial-list phrases below.

**The partial-list phrases.** A closed list, matched as case-insensitive substrings of `explanation` and nowhere else:
`only part of`, `not a complete list`, `not the complete list`, `not the full list`, `incomplete`, `may not be complete`, `there may be more`, `there may be other`, `not every advisory`.

**What a withheld reply looks like.** It is checked as rule 9, route `checker`, verdict `refused`, with this text: "Otis was not shown every record for this package, so it cannot give a complete list. Ask about one version or one advisory ID." Rule 9 runs last, after rule 8, so every earlier verdict and count stays comparable.

## What it does not do
- It does not read the gold, the question type or any result.
- It does not change a reply that is shown. It only withholds.
- It is off by default. A recheck or a run without `--completeness` gives exactly the checker as tagged `phase6-system-v1`.
- A package with 10 records or fewer passes whenever the model was shown all of them.

## How it is used
1. A free recheck on the saved dev replies (3 runs of 40), written to a separate file. It is descriptive: the dev set holds few list questions, so I report counts and make no adoption claim.
2. As part of the system the dev generation check runs, if R9 earns the check. R9 passed rules 1 to 3 on Dev-R, with all the evidence for 179 of 179 main questions against 96 for R1's top 10, on gold built from the links it follows, so that figure is an upper bound.
3. In the clean run on Test v2, only if the dev check passes and it is funded.

The write-up reports both numbers: the wrong lists removed, and the extra declines it costs.
