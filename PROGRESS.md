# Progress

Update this at the end of every session.

## Phases
Each phase stops at its "done when" and leaves a green CI run, an ADR for any real decision, and a debug-log entry for the first real bug.

- [x] 0. Repo and guard rails. Done 2026-11-01: CI run 41317004259 green; gitleaks 8.30.1 caught the planted token, then found no leaks in the history.
- [x] 1. Data: fetchers for GitHub advisories (OSV JSON), NVD API 2.0 and KEV; PyPI, npm and Maven version comparators; snapshot manifest; committed sample. Done 2026-11-01: snapshot `2d04b933ea7b` (588 advisories, 576 NVD records, 2 CVEs NVD does not hold, KEV 2026.10.30). Counts and disagreement figures are in `docs/data-report.md`. No separate CPE map: CPE matches are stored and not used for the join (ADR 0002).
- [x] 2. Eval freeze and baseline. Done 2026-11-01: tag `eval-freeze-v1` pushed on `abeedf8`, the freeze guard green in CI, and the dev baseline table below. GitHub tag protection for `eval-freeze-*` is still to be saved (not found by the API on 1 November).
- [ ] 3. Retrieval: the ablation ladder (BM25, dense, hybrid with RRF, rerank, contextual headers, metadata filter, decomposition and iterative retrieval), two embedding models. Tuned on dev only. Done when: ladder table on dev and an ADR. In progress: the ladder, its metrics, its adoption rule and its models are fixed in `docs/retrieval-plan.md`, committed before any retrieval code or result.
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
- Chunking: one chunk per source record with a contextual header. Reversed on 1 November 2026 after measuring record length: the median GitHub record is 458 characters, but p90 is 6,126, p99 24,036 and the longest 42,671. Splitting long records is now rung R7 of the ladder (`docs/retrieval-plan.md`).
- Eval: about 150 questions, dev 40 and test 110, frozen and tagged before retrieval code. Gold from an independent script, reviewed by Joe (no hand-written subset, so the write-up says independence is weaker). Deterministic metrics lead; RAGAS-style LLM judging is not the headline.
- Every table: no-retrieval LLM, long-context, structured lookups with no LLM, then the ablation ladder.
- Demo: FastAPI and a static page using `textContent` only, on a Hugging Face Docker Space.
- Tooling: Python 3.12+, uv, ruff, pytest, pre-commit; gitleaks 8.30.1 in CI (not installed locally).

- Versions: PEP 440 (packaging), SemVer 2.0 (written here) and a port of Maven 3.9.9 `ComparableVersion`, chosen by OSV range type first. See `docs/adr/0003-version-order-by-range-type.md`.
- Sample: 12 advisories picked by 16 named rules (`data/sample/chosen.json`), copied byte for byte, with `data/ATTRIBUTION.md`. CI never skips the real-data tests: they read `data/raw` if present, else the sample.

## Facts about the data that the evaluation has to respect
- The corpus has no advisory with an open-ended range: every range has a fix or a last affected version. "Still unfixed" questions cannot be built from it.
- OSV records can list packages outside the 18 (RubyGems, Go and so on); 155 such ranges are in the store and ignored in every count.
- 207 of 576 NVD records have no Primary CVSS v3 score: 89 only v2 (old CVEs), 117 only the reporter's score (Secondary), 1 nothing. NVD scores none of them with v4.
- GitHub and NVD give different v3 scores for 65 of 275 pairs that both score; 46 of those change severity band.
- OSV lists three pre-1.0 Django versions (0.91.0, 0.95, 0.96.0) for some advisories and not for others with the same range; the ranges are right to call them affected.
- Fixed versions compared as text: 337 pairs agree, 35 share no version. A version-aware comparison needs NVD's version strings parsed too, and is left to the evaluation work.

- Generator: Sonnet 5.5 for the no-retrieval baseline and later the full system, so the two stay comparable. Monthly ceiling for eval runs and the demo cap: £25.
- Eval mix (150 questions): 30 direct lookup, 35 version-affected, 25 multi-hop, 30 should-abstain (15 trivial, 15 hard, reported apart), 30 sources-disagree. Every type appears in both dev (40) and test (110).
- Gold review: Joe reads all 150 rows in a table (question, gold answer, the GitHub URL it came from) before the tag. No hand-written subset.
- Phase 2 plan approved after review (see `eval/rules.md`): baseline run on the 40 dev questions only until Phase 5; Maven's real 3.9.9 `ComparableVersion` jar (from Maven Central, Java 17) is the outside oracle for Maven gold; tag protection steps given to Joe to apply in GitHub settings. Sonnet 5.5 reliable knowledge and training data cutoffs are both June 2026 (Anthropic models overview, read 2026-11-01), so pre-cutoff is before 2026-06-01, post-cutoff is on or after 2026-07-01, and June is a boundary month.

