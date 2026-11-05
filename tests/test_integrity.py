"""The ingest check: what the two signals say, and what holding a record back does to the store.
No test fetches anything. The release lists are small made-up ones."""

import pytest
from generation_world import DB, A, B, C, D

from advisor.integrity import check, plausible

DB.commit()  # the shared test store has an open write transaction, which blocks a backup

DJANGO = ["1.1.3", "3.0", "3.0.4", "3.0.5", "3.1a1", "3.1"]


@pytest.mark.parametrize(
    ("ecosystem", "range_type", "fixed", "released", "expected"),
    [
        ("PyPI", "ECOSYSTEM", "3.0.5", DJANGO, check.LISTED),
        ("PyPI", "ECOSYSTEM", "3.0.6", DJANGO, check.NOT_LISTED),
        ("PyPI", "ECOSYSTEM", "99.99.99", DJANGO, check.NOT_LISTED),
        ("PyPI", "ECOSYSTEM", None, DJANGO, check.CANNOT_CHECK),
        ("PyPI", "ECOSYSTEM", "0", DJANGO, check.CANNOT_CHECK),
        ("Maven", "ECOSYSTEM", "RELEASE", ["2.0"], check.CANNOT_CHECK),
        ("PyPI", "ECOSYSTEM", "3.0.5", None, check.CANNOT_CHECK),
        ("npm", "ECOSYSTEM", "1.0.0", ["1.0.0"], check.CANNOT_CHECK),  # no version order exists
        ("npm", "SEMVER", "1.4.0", ["1.3.0", "1.4.0"], check.LISTED),
    ],
)
def test_the_release_list_signal_judges_a_fixed_version_or_says_it_cannot(
    ecosystem, range_type, fixed, released, expected
):
    assert check.release_status(ecosystem, range_type, fixed, released) == expected


def test_the_refined_rule_leaves_pre_releases_and_versions_older_than_the_list_unjudged():
    args = ("PyPI", "ECOSYSTEM")
    assert check.release_status(*args, "1.7b4", DJANGO) == check.NOT_LISTED
    assert check.release_status(*args, "1.7b4", DJANGO, refined=True) == check.CANNOT_CHECK
    assert check.release_status(*args, "0.96.1", DJANGO) == check.NOT_LISTED
    assert check.release_status(*args, "0.96.1", DJANGO, refined=True) == check.CANNOT_CHECK
    # A version above the oldest listed one is still judged under the refined rule.
    assert check.release_status(*args, "3.0.6", DJANGO, refined=True) == check.NOT_LISTED
    assert check.release_status(*args, "3.0.5", DJANGO, refined=True) == check.LISTED


def test_a_fixed_version_the_ecosystems_order_cannot_read_is_unjudged_and_does_not_crash():
    """npm uses SemVer, which needs three numbers. A record that says 99.99 is not a version to
    judge, and it must not stop the check for every other record."""
    for refined in (False, True):
        status = check.release_status("npm", "SEMVER", "99.99", ["1.0.0", "1.4.0"], refined=refined)
        assert status in (check.CANNOT_CHECK, check.NOT_LISTED)
    assert (
        check.release_status("npm", "SEMVER", "99.99", ["1.4.0"], refined=True)
        == check.CANNOT_CHECK
    )


@pytest.mark.parametrize(
    ("ours", "theirs", "expected"),
    [
        ({"3.0.5"}, {"3.0.5"}, check.AGREES),
        ({"3.0.5", "2.2.10"}, {"3.0.5"}, check.AGREES),  # one version in common is enough
        ({"3.0.5"}, {"3.0.6"}, check.DISAGREES),
        ({"3.0.5"}, set(), check.CANNOT_CHECK),
        (set(), {"3.0.5"}, check.CANNOT_CHECK),
    ],
)
def test_the_second_source_signal_asks_for_one_version_in_common(ours, theirs, expected):
    assert check.second_source_status("PyPI", "ECOSYSTEM", ours, theirs) == expected


def test_each_record_gets_both_verdicts_from_the_store_and_the_lists():
    lists = {
        ("PyPI", "django"): DJANGO,
        ("npm", "axios"): ["1.3.0"],  # the record's 1.4.0 is not here
        ("PyPI", "pillow"): ["9.0"],
        # no list for spring-webmvc
    }
    verdicts = check.check_records(DB, lists)
    assert (verdicts[A].release, verdicts[A].second_source) == (check.LISTED, check.AGREES)
    assert (verdicts[B].release, verdicts[B].second_source) == (
        check.NOT_LISTED,
        check.CANNOT_CHECK,
    )
    assert verdicts[C].release == check.CANNOT_CHECK
    assert verdicts[D].release == check.LISTED
    assert check.held_back(verdicts) == {B}  # only the release list holds a record back


def test_check_records_can_be_limited_to_named_records():
    assert set(check.check_records(DB, {}, only={A, B})) == {A, B}


def test_holding_a_record_back_removes_it_from_a_copy_and_not_from_the_store():
    before = DB.execute("SELECT COUNT(*) FROM records WHERE source = 'ghsa'").fetchone()[0]
    copy = check.without(DB, {B})
    assert copy.execute("SELECT COUNT(*) FROM records WHERE record_id = ?", (B,)).fetchone()[0] == 0
    assert (
        copy.execute("SELECT COUNT(*) FROM affected WHERE record_id = ?", (B,)).fetchone()[0] == 0
    )
    assert DB.execute("SELECT COUNT(*) FROM records WHERE source = 'ghsa'").fetchone()[0] == before


# --- the two lies built by a rule ---------------------------------------------------------------


def test_not_yet_released_is_the_next_patch_above_the_latest_stable_release():
    released = ["3.0.4", "3.0.5", "3.1a1"]  # the a1 is not stable, so it is ignored
    assert plausible.not_yet_released("PyPI", "ECOSYSTEM", released) == "3.0.6"
    assert plausible.not_yet_released("PyPI", "ECOSYSTEM", [*released, "3.0.6"]) == "3.0.7"
    assert plausible.not_yet_released("PyPI", "ECOSYSTEM", ["1.0rc1"]) is None


def test_released_but_wrong_is_the_nearest_stable_release_below_the_real_fix():
    released = ["2.2.1", "3.0", "3.0.4", "3.0.5rc1", "3.0.5", "3.1"]
    wrong = plausible.released_but_wrong("PyPI", "ECOSYSTEM", released, "3.0.5")
    assert wrong == "3.0.4"
    assert plausible.released_but_wrong("PyPI", "ECOSYSTEM", ["3.0.5"], "3.0.5") is None
