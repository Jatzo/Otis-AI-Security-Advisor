# 0001: Retrieval answers the question; deterministic code only checks the answer

- Status: accepted
- Date: 2026-11-01

## Context
Many questions about vulnerabilities are structured underneath. "Does requests 2.25.0 have a known CVE?" is a version-range comparison. "Is it being exploited?" is a lookup against the KEV list. A database query answers both exactly, with no model involved.

The project exists to show retrieval-augmented generation measured honestly. It also must never let an answer claim something the retrieved sources do not support.

## Decision
Retrieval and generation answer every question. The model reasons over retrieved advisory text, version ranges included, and returns claims that each cite evidence IDs.

Deterministic code has two jobs and no others: it checks every CVE ID, package, version, score and KEV claim against the cited evidence and a version-range resolver, failing closed when a claim does not hold; and it computes the gold answers for the evaluation.

## Alternatives not taken
- **Structured lookups answer, the model only phrases the result.** More accurate on version questions from day one, but retrieval becomes decoration and the system stops being a test of retrieval. It survives as a comparison row ("structured lookups, no model") that the full system has to match or explain.
- **Model answers, nothing checks.** The common tutorial design. An instruction to "answer only from context" is not a guarantee, and in this domain an invented CVE ID is the worst failure there is.
- **Long context instead of retrieval.** Putting all of one package's advisories in the prompt is a real option at this corpus size. It is measured as a baseline rather than assumed away.

## Consequences
- Retrieval quality shows up directly in answer scores, so the retrieval ablation table means something.
- The checker can only catch claims of a type it knows how to check. Free-text reasoning that is wrong but cites no checkable fact gets through; the write-up has to say so.
- If the "structured lookups, no model" row beats the full system on version questions, that is reported, not hidden.
