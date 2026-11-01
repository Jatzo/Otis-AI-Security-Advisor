# Progress

Update this at the end of every session.

## Phases
Each phase stops at its "done when" and leaves a green CI run, an ADR for any real decision, and a debug-log entry for the first real bug.

- [x] 0. Repo and guard rails. Done 2026-11-01: CI run 41317004259 green; gitleaks 8.30.1 caught the planted token, then found no leaks in the history.
- [ ] 1. Data: fetchers for GitHub advisories (OSV JSON), NVD API 2.0 and KEV; CPE map; PyPI, npm and Maven version comparators; snapshot manifest; committed sample. Done when: per-package and per-source counts, a sample, and real disagreement statistics.
- [ ] 2. Eval freeze and baseline: questions, gold script, disagreement rules, `eval-freeze-v1` tag, CI guard, then the no-retrieval baseline. Done when: tag pushed, guard working, baseline table.
- [ ] 3. Retrieval: the ablation ladder (BM25, dense, hybrid with RRF, rerank, contextual headers, metadata filter, decomposition and iterative retrieval), two embedding models. Tuned on dev only. Done when: ladder table on dev and an ADR.
- [ ] 4. Generation and checker: schema output, fail-closed checker, abstention. Done when: tests show a fabricated CVE removed and an out-of-scope question refused.
- [ ] 5. Full evaluation: test split scored once, blind hand spot-check, cost and latency. Done when: report table with per-question detail.
- [ ] 6. Red team: threat model, poisoned corpus frozen before defences, XSS and link tests, abuse controls. Done when: attack success rate table, what held and what did not.
- [ ] 7. Demo on a Hugging Face Docker Space: answer, evidence and per-claim checker verdicts. Done when: public link with caps live.
- [ ] 8. Write-ups: two READMEs, `docs/brief.pdf`, weekly drift job.

## Decisions made
- Name: Otis (the tool), AI Security Advisor (the project). Repo: github.com/Jatzo/Otis-AI-Security-Advisor, public.
- Design: retrieval and generation answer every question; deterministic code only checks the answer and grades the eval. See `docs/adr/0001-retrieval-answers-code-checks.md`.
- Packages. PyPI: django, flask, jinja2, requests, urllib3, pillow, pyyaml, cryptography, aiohttp. npm: lodash, express, axios, jsonwebtoken, ws, minimist. Maven: log4j-core, spring-webmvc, struts2-core (KEV barely covers npm and PyPI libraries).
- Data: GitHub advisory database (OSV JSON), NVD API 2.0, CISA KEV. Sample and fetch scripts in git, full data out of it.
- Store: SQLite (FTS5 for BM25) plus exact numpy vector search. No vector database at this size.
- Chunking: one chunk per source record with a contextual header. Fixed-size versus structure-aware dropped as an experiment: advisories are short.
- Eval: about 150 questions, dev 40 and test 110, frozen and tagged before retrieval code. Gold from an independent script, reviewed by Joe (no hand-written subset, so the write-up says independence is weaker). Deterministic metrics lead; RAGAS-style LLM judging is not the headline.
- Every table: no-retrieval LLM, long-context, structured lookups with no LLM, then the ablation ladder.
- Demo: FastAPI and a static page using `textContent` only, on a Hugging Face Docker Space.
- Tooling: Python 3.12+, uv, ruff, pytest, pre-commit; gitleaks 8.30.1 in CI (not installed locally).

## Open
- Generator model and monthly budget. Needed before the Phase 2 baseline run. Price the run first and ask.

## Next session
Phase 1: data. First count advisories per package from the GitHub advisory database before pulling any text, and show the counts before going further.
