# 0011: Check fixed versions against release lists and a second source

- Status: accepted
- Date: 2026-11-05

## Context
The answer checker compares a reply with the record it cites, so a record that lies passes. The red team put a new record with a false fixed version into a list answer in 3 of 4 held-out cases ([red team report](../red-team-report.md), finding 4). The roadmap names an ingest check as the defence: cross-check each record's ranges against a second source, and flag a fix version no release has reached.

The roadmap also said the data defence could be tested for free. The open choice was where the second source comes from: release lists fetched from the registries, or an offline comparison of GitHub with NVD.

## Decision
- **Two signals, with different powers.** R, the release list, holds a record back. X, the GitHub against NVD comparison, only marks a record unverified. Both can say "cannot check", and a fix of 0, a missing fix, a Maven token such as RELEASE and a package with no list are never judged.
- **Release lists are fetched, and stored apart from the snapshot.** `python -m advisor.ingest releases` writes `data/releases/` with the fetch date and a hash for each of the 18 files. They are small (90 KB), committed, and read by tests from a made-up sample, so CI never fetches. A registry's list grows over time, so a list is dated and kept separate from `data/raw`.
- **The check lives outside the tagged system.** It is in `src/advisor/integrity/` and works on an in-memory copy of the store, the way the poison builder does. Putting a hold-back into retrieval is a separate decision and would need a new system tag.
- **The measures were fixed first**, in the plan. The first rule for R is the main result. A refined rule, which leaves pre-release tags and versions older than a registry's list unjudged, was written after I read the 16 records the first rule flagged. It is reported beside the first, labelled as fitted, and does not replace it.
- **Two kinds of lie are built by a rule** to test it fairly, because the red team's 99.99.99 and 88.88.88 are caught by any release list by construction. One names the next patch above the latest release. The other names the nearest earlier release. The sample is 24 real advisories drawn with seed 20261104.

## Alternatives not taken
- **Only the offline GitHub against NVD comparison.** No network and no new files, but both sources can repeat the same wrong version, and it flagged 8.2% of the real records it could check.
- **Hold back on X as well.** It would remove 33 real records, and I read all 33: none looks like a lie.
- **A fixed list of "old" versions to skip.** The refined rule is one comparison with the registry's own oldest listed release, which does not need a table kept up to date.
- **Judge the first rule only.** It flags 16 real records, 11 of them for reasons that are about the lists and not the records. Reporting both shows the cost of the plain rule and the fitted one.

## Consequences
- Against the roadmap's adoption rule, holding back R's flags misses the frozen-set part (B2 had no successes there), meets the held-out part by construction (R flags all four B2 records, so the model never sees them) and costs no dev answer. The model was not run, so the held-out result is by design, not measured.
- A lie that names a real release gets past R. X sees it only where the record keeps a real CVE alias and NVD holds an end version, and X is a flag.
- Five real records stay flagged under the refined rule. They may be faults in the advisories or gaps in the registries, and I have not established which.
- No defence has been tested with the model.
