# Ingest check: can a false record be found before it is used

No defence has been tested with the model. This is a check on the records, measured without one.

## Why

The checker compares a reply with the record it cites, so a record that lies passes ([red team report](red-team-report.md), finding 4). A new record with a false fixed version got into a list answer in 3 of 4 held-out cases. The check here looks at the record before anything uses it.

## What it does

[src/advisor/integrity/check.py](../src/advisor/integrity/check.py) gives each GitHub record two verdicts. Each can also say "cannot check".

- **R, the release list.** The fixed version must be one the package's registry has published. PyPI, npm and Maven lists for the 18 packages are fetched by `python -m advisor.ingest releases` and stored in `data/releases/`, apart from the snapshot, with the fetch date (5 November 2026) and a hash of each file. A version that no registry lists is the signal. R is the only signal that holds a record back.
- **X, the second source.** The fixed versions GitHub gives must share a version with the end versions NVD gives for the same CVE. X only marks a record unverified. It never holds one back, because real sources differ.

The measures were written before the first run: how many real records each signal flags, with every flag read by hand; what holding back R's flags costs in dev retrieval; what both say about the 8 red team B2 records; and what they say about 24 real advisories lied about in two ways built by a rule (seed 20261104). The script is [scripts/measure_ingest_check.py](../scripts/measure_ingest_check.py) and the figures are in `eval/results/ingest-check.json`.

## What the real records gave

588 GitHub records have a range on one of the 18 packages.

| | R as first written | R refined | X |
|---|---|---|---|
| Flagged | 16 (2.7%) | 5 (0.85%) | 33 (8.2% of the 404 it could check) |
| Passed | 571 | 571 | 371 |
| Cannot check | 1 | 12 | 184 |

**R, as first written: 16 records, all real.** I read each. Eleven are not a fault in the record.
- Fourteen of the 23 distinct unlisted fixed versions are Django 0.91 to 1.1.1. PyPI's list starts at 1.1.3, so it cannot speak for them.
- Two are pre-release tags (1.7b4, 1.7c3) that PyPI does not keep.

The other five records are not explained by the lists, and I did not find out why.
- Django 1.11.19, 2.0.11 and 2.1.6 are absent from PyPI, while 1.11.20 and 2.1.7 are there (`GHSA-wh4h-v3f2-r2pp`).
- Spring 5.3.42 is above Maven Central's last listed 5.3.x, 5.3.39 (`GHSA-w3c8-7r8f-9jp8`).
- Struts 2.1.1, 2.1.3 and 2.5.11 are absent from Central while their neighbours are listed (`GHSA-jgcr-9c2q-rvp8`, `GHSA-wv7g-xhvw-8hcp`, `GHSA-8fx9-5hx8-crhm`).

These may be mistakes in the advisories, or releases the registry does not hold. I have not checked them against the projects' release notes.

**R, refined.** I then made R leave pre-release tags and versions older than a registry's list unjudged. That leaves the five above. It was written after reading the records the first rule flagged, so its count is fitted to them. The first rule is the main result.

**X: 33 records, all real.** I read each. About 26 are two sources fixing a flaw at versions one patch release apart (Pillow 8.1.2 against 8.1.1, Struts, Django 4.2.22 against 4.2.23, axios 1.15.2 against 1.15.1). About 7 are NVD listing versions of other products under the same CVE, such as OpenSSL versions under `cryptography`. None looks like a lie. X is a flag for a person to look at.

## What holding back costs

Removing R's flagged records from a copy of the store, with either rule, leaves all-evidence at 10 on the dev questions at 24 of 32, the same as the clean store. No dev question changes. That is 16 records held back as first written and 5 refined.

## What it found among the lies

| Records | R | X |
|---|---|---|
| The 8 red team B2 records (99.99.99 and 88.88.88) | 8 of 8 | 5 of 8; 3 cannot be checked |
| 24 real advisories, fixed version made the next patch above the latest release | 24 of 24 | 19 of 19 it could check; 5 cannot be checked |
| 24 real advisories, fixed version made the nearest earlier release | 0 of 24 | 19 of 19 it could check; 5 cannot be checked |

Three limits go with this table.
- R catches the B2 records and the unreleased kind by construction. No registry lists 99.99.99. It misses the earlier-release kind by construction, because that version is real. These are limits of the design.
- X catches the made-up records because I kept the real CVE alias on them, and the lie differs from NVD's version. An attacker who leaves the alias off makes X say it cannot check. The five it cannot check lack an NVD end version.
- X flags 8.2% of the real records it can check. Used as a hold-back it would remove 33 real records, so it stays a flag.

## Against the written adoption rule

The roadmap keeps a defence only if it removes at least 3 successes in its class on the frozen set, holds on the held-out set, and costs at most one correct dev answer. Holding back R's flags:
- **Frozen set:** misses the rule. B2 had 0 successes there, so there is nothing to remove.
- **Held-out set:** B2 had 3 successes in 4, and R flags all 4 records, so the record never reaches the model. That meets the rule by construction. I did not run the model on it.
- **Dev cost:** 0 answers, under either R.

So it meets two of the three parts. It has not been run with the model, and the three held-out successes are removed by design and not measured.

## What this does not show

- A lie that names a real release gets past R. Only X can see it, and X is a flag.
- The release lists were fetched on 5 November 2026 and will change. The check would need fresh lists in use.
- The five records R still flags may be real data faults that the check has found, or registry gaps. Someone should look at them.
- Nothing here is wired into retrieval. Doing so would change the tagged system and needs a new system tag.

Files: `data/releases/` (18 lists and a manifest), `eval/results/ingest-check.json`, `src/advisor/integrity/`, `src/advisor/ingest/releases.py`, tests in `tests/test_integrity.py` and `tests/test_releases.py`. Decision: [ADR 0011](adr/0011-check-fixed-versions-against-release-lists-and-a-second-source.md).
