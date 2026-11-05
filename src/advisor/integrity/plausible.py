"""Two kinds of lie about a fixed version, built by a rule, to test the ingest check.

The red team's B2 records use 99.99.99 and 88.88.88, which no registry lists, so a release list
catches them by construction. These two are fairer:

not yet released: the next patch above the latest stable release. A release list should catch it.
released but wrong: the nearest stable release below the real fix. It claims an earlier fix, so the
    versions between look safe. A release list cannot catch it, because the version is real.

A stable version here is digits and dots only. Anything with a letter (a1, rc1, alpha, RELEASE) is
left out of both rules.
"""

from functools import cmp_to_key

from advisor import versions
from advisor.integrity.check import STABLE


def stable(released: list[str]) -> list[str]:
    return [version for version in released if STABLE.fullmatch(version)]


def latest_stable(ecosystem: str, range_type: str, released: list[str]) -> str | None:
    compare = versions.comparator(ecosystem, range_type)
    candidates = stable(released)
    return max(candidates, key=cmp_to_key(compare)) if candidates else None


def not_yet_released(ecosystem: str, range_type: str, released: list[str]) -> str | None:
    """The latest stable release with its last number raised by one. By construction it is not
    listed, because the list has nothing newer than its latest stable release."""
    latest = latest_stable(ecosystem, range_type, released)
    if latest is None:
        return None
    *head, last = latest.split(".")
    candidate = ".".join([*head, str(int(last) + 1)])
    return candidate


def released_but_wrong(
    ecosystem: str, range_type: str, released: list[str], real_fix: str
) -> str | None:
    """The nearest stable release strictly below the real fix, or None if there is none."""
    compare = versions.comparator(ecosystem, range_type)
    below = [v for v in stable(released) if compare(v, real_fix) < 0]
    return max(below, key=cmp_to_key(compare)) if below else None
