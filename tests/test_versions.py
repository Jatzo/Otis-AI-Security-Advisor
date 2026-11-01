"""Version ordering. The Maven vectors are copied from Apache Maven 3.9.9's own
ComparableVersionTest, the SemVer ones from the semver.org precedence examples."""

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from advisor import versions
from advisor.versions import UnparseableVersion, compare_maven, compare_pypi, compare_semver


def assert_ascending(compare, sequence):
    for low, high in itertools.combinations(sequence, 2):
        assert compare(low, high) < 0, f"expected {low} < {high}"
        assert compare(high, low) > 0, f"expected {high} > {low}"


def assert_equal(compare, *group):
    for a, b in itertools.product(group, repeat=2):
        assert compare(a, b) == 0, f"expected {a} == {b}"


MAVEN_QUALIFIER_ORDER = [
    "1-alpha2snapshot", "1-alpha2", "1-alpha-123", "1-beta-2", "1-beta123", "1-m2", "1-m11",
    "1-rc", "1-cr2", "1-rc123", "1-SNAPSHOT", "1", "1-sp", "1-sp2", "1-sp123", "1-abc",
    "1-def", "1-pom-1", "1-1-snapshot", "1-1", "1-2", "1-123",
]  # fmt: skip
MAVEN_NUMBER_ORDER = [
    "2.0", "2.0.a", "2-1", "2.0.2", "2.0.123", "2.1.0", "2.1-a", "2.1b", "2.1-c", "2.1-1",
    "2.1.0.1", "2.2", "2.123", "11.a2", "11.a11", "11.b2", "11.b11", "11.m2", "11.m11", "11",
    "11.a", "11b", "11c", "11m",
]  # fmt: skip


def test_maven_orders_qualifiers_as_maven_does():
    assert_ascending(compare_maven, MAVEN_QUALIFIER_ORDER)


def test_maven_orders_numbers_and_letters_as_maven_does():
    assert_ascending(compare_maven, MAVEN_NUMBER_ORDER)


@pytest.mark.parametrize(
    "group",
    [
        ["1", "1.0", "1.0.0", "1-0", "1.0-0"],
        ["1a", "1-a", "1.0-a", "1.0.0-a", "1.0a"],
        ["1ga", "1release", "1final", "1", "1Ga", "1RELEASE", "1FinaL"],
        ["1cr", "1rc", "1Cr", "1cR"],
        ["1a1", "1-alpha-1"],
        ["1b2", "1-beta-2"],
        ["1m3", "1-milestone-3", "1MILESTONE3"],
        ["0000000000000000001", "01", "1"],
        ["0000000000000000000", "0"],
        ["1-abcdefghijklmnopqrstuvwxyz", "1-ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
    ],
)
def test_maven_treats_these_spellings_as_the_same_version(group):
    assert_equal(compare_maven, *group)


@pytest.mark.parametrize(
    ("low", "high"),
    [
        ("1.5", "2"),
        ("1.0.1", "1.1"),
        ("1.1", "1.2.0"),
        ("1.0-alpha-1", "1.0"),
        ("1.0-beta-1", "1.0-SNAPSHOT"),
        ("1.0-alpha-1-SNAPSHOT", "1.0-alpha-1"),
        ("1.0", "1.0-1"),
        ("1.0.0", "1.0-1"),
        ("2.0-1", "2.0.1"),
        ("2.0.1", "2.0.1-xyz"),
        ("2.0.1-xyz", "2.0.1-123"),
        ("6.1.0rc3", "6.1.0"),
        ("6.1.0rc3", "6.1H.5-beta"),
        ("6.1.0", "6.1H.5-beta"),
        ("20190126.230843", "1234567890.12345"),
        ("123456789012345.1H.5-beta", "12345678901234567890.1H.5-beta"),
        ("1-0.alpha", "1"),
        ("1-0.beta", "1"),
        ("1-0.alpha", "1-0.beta"),
        ("1.0.0.RC1", "1.0.0-RC2"),
    ],
)
def test_maven_orders_the_edge_cases_in_its_bug_reports(low, high):
    assert compare_maven(low, high) < 0
    assert compare_maven(high, low) > 0


@pytest.mark.parametrize("word", ["abc", "alpha", "a", "beta", "b", "def", "milestone", "m", "RC"])
def test_maven_reads_a_dotted_word_like_a_hyphenated_one(word):
    assert_equal(compare_maven, f"2-{word}", f"2.0.{word}", f"2.0.0.{word}")


def test_a_spring_release_suffix_is_the_same_version_as_without_it():
    # spring-webmvc fixed versions look like 5.2.20.RELEASE. Maven 3.9.9 reads RELEASE as
    # the empty qualifier, so the two are equal. An older or different reading would make
    # every spring-webmvc range off by one.
    assert compare_maven("5.2.20.RELEASE", "5.2.20") == 0
    assert compare_maven("5.2.19.RELEASE", "5.2.20.RELEASE") < 0


def test_an_empty_maven_version_is_refused():
    with pytest.raises(UnparseableVersion):
        compare_maven("  ", "1")


def test_semver_follows_the_spec_example_for_precedence():
    spec = [
        "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
        "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0",
    ]  # fmt: skip
    assert_ascending(compare_semver, spec)
    assert_ascending(compare_semver, ["1.9.0", "1.10.0", "1.11.0", "2.0.0"])


def test_semver_ignores_build_metadata():
    assert compare_semver("1.0.0+20130313144700", "1.0.0+exp.sha.5114f85") == 0


@pytest.mark.parametrize("text", ["1.0", "v1.0.0", "01.0.0", "1.0.0-", "1.0.0-01", "latest", ""])
def test_semver_refuses_what_is_not_semver(text):
    with pytest.raises(UnparseableVersion):
        compare_semver(text, "1.0.0")


def test_pypi_follows_pep_440_ordering():
    assert_ascending(
        compare_pypi, ["1.0.dev1", "1.0a1", "1.0b2", "1.0rc1", "1.0", "1.0.post1", "1.0.1"]
    )
    assert compare_pypi("1.0", "1.0.0") == 0


def test_pypi_refuses_what_is_not_a_pep_440_version():
    with pytest.raises(UnparseableVersion):
        compare_pypi("not-a-version", "1.0")


def test_a_semver_range_uses_semver_whatever_the_ecosystem():
    assert versions.comparator("npm", "SEMVER") is compare_semver
    assert versions.comparator("Go", "SEMVER") is compare_semver


def test_an_ecosystem_with_no_order_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="No version order"):
        versions.comparator("npm", "ECOSYSTEM")
    with pytest.raises(ValueError, match="No version order"):
        versions.comparator("RubyGems", "ECOSYSTEM")


