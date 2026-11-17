"""The evidence-round retrieval candidates, on a small made-up corpus. No store, no network."""

from advisor.retrieval import candidates
from advisor.retrieval.units import Unit

PACKAGES = ["django", "org.apache.logging.log4j:log4j-core", "axios"]


def unit(unit_id: str, packages=(), aliases=()) -> Unit:
    source = unit_id.split(":")[0]
    return Unit(
        unit_id, source, f"header {unit_id}", "body", frozenset(packages),
        frozenset({unit_id.split(":")[1].upper(), *aliases}),
    )  # fmt: skip


def corpus() -> list[Unit]:
    return [
        unit("ghsa:GHSA-aaaa-1", ["django"], ["CVE-2026-1"]),
        unit("ghsa:GHSA-aaaa-2", ["django"], ["CVE-2026-1", "CVE-2026-2"]),
        unit("ghsa:GHSA-bbbb-1", ["axios"]),
        unit("nvd:CVE-2026-1", ["django"]),
        unit("nvd:CVE-2026-2", ["django"]),
        unit("kev:CVE-2026-1", ["django"]),
    ]


def test_an_advisory_is_followed_by_its_nvd_record_then_its_kev_entry():
    links = candidates.Links(corpus())

    assert links.of("ghsa:GHSA-aaaa-2") == ["nvd:CVE-2026-1", "nvd:CVE-2026-2", "kev:CVE-2026-1"]


def test_an_nvd_record_links_to_its_advisories_and_a_kev_entry_to_the_nvd_record_first():
    links = candidates.Links(corpus())

    assert links.of("nvd:CVE-2026-1") == ["ghsa:GHSA-aaaa-1", "ghsa:GHSA-aaaa-2"]
    assert links.of("kev:CVE-2026-1") == ["nvd:CVE-2026-1", "ghsa:GHSA-aaaa-1", "ghsa:GHSA-aaaa-2"]


def test_a_link_to_a_unit_that_does_not_exist_is_left_out():
    links = candidates.Links(corpus())

    assert links.of("ghsa:GHSA-bbbb-1") == []


def test_r9_walks_the_ranking_and_stops_at_the_limit():
    links = candidates.Links(corpus())
    ranked = ["ghsa:GHSA-bbbb-1", "ghsa:GHSA-aaaa-1", "nvd:CVE-2026-2"]

    assert candidates.r9(ranked, links, 4) == [
        "ghsa:GHSA-bbbb-1", "ghsa:GHSA-aaaa-1", "nvd:CVE-2026-1", "kev:CVE-2026-1",
    ]  # fmt: skip


def test_r9_never_repeats_a_unit_and_keeps_r1s_order_for_what_r1_found():
    links = candidates.Links(corpus())
    ranked = ["nvd:CVE-2026-1", "ghsa:GHSA-aaaa-1"]

    out = candidates.r9(ranked, links, 10)

    assert out[0] == "nvd:CVE-2026-1"
    assert len(out) == len(set(out))


def test_r9_with_no_links_is_r1():
    links = candidates.Links(corpus())
    ranked = ["ghsa:GHSA-bbbb-1"]

    assert candidates.r9(ranked, links, 10) == ranked


def test_a_question_naming_one_package_is_scoped_and_two_or_none_are_not():
    assert candidates.names_one_package("Is django 4.2 affected?", PACKAGES) == "django"
    assert candidates.names_one_package("django or axios?", PACKAGES) is None
    assert candidates.names_one_package("Is anything affected?", PACKAGES) is None


def test_package_matching_is_whole_word_and_does_not_read_log4j_core_wording():
    assert candidates.names_one_package("Which log4j-core advisories?", PACKAGES) == PACKAGES[1]
    assert candidates.names_one_package("Which Log4j Core advisories?", PACKAGES) is None
    assert candidates.names_one_package("djangorestframework issues", PACKAGES) is None


def test_r10_lists_the_packages_records_in_r1_order_then_by_id_and_cuts_at_the_cap():
    units = corpus()
    ranked = ["nvd:CVE-2026-2", "ghsa:GHSA-bbbb-1", "ghsa:GHSA-aaaa-2"]

    out, scoped = candidates.r10(ranked, units, "What affects django?", PACKAGES, cap=4)

    assert scoped
    assert out == ["nvd:CVE-2026-2", "ghsa:GHSA-aaaa-2", "ghsa:GHSA-aaaa-1", "kev:CVE-2026-1"]


def test_r10_leaves_an_unscoped_question_at_r1s_top_ten():
    ranked = [f"ghsa:X{i}" for i in range(30)]

    out, scoped = candidates.r10(ranked, corpus(), "Anything at all?", PACKAGES)

    assert not scoped
    assert out == ranked[:10]
