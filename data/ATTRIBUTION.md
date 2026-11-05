# Where the data comes from

The data was fetched on 1 November 2026 (snapshot `2d04b933ea7b`, KEV catalogue `2026.10.30`). This file covers the sample in `data/sample/` and anything built from the full snapshot: the store, the passages Otis retrieves and the answers it shows.

## GitHub Advisory Database (`osv/`)

Licence: Creative Commons Attribution 4.0 (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/.
Source: https://github.com/github/advisory-database, fetched through the OSV.dev API.

Changes made: each record is saved as its own file with sorted keys and indentation. No value is edited. Advisories GitHub has withdrawn are not in the snapshot, because OSV.dev leaves them out.

## National Vulnerability Database (`nvd/`)

Source: NIST National Vulnerability Database, NVD API 2.0.
NIST publications are in the public domain. NVD asks services that use its data to show this notice:

This product uses data from the NVD API but is not endorsed or certified by the NVD.

Changes made: each CVE is saved as its own file with sorted keys and indentation. A CVE that NVD does not hold is saved as an empty record marked `notInNvd`, so the gap shows.

## CISA Known Exploited Vulnerabilities catalogue (`kev/`)

Source: https://www.cisa.gov/known-exploited-vulnerabilities-catalog.
Licence: CC0 1.0 Universal, from CISA's licence file for the catalogue. No attribution is required. This project does not use the CISA logo or the DHS Seal, and CISA does not endorse it.

Changes made: in the sample, the catalogue is cut down to the entries for the sampled CVEs, and its `count` is set to match. The full catalogue is not committed.

## Why these advisories are in the sample

`chosen.json` lists the rule that picked each advisory. Each rule names a case the system has to handle.

## Release lists (`releases/`)

Fetched on 5 November 2026 from the PyPI JSON API, the npm registry and Maven Central's `maven-metadata.xml`, for the 18 corpus packages. Only the version numbers are kept, with the source address and the fetch date. They are used by the ingest check ([docs/ingest-check.md](../docs/ingest-check.md)) and are not part of the snapshot.
