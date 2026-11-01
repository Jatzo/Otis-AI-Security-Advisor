# Evaluation rules

Status: draft for checkpoint 1. These rules freeze with the questions and the gold (tag `eval-freeze-v1`). Nothing here is written after seeing how any retrieval system performs.

Snapshot: `2d04b933ea7b` (data fetched 1 November 2026). Generator under test: Claude Sonnet 5.5. Its reliable knowledge cutoff and its training data cutoff are both June 2026, from Anthropic's models overview.

## 1. What this eval measures, and what it does not

It measures whether an answer is faithful to three sources: the GitHub Advisory Database, the National Vulnerability Database and the CISA KEV catalogue, as they stood on the snapshot date, for 18 packages. It does not measure whether those sources are true.

The gold does not come from the system's store or its code. It comes from a separate script, `make_gold.py`, that reads GitHub's REST API and the raw NVD and KEV files with its own parsing. That makes it independent in code and format. It is not independent in facts: GitHub's REST API and OSV.dev serve the same advisory database, and NVD often copies from GitHub or the reverse. The write-up says so.

## 2. Scope the system is told

Every system under test, the no-retrieval baseline included, is told this scope in plain words:

- 18 packages: PyPI django, flask, jinja2, requests, urllib3, pillow, pyyaml, cryptography, aiohttp; npm lodash, express, axios, jsonwebtoken, ws, minimist; Maven log4j-core, spring-webmvc, struts2-core.
- Three sources: GitHub-reviewed advisories, NVD records for the CVEs those advisories name, and the CISA KEV catalogue.
- A snapshot date of 1 November 2026. Withdrawn advisories are not included.

A question outside this scope is one the system should decline. A system that was never told the scope cannot be judged for declining.

## 3. Questions

150 questions: 40 in dev, 110 in test. The system is tuned on dev only. Test is scored once per system.

| Type | Dev | Test | Total |
|---|---|---|---|
| Direct lookup | 8 | 22 | 30 |
| Version-affected | 9 | 26 | 35 |
| Multi-hop | 7 | 18 | 25 |
| Should-abstain (trivial 4 + hard 4 dev; 11 + 11 test) | 8 | 22 | 30 |
| Sources-disagree (about 3 dev and 7 test are agree-controls) | 8 | 22 | 30 |

Split rules:

- Assignment is by a seeded hash of the question's advisory group, not of the question, so no advisory or CVE appears in both dev and test. An advisory group is an advisory plus every CVE it names.
- No advisory is the subject of more than 2 questions. KEV has only 10 advisories, so KEV questions are capped by that rule.
- Each type uses 2 or 3 different wordings. Every question records its template id.
- Questions are drawn by a seeded random sample (seed 20261101) from the facts that fit each question kind, with fixed quotas by ecosystem for version questions. The seed and the script are in the repository, and the build is repeatable byte for byte.

### 3.1 Direct lookup (30)

A single fact about one record: affected versions, first fixed version, GitHub's severity label, the CVE that goes with a GHSA ID (or the reverse), whether the CVE is on KEV. Fifteen name the advisory by ID. Fifteen describe it in different words from the advisory summary, hand-paraphrased, so that matching on the summary text cannot find it.

### 3.2 Version-affected (35)

Twenty ask whether one package version is affected by one advisory (yes or no; ten of each). Fifteen ask which advisories affect one package version (an ID list of at most 10). Versions are chosen at the edges: just below a fixed version, the fixed version itself, and the gap between two ranges for the advisories that have more than one range.

The gold needs two independent routes to agree: the GitHub REST range read with `packaging.specifiers` (PyPI), `semver` (npm) and `univers` (Maven), and OSV's registry-derived list of affected versions. For Maven, the real Apache Maven 3.9.9 `ComparableVersion` is a third route. A question where the routes disagree is dropped, and the number dropped is reported by reason. Maven versions with a `RELEASE` suffix are kept and reported as their own slice.

### 3.3 Multi-hop (25)

The answer needs more than one record or more than one source. Three patterns: a cross-source join, such as advisory to CVE to NVD score, or the advisories for a package whose CVE is on KEV (10); an intersection, such as the advisories for a package that affect one version and carry one severity (9); a comparison between two named advisories, such as which was published first or which has the higher GitHub score (6). Answers are at most 10 items. In the review table every item shows its derivation and its evidence link.

A comparison names two advisories, so both belong to one split. A count across a whole package would put the same evidence in both splits, which the grouping rule forbids.

A system that retrieves once and answers will do worse here. That is expected and is reported on its own line.

### 3.4 Should-abstain (30)

The correct answer is that the corpus does not hold what was asked.

- Trivial (15): an invented ID in a plausible format, a package that does not exist, or a question that is not about security advisories.
- Hard (15): a withdrawn GHSA ID that GitHub's REST API still serves (6); a real advisory for a package outside the 18 (5); a field the corpus does not hold, such as EPSS or exploit code (4).

Trivial and hard are reported apart. Over-abstention (declining an answerable question) is reported next to answerable accuracy, so declining everything cannot score well.

### 3.5 Sources-disagree (30)

Twenty questions where the sources differ and ten agree-controls where they do not, so always answering "they disagree" scores badly. The answer must say whether they differ and give both values.

