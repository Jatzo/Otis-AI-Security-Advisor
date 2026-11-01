# 0002: GitHub advisories come from OSV.dev, NVD is joined by CVE ID, and each source keeps its own row

- Status: accepted
- Date: 2026-11-01

## Context
The corpus needs three sources for 18 packages: GitHub-reviewed advisories, NVD and CISA KEV. They describe the same vulnerabilities in different shapes. GitHub names packages and gives version ranges. NVD names software by CPE and scores it itself, often later and sometimes differently. KEV lists CVE IDs only.

Counted on 2026-11-01: GitHub's advisory API lists 605 reviewed advisories for the 18 packages; OSV.dev returns 588 of them, because it leaves out the 17 that GitHub has withdrawn.

## Decision
- **GitHub advisories come from the OSV.dev query API**, filtered to `GHSA-` IDs. It needs no token, gives structured version events (introduced, fixed, last affected), and the same records appear in the GitHub Advisory Database under CC BY 4.0.
- **Withdrawn advisories are out of the corpus**, as OSV.dev serves it. Questions about them belong in the eval as "should not be reported" cases.
- **NVD is fetched by CVE ID**, using the aliases on the GitHub records, rather than searched by CPE. CPE matches are stored for later checks, not used for the join.
- **Each source keeps its own row.** A CVE described by GitHub and NVD is two records. Scores are computed from each vector by the same library, so a difference in scores is a difference in the vectors, not in arithmetic.
- **NVD's own (Primary) score is used, not the reporter's (Secondary) copy.** A CVE NVD has not analysed has no NVD score, and that gap is kept as data.

## Alternatives not taken
- **GitHub's REST advisory API.** It has numeric scores and includes withdrawn records, but needs a token in CI. It is kept for the independent gold-answer script, so the gold and the system read GitHub through different paths.
- **Cloning github/advisory-database.** Several gigabytes of history for 588 records.
- **Searching NVD by CPE.** CPE names for libraries are inconsistent (vendor and product strings vary), so a CPE search would miss records or pull in other products. Joining on the CVE ID GitHub already gives is exact.
- **Merging sources into one row per CVE.** Simpler to query, but it would decide every disagreement silently, which is the thing the system exists to show.

## Consequences
- A CVE with no GitHub advisory for these packages is not in the corpus, even if NVD lists one of them by CPE. The coverage claim is "what GitHub has reviewed for these packages".
- The 11 fetched GitHub advisories with no CVE ID have no NVD record, by construction.
- Without an NVD API key the fetch takes about an hour; it is resumable and run rarely.
