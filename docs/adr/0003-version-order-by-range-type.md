# 0003: Versions are ordered by PEP 440, SemVer 2.0 and Maven 3.9.9, chosen by range type

- Status: accepted
- Date: 2026-11-01

## Context
"Is 2.25.0 affected?" is answered by comparing it with the introduced and fixed versions in an advisory's ranges. Each ecosystem orders versions differently, and a wrong order gives a wrong answer with no error. The corpus has 673 PyPI ranges and 295 Maven ranges that OSV marks `ECOSYSTEM`, and 160 npm ranges it marks `SEMVER`. Advisories also list ranges for other ecosystems (RubyGems, Go and so on); those are kept in the store and ignored in every count.

## Decision
- **The comparator is chosen by range type first, then ecosystem.** `SEMVER` means SemVer 2.0 whatever the ecosystem. `ECOSYSTEM` means PEP 440 for PyPI and Maven's order for Maven. Any other combination raises, so a new ecosystem cannot be answered by accident.
- **PyPI uses the `packaging` library**, pinned. PEP 440 is large and `packaging` is its reference implementation.
- **npm is SemVer 2.0 written here**, about 25 lines from the spec. Build metadata is ignored, as the spec says.
- **Maven is a port of `ComparableVersion` from Apache Maven 3.9.9.** The release is named because Maven has changed the rules over time. In 3.9.9 a `RELEASE` suffix is the empty qualifier, so `5.2.20.RELEASE` equals `5.2.20`. Every `spring-webmvc` fixed version carries that suffix.
- **A version a comparator cannot parse raises `UnparseableVersion`.** It is never guessed at. An `introduced` of `0` means "from the first version" and is handled before parsing, because `0` is not valid SemVer.

## Evidence
- Maven's own `ComparableVersionTest` vectors from 3.9.9 pass, and so do the SemVer spec examples.
- OSV lists every registry version it considers affected for 511 of the 588 advisories. That list comes from the registries, not from this code. All 44,733 listed versions come out affected under the ranges and comparators, and none failed to parse.
- The other direction: of 214,771 (advisory, known version) pairs that OSV does not list, 137 come out affected. All 137 are three pre-1.0 Django versions (`0.91.0`, `0.95`, `0.96.0`) that OSV lists for some advisories with ranges starting at 0 and not for others. That is an upstream inconsistency, named in the tests.
- A second implementation, `univers`, agrees with the SemVer code on all 3,321 pairs of real npm versions. For Maven it differs on 17 of 143,380 pairs, every one involving a `RELEASE` suffix.

## Alternatives not taken
- **`univers` for all three ecosystems.** It reads a `RELEASE` suffix differently from Maven 3.9.9, which would shift every `spring-webmvc` range, and it brings three more runtime packages. It stays as a development-only cross-check.
- **Writing PEP 440 here.** More code and more ways to be wrong than the library that defines the behaviour.
- **Comparing versions as numbers split on dots.** Wrong for `rc`, `post`, `-SNAPSHOT` and every Maven qualifier, and wrong silently.

## Consequences
- If the 3.9.9 reading of `RELEASE` is not what a Spring user's build tool does, `spring-webmvc` answers are off by one release. The tests pin the reading so a change is a visible decision.
- The first range comparison with NVD in the data report is still text only. A version-aware comparison needs NVD's version strings parsed too, and is left to the evaluation work.
