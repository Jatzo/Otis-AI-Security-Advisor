# 0006: The checker refuses whole replies, and a named ID the store lacks is refused without a model call

- Status: accepted
- Date: 2026-11-02

## Context
[ADR 0001](0001-retrieval-answers-code-checks.md) says the model answers and deterministic code only checks. Phase 4 has to turn that into rules: what the checker does with a reply that is partly wrong, and what happens when a question names an advisory that does not exist. The rules were written and reviewed before any code ([generation-plan.md](../generation-plan.md)); this records the two choices that are decisions rather than detail.

## Decision
**One failed claim refuses the whole reply.** The model writes its answer and the claims it rests on. Code reads each claim against the store. If any claim is wrong, or cannot be checked, the reply becomes an abstention with a fixed sentence and the reasons go into a `checker` object beside it. Wrong and unverifiable claims are counted apart.

**One repair is allowed: cutting out an ID the evidence never held.** An advisory or CVE ID that is not a shown unit's own ID, one of its aliases in the store, or written in the question is removed from `ids`, from the sentence of `explanation` that holds it, and from every claim that names it. The reply is marked `repaired`. An invented ID inside `value` or `disagreement` is a refusal, because it cannot be cut out of a fact. If `ids` held IDs and none is left, the reply is refused.

**The gate extends ADR 0001 by one case.** If a question names a GHSA or CVE ID that no record, alias or KEV entry in the store holds, the reply is an abstention and the model is not called. This is the only place a reply is made without the model. It never produces an answer, only a refusal, so code still never answers a question. In the dev run the model is called anyway, so the raw and checked files cover the same 40 questions.

## Alternatives not taken
- **Drop the wrong claim and keep the rest.** Removing a wrong version or score changes what the answer says. Patching it would be code answering the question, which ADR 0001 rules out. Cutting an invented ID leaves everything else meaning what it meant, which is why it is the one exception.
- **Ask the model to try again.** A second call is another chance to invent something, doubles the cost, and makes the checked row depend on a retry policy. A refusal is cheaper and easier to measure.
- **Let the model decide what is an unknown ID.** The model is told not to give an ID it cannot point to in a record, and one baseline reply in 120 still invented one. The gate and the grounding rule do not rely on the model noticing.

## How the plan was read where it was silent
These readings are in the code and the tests, and the results will say how often each one decided a reply.
- A `published` claim on a CVE is read against that CVE's NVD record, and on a GHSA ID against the advisory. It has no `source` field to say otherwise.
- A claim "supports a verdict" when it is the kind the verdict needs (an `affects` claim with a package-version pair in the question, a `kev` claim without one) and is about a named ID or its alias. A claim about another advisory beside it does not refuse the reply; it just does not support the verdict.
- A null `github` side in `disagreement` has no claim that can support it, so it is refused. A null `nvd` side needs a passing `score` claim for NVD with null.
- A `value` or a side written as `none`, `n/a` or `null` is read as null, as the scorer reads it.
- An abstention by the model stands as written, unless an invented ID rides along, in which case it is cut down to a plain abstention. It stays counted as the model's.

## Consequences
- The checker's strength is also its cost: a true answer with one claim the code cannot check is refused. The smoke run showed it once (a fixed-version claim on an NVD record with no CPE row). Those are counted as harmed and each one is read by hand.
- A reply can pass with a wrong conclusion drawn from true facts, because the checker sees each stated fact and not the argument. The write-up says what it cannot see.
- A true KEV answer can pass although the KEV status came from the store check and not from anything the model was shown, because R1 never retrieved a KEV unit. The results count KEV claims with and without a KEV unit shown.