- GitHub's REST API lists 606 advisories for the 18 packages: 588 not withdrawn, which is exactly the 588 in the corpus (no difference either way), and 18 withdrawn.
- OSV lists affected versions for PyPI and Maven but not for npm, so npm version-affected gold has one independent route (the REST range read with python-semver). Those questions are flagged single-route and kept few.
- Route agreement (REST ranges against OSV's registry lists): PyPI 108,397 agree and 138 differ, Maven 20,828 agree and none differ. Apache Maven 3.9.9's own jar (SHA-1 checked against Maven Central) confirms `5.2.20.RELEASE` equals `5.2.20`.

- Question set built (`eval/questions.jsonl`, `eval/gold.jsonl`, evidence under `eval/evidence/`, review table `eval/review.md`): 150 questions, dev 40 and test 110, all planned counts met. Rebuilding gives byte-identical files. 30% of answerable test questions are post-cutoff, 8 are in the Maven RELEASE slice, 8 rest on a weaker second route (OSV range events, no registry list), 8 are stale-risk. Every gold answer was re-derived by separate code from the raw data, with no differences, and each fact was checked to exist in the corpus the system will hold.
- Rules changed while building (still before any freeze): a scored `value` field was added to the answer schema, and multi-hop pattern C became a comparison between two advisories so that one question never puts the same evidence in both splits.

- Rules changed again after the independent review of the Phase 2 plan, still before any freeze (`eval/rules.md`, `eval/answer_schema.json`): an ID repeated from the question is not fabrication (23 of the 30 abstain questions carry one); `map_id` questions are not aliased; `ids` means the IDs that are the answer; `abstain: true` on an answerable question is wrong; null, `none` and `n/a` read as a silent source; `flagged` means the band differs; a refusal scores wrong and is its own column.
- Scorer and runner written (`eval/score.py`, `eval/run_baseline.py`, `eval/task.md`, `eval/baseline_prompt.md`, `eval/id_snapshot.json`). Baseline settings fixed in the runner: `claude-sonnet-5-5`, effort `high` (the model default), `max_tokens` 16000, adaptive thinking, no fallback model, no temperature, SDK retries off so attempts are counted. `anthropic` pinned to 1.15.0 (2.x was under two weeks old).
- Run order changed: tag `eval-freeze-v1` first, then the dev baseline, 3 runs, with a hard spend cap passed on the command line. The runner refuses a real run unless the frozen files match the tag. A runner or scorer fault found after the tag is fixed under `eval-freeze-v1.1` with the reason in the ADR.

- Dev baseline (Sonnet 5.5, no retrieval, effort high, 40 dev questions, 3 runs, results in `eval/results/`): correct 15/40 in every run, and 7/32 on answerable questions (22%, 95% CI 11 to 39). By type, run 1: lookup 0/8, multi-hop 1/7, sources-disagree 2/8, version 4/9, abstain 8/8. The model declined 31 of 40 questions, so 23 of 32 answerable ones were over-abstentions: the prompt tells it to decline when unsure. Post-cutoff 0/4. The same outcome came up in all three runs for 37 of 40 questions. One invented advisory ID in 120 replies (`GHSA-6757-jp84-gxfp`, run 1, absent from GitHub and OSV). No refusals, no parse failures. Cost $0.70 for 120 calls, median latency 2.4 s.

- Phase 3 plan approved by Joe on 1 November 2026 after review: the soft filter reads IDs and package names only (no version ranges, to keep ADR 0001), no KEV flag in headers, a rung is adopted only with at least 4 net questions and exact McNemar p below 0.05 on all-evidence@10, baseline rows B0 and B1, torch and the ML libraries in an optional dependency group so CI stays fast.

## Open
- Save the GitHub tag-protection ruleset for `eval-freeze-*` (restrict updates and deletions), then confirm with `gh api repos/Jatzo/Otis-AI-Security-Advisor/rulesets`.
- `eval/results/` (three baseline runs, scored file, ID lookup) is not committed yet.
- The test split baseline is not run: it needs `--allow-test`, a single run, and waits for Phase 5.

## Next session
Phase 3, retrieval: propose the package list, chunking, embedding models and the ablation ladder, and ask before locking them in. Tune on dev only.