SPANS = [("1.0", "1.5", None), ("2.0", None, "2.3")]


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.9", False),  # before anything was introduced
        ("1.0", True),  # introduced is inclusive
        ("1.4.9", True),
        ("1.5", False),  # fixed is exclusive
        ("1.9", False),  # between the two spans
        ("2.0", True),
        ("2.3", True),  # last_affected is inclusive
        ("2.3.1", False),
    ],
)
def test_a_version_is_affected_only_inside_a_span(version, expected):
    assert versions.is_affected("PyPI", "ECOSYSTEM", version, SPANS) is expected


def test_introduced_zero_means_every_earlier_version_and_is_never_parsed():
    assert versions.is_affected("npm", "SEMVER", "0.0.1", [("0", "1.2.3", None)])
    assert not versions.is_affected("npm", "SEMVER", "1.2.3", [("0", "1.2.3", None)])


def test_a_span_with_no_end_covers_every_later_version():
    assert versions.is_affected("Maven", "ECOSYSTEM", "99.0", [("2.0", None, None)])


def test_an_unparseable_version_in_a_span_raises_instead_of_answering():
    with pytest.raises(UnparseableVersion):
        versions.is_affected("npm", "SEMVER", "1.0.0", [("1.0", None, None)])


# Versions built from the parts the corpus really has: numbers, dots, hyphens, short words.
maven_versions = st.text(alphabet="0123456789.-abcmrsxz", min_size=1, max_size=10).filter(
    lambda text: text.strip()
)
semver_versions = st.builds(
    lambda major, minor, patch, pre: f"{major}.{minor}.{patch}" + (f"-{pre}" if pre else ""),
    st.integers(0, 12),
    st.integers(0, 12),
    st.integers(0, 12),
    st.one_of(
        st.just(""),
        st.lists(
            st.sampled_from(["alpha", "beta", "rc", "0", "1", "11", "x-y"]), min_size=1, max_size=3
        ).map(".".join),
    ),
)


@given(a=maven_versions, b=maven_versions)
def test_maven_comparison_reads_the_same_both_ways_round(a, b):
    assert compare_maven(a, b) == -compare_maven(b, a)


@given(a=maven_versions, b=maven_versions, c=maven_versions)
def test_maven_order_is_transitive(a, b, c):
    if compare_maven(a, b) <= 0 and compare_maven(b, c) <= 0:
        assert compare_maven(a, c) <= 0


@given(a=semver_versions, b=semver_versions, c=semver_versions)
def test_semver_order_is_transitive_and_reads_the_same_both_ways_round(a, b, c):
    assert compare_semver(a, b) == -compare_semver(b, a)
    if compare_semver(a, b) <= 0 and compare_semver(b, c) <= 0:
        assert compare_semver(a, c) <= 0


@given(version=semver_versions, fixed=semver_versions)
def test_with_one_span_a_version_is_affected_exactly_when_it_is_below_the_fixed_one(version, fixed):
    below = compare_semver(version, fixed) < 0
    assert versions.is_affected("npm", "SEMVER", version, [("0", fixed, None)]) is below


def test_a_maven_version_long_enough_to_overflow_the_stack_is_refused():
    deep = "1" + "-1" * 1500

    with pytest.raises(UnparseableVersion):
        compare_maven(deep, deep)


def test_semver_digits_are_ascii_only():
    with pytest.raises(UnparseableVersion):
        compare_semver("1\u0662.0.0", "12.0.0")  # the second digit is Arabic-Indic