## 4. When the sources disagree

GitHub is the CNA for many of the CVEs involved, so a matching score may be a copy. Agreement is reported as agreement, not as independent confirmation.

- D1, severity band (about 9 disagreeing, plus the agree-controls). The CVSS v3 base scores of GitHub and NVD fall in different bands: none (0), low (0.1 to 3.9), medium (4.0 to 6.9), high (7.0 to 8.9), critical (9.0 and above). The values given are the two v3 scores as published, GitHub's from its REST record and NVD's `baseScore`, written with one decimal. A v4 score is never used here.
- D2, fixed version (about 5). GitHub's first patched versions and NVD's `versionEndExcluding` values share no version. Only cases where every version is plain dotted-numeric and the CVE has a single release branch are used, so no in-repo comparator decides the gold. The values given are the version lists.
- D3, one source silent (about 6). GitHub scores the CVE and the NVD record holds no CVSS v3 score of any kind (awaiting analysis, deferred, rejected, or only a v2 score). A record whose only v3 score is the reporter's own, marked Secondary, is not used, because a reader could fairly call that NVD's score. The values are the GitHub score and `none`.

Where the two scores differ but stay in the same band, the sources agree under D1. The exact scores are in the gold and shown in the review table.

## 5. The answer

Every system returns one JSON object whose scored fields are in `answer_schema.json`. The scorer reads only those fields and ignores any others, so later phases can add fields (for example a citation per claim) without changing the freeze.

- `abstain`: true when the sources do not support an answer.
- `verdict`: `yes`, `no` or null, for questions that ask whether something is true.
- `ids`: GHSA and CVE IDs the answer relies on or lists.
- `value`: a single fact as plain text, for questions that ask for one: a version, a score or a severity label. Null otherwise.
- `disagreement`: whether the sources differ, with both values as text (`github`, `nvd`), null where a source says nothing.
- `explanation`: free text.

## 6. Scoring

All scoring is deterministic code. No model judges an answer.

- IDs are normalised through an alias map built from the raw data, so a GHSA ID and its CVE ID count as the same advisory. Versions compare equal when they differ only in trailing zeros (`2.25` and `2.25.0`).
- Each question's gold names the one field that answers it: `ids`, `verdict`, `value` or `disagreement`. That field alone decides whether the answer is correct. The other fields are read only for the fabrication rate.
- Direct lookup and multi-hop: correct when the answering field matches the gold exactly. For an ID set, set F1 is reported next to it.
- A `value` is compared after normalising: versions as in the line above, severity labels in lower case with `medium` read as `moderate` (GitHub's advisory database and OSV say moderate, its REST API says medium), scores to one decimal place.
- Version-affected: correct when the verdict matches (yes or no), or when the ID set matches.
- Should-abstain: correct when `abstain` is true. Any ID in the answer counts toward the fabrication rate whatever else it says.
- Sources-disagree: correct only when `disagreement.flagged` matches the gold and both values match.
- Every ID in an answer, including IDs inside `explanation`, gets one label: in the corpus; real but outside the scope (checked against GitHub's REST API, NVD and OSV, withdrawn advisories included); or nonexistent. Only nonexistent IDs count as fabrication.
- An answer that does not parse against the schema is counted in its own column and scored as wrong.
- Yes/no questions are balanced, and the majority-class floor is reported.
- Cost per query (tokens and price) and latency are recorded for every call.

## 7. Slices

- Pre-cutoff: every date on the evidence (the advisory's published date, its CVE's NVD published date) is before 1 June 2026.
- Post-cutoff: the earliest of those dates is on or after 1 July 2026. At least 20 percent of answerable test questions are post-cutoff.
- June 2026 is the boundary month and belongs to neither slice.
- Stale-risk: the evidence was published before the cutoff but modified after it, so a model may remember an older version of the record. Flagged, not excluded.
- Maven `RELEASE` slice, and ecosystem, reported as slices. The post-cutoff slice is about three quarters PyPI and holds almost no KEV records, so it is not compared type by type.

## 8. Statistics

Per-type groups are small (18 to 26 in test), so:

- Report counts (`17/22`), not only percentages, with 95 percent Wilson intervals. Gaps under about 30 points within one type are not claimed as differences.
- Compare a system with the baseline on the questions where they disagree, with an exact McNemar test, and show the per-question table.
- Pooled comparisons across types are stronger and are reported first.
- The comparisons below are named before the freeze and are the only ones given a headline:
  1. Correct rate on all test questions, system against baseline.
  2. Correct rate on the answerable test questions only.
  3. Fabrication rate.
  4. Abstention precision and recall, and over-abstention.
  5. Sources-disagree correctness.
  6. The baseline on the pre-cutoff and post-cutoff slices.
- The retrieval ladder is compared on dev only. Test is scored once.

## 9. Freeze and errata

- Frozen: everything under `eval/` except `eval/results/` and `eval/errata.jsonl`. The REST records the gold used are committed under `eval/evidence/`, so the gold can be checked offline.
- The guard compares git blobs with the `eval-freeze-v1` tag, fails if the tag is missing, and runs offline in CI.
- A mistake found in the gold after the freeze goes into `errata.jsonl` as an appended line. Scores are reported both as frozen and with the errata applied. A frozen file is not edited.
