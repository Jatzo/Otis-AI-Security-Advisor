"""The comparators against real advisories.

OSV lists, for most advisories, every registry version it considers affected. That list is
produced from the registries, not by this code, so it is an independent check on the ranges
and the comparators together. These tests read data/raw when it is there and the committed
sample otherwise; with neither, they fail rather than skip, so CI cannot pass on nothing.
"""

import itertools
from collections import defaultdict
from pathlib import Path

import pytest
from univers.versions import MavenVersion, SemverVersion

from advisor import store, versions
from advisor.ingest import raw
from advisor.packages import PACKAGES

CORPUS = {(p.ecosystem, p.name) for p in PACKAGES}
# OSV lists these three pre-1.0 Django releases for some advisories and not for others
# whose ranges also begin at 0; the ranges are right to call them affected.
UNLISTED_BUT_AFFECTED = {("django", "0.91.0"), ("django", "0.95"), ("django", "0.96.0")}


@pytest.fixture(scope="module")
def entries():
    """(ecosystem, package, [(range type, spans)], listed versions) for each corpus package
    an advisory names, with GIT ranges left out as the store leaves them."""
    root = Path("data/raw/osv")
    if not any(root.glob("GHSA-*.json")):
        root = Path("data/sample/osv")
    paths = raw.record_paths(root)
    assert paths, "No advisories to test against: expected data/raw/osv or data/sample/osv"
    found = []
    for path in paths:
        for affected in raw.read_record(path).get("affected", []):
            package = affected["package"]
            if (package["ecosystem"], package["name"]) not in CORPUS:
                continue
            ranges = [
                (r["type"], store.spans(r["events"]))
                for r in affected.get("ranges", [])
                if r["type"] != "GIT"
            ]
            found.append(
                (package["ecosystem"], package["name"], ranges, set(affected.get("versions", [])))
            )
    return found


def test_every_version_in_a_range_parses_under_its_ecosystems_rules(entries):
    for ecosystem, _, ranges, _ in entries:
        for range_type, spans in ranges:
            compare = versions.comparator(ecosystem, range_type)
            for span in spans:
                for version in span:
                    if version not in (None, "0"):
                        compare(version, version)


def test_every_version_osv_lists_as_affected_is_affected_under_the_ranges(entries):
    contradictions = [
        (package, version)
        for ecosystem, package, ranges, listed in entries
        for version in listed
        if not any(versions.is_affected(ecosystem, t, version, spans) for t, spans in ranges)
    ]

    assert contradictions == []


def test_ranges_do_not_reach_versions_that_other_advisories_list_but_this_one_does_not(entries):
    universe = defaultdict(set)
    for ecosystem, package, _, listed in entries:
        universe[(ecosystem, package)] |= listed
    too_wide = {
        (package, version)
        for ecosystem, package, ranges, listed in entries
        if listed
        for version in universe[(ecosystem, package)] - listed
        if any(versions.is_affected(ecosystem, t, version, spans) for t, spans in ranges)
    }

    assert too_wide <= UNLISTED_BUT_AFFECTED


def real_strings(entries, ecosystem):
    strings = set()
    for eco, _, ranges, listed in entries:
        if eco == ecosystem:
            strings |= listed
            strings |= {
                v for _, spans in ranges for span in spans for v in span if v not in (None, "0")
            }
    return sorted(strings)


def test_semver_order_matches_a_second_implementation_on_real_npm_versions(entries):
    for a, b in itertools.combinations(real_strings(entries, "npm"), 2):
        theirs = (SemverVersion(a) > SemverVersion(b)) - (SemverVersion(a) < SemverVersion(b))
        assert versions.compare_semver(a, b) == theirs, (a, b)


def test_maven_order_matches_a_second_implementation_except_where_it_reads_release_differently(
    entries,
):
    # The other implementation does not treat a RELEASE suffix as the empty qualifier, which
    # Maven 3.9.9 does. Any other difference would be a real fault in the port.
    for a, b in itertools.combinations(real_strings(entries, "Maven"), 2):
        if "release" in a.lower() or "release" in b.lower():
            continue
        theirs = (MavenVersion(a) > MavenVersion(b)) - (MavenVersion(a) < MavenVersion(b))
        assert versions.compare_maven(a, b) == theirs, (a, b)
