"""Version ordering for the corpus, so "is 2.25.0 affected?" has an exact answer.

Each ecosystem orders versions its own way, and a wrong order gives a wrong answer with
no error, so an unparseable version raises UnparseableVersion rather than being guessed at.

OSV says how a range is to be read: SEMVER ranges use SemVer 2.0 whatever the ecosystem,
and ECOSYSTEM ranges use the ecosystem's own order. The comparator is chosen from the
range type first, then the ecosystem.

PyPI is PEP 440, through the packaging library. SemVer is written here from the spec.
Maven is a port of ComparableVersion from Apache Maven 3.9.9, the release it was checked
against; Maven's own test vectors are in the tests.
"""

import re
from collections.abc import Callable, Sequence

from packaging.version import InvalidVersion, Version

# (introduced, fixed, last_affected), as store.spans produces them.
Span = tuple[str | None, str | None, str | None]


class UnparseableVersion(ValueError):
    """A version string the ecosystem's rules do not accept."""


def compare_pypi(left: str, right: str) -> int:
    try:
        a, b = Version(left), Version(right)
    except InvalidVersion as error:
        raise UnparseableVersion(str(error)) from error
    return (a > b) - (a < b)


_IDENTIFIER = r"(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
_SEMVER = re.compile(
    rf"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-({_IDENTIFIER}(?:\.{_IDENTIFIER})*))?"
    r"(?:\+[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)?",  # build metadata never affects order
    re.ASCII,  # the spec allows ASCII digits only
)


def semver_key(version: str) -> tuple:
    match = _SEMVER.fullmatch(version)
    if not match:
        raise UnparseableVersion(f"Not a SemVer 2.0 version: {version!r}")
    major, minor, patch, prerelease = match.groups()
    if prerelease is None:
        return int(major), int(minor), int(patch), 1, ()  # a release outranks its prereleases
    # Numeric identifiers sort below alphanumeric ones, and a longer list outranks its prefix.
    identifiers = tuple(
        (0, int(i), "") if i.isdigit() else (1, 0, i) for i in prerelease.split(".")
    )
    return int(major), int(minor), int(patch), 0, identifiers


def compare_semver(left: str, right: str) -> int:
    a, b = semver_key(left), semver_key(right)
    return (a > b) - (a < b)


_QUALIFIERS = ("alpha", "beta", "milestone", "rc", "snapshot", "", "sp")
_ALIASES = {"ga": "", "final": "", "release": "", "cr": "rc"}
_SHORT_QUALIFIERS = {"a": "alpha", "b": "beta", "m": "milestone"}  # only before a digit
_RELEASE_RANK = str(_QUALIFIERS.index(""))


class _Qualifier:
    """A word in a Maven version, such as "beta" or "sp"."""

    def __init__(self, word: str, followed_by_digit: bool) -> None:
        if followed_by_digit:
            word = _SHORT_QUALIFIERS.get(word, word)
        self.word = _ALIASES.get(word, word)

    def rank(self) -> str:
        # Known words sort by their place in the list; unknown words sort after all of
        # them, in alphabetical order. Maven compares these as text, so this does too.
        if self.word in _QUALIFIERS:
            return str(_QUALIFIERS.index(self.word))
        return f"{len(_QUALIFIERS)}-{self.word}"


def _is_empty(item: object) -> bool:
    if isinstance(item, int):
        return item == 0
    if isinstance(item, _Qualifier):
        return item.rank() == _RELEASE_RANK
    return not item  # a list


def _compare_items(left: object, right: object | None) -> int:
    """Maven's ordering of two items; right is None when one version has run out of items."""
    if isinstance(left, int):
        if right is None:
            return 0 if left == 0 else 1
        if isinstance(right, int):
            return (left > right) - (left < right)
        return 1  # 1.1 is above 1-sp and above 1-1
    if isinstance(left, _Qualifier):
        if right is None:
            return (left.rank() > _RELEASE_RANK) - (left.rank() < _RELEASE_RANK)
        if isinstance(right, _Qualifier):
            return (left.rank() > right.rank()) - (left.rank() < right.rank())
        return -1  # 1.any is below 1.1 and below 1-1
    if not isinstance(left, list):
        raise TypeError(f"Not a Maven version item: {left!r}")
    if right is None:
        for item in left:
            result = _compare_items(item, None)
            if result:
                return result
        return 0
    if isinstance(right, int):
        return -1
    if isinstance(right, _Qualifier):
        return 1
    if not isinstance(right, list):
        raise TypeError(f"Not a Maven version item: {right!r}")
    for index in range(max(len(left), len(right))):
        a = left[index] if index < len(left) else None
        b = right[index] if index < len(right) else None
        # The shorter side is compared the other way round, then flipped.
        result = -_compare_items(b, a) if a is None else _compare_items(a, b)
        if result:
            return result
    return 0


def _parse_item(is_digit: bool, text: str) -> int | _Qualifier:
    return int(text) if is_digit else _Qualifier(text, False)


MAX_MAVEN_VERSION_LENGTH = 128


def parse_maven(version: str) -> list:
    """Port of ComparableVersion.parseVersion (Maven 3.9.9)."""
    if not version.strip():
        raise UnparseableVersion("An empty Maven version")
    # Every hyphen nests a list and comparing recurses one level per list, so a long run
    # of hyphens would overflow the stack. Real versions are under 50 characters.
    if len(version) > MAX_MAVEN_VERSION_LENGTH:
        raise UnparseableVersion(f"A Maven version of {len(version)} characters")
    version = version.lower()
    root: list = []
    current = root
    stack = [root]
    is_digit = False
    start = 0
    for index, char in enumerate(version):
        if char in ".-":
            current.append(0 if index == start else _parse_item(is_digit, version[start:index]))
            start = index + 1
            if char == "-":
                current = _push_list(current, stack)
        elif char.isdecimal():  # Java's isDigit, which is the Unicode decimal digits
            if not is_digit and index > start:
                # 1.0.0.X1 is below 1.0.0-X2: any word before a digit opens a sub-list.
                if current:
                    current = _push_list(current, stack)
                current.append(_Qualifier(version[start:index], True))
                start = index
                current = _push_list(current, stack)
            is_digit = True
        else:
            if is_digit and index > start:
                current.append(_parse_item(True, version[start:index]))
                start = index
                current = _push_list(current, stack)
            is_digit = False
    if len(version) > start:
        if not is_digit and current:
            current = _push_list(current, stack)
        current.append(_parse_item(is_digit, version[start:]))
    for items in reversed(stack):
        _drop_trailing_empty(items)
    return root


def _push_list(current: list, stack: list[list]) -> list:
    child: list = []
    current.append(child)
    stack.append(child)
    return child


def _drop_trailing_empty(items: list) -> None:
    """Remove trailing 0, "" and empty lists, so 1, 1.0 and 1.0.0 are equal."""
    for index in range(len(items) - 1, -1, -1):
        if _is_empty(items[index]):
            del items[index]
        elif not isinstance(items[index], list):
            break


def compare_maven(left: str, right: str) -> int:
    return _compare_items(parse_maven(left), parse_maven(right))


_BY_ECOSYSTEM: dict[str, Callable[[str, str], int]] = {
    "PyPI": compare_pypi,
    "Maven": compare_maven,
}


def comparator(ecosystem: str, range_type: str) -> Callable[[str, str], int]:
    if range_type == "SEMVER":
        return compare_semver
    if range_type == "ECOSYSTEM" and ecosystem in _BY_ECOSYSTEM:
        return _BY_ECOSYSTEM[ecosystem]
    raise ValueError(f"No version order for {ecosystem} {range_type} ranges")


def is_affected(ecosystem: str, range_type: str, version: str, spans: Sequence[Span]) -> bool:
    """Whether the version falls in any span: from introduced, up to but not including
    fixed, or up to and including last_affected. An introduced of "0" or none means from
    the very first version, and a span with neither end is open: every later version."""
    compare = comparator(ecosystem, range_type)
    for introduced, fixed, last_affected in spans:
        if introduced not in (None, "0") and compare(version, introduced) < 0:
            continue
        if fixed is not None and compare(version, fixed) >= 0:
            continue
        if last_affected is not None and compare(version, last_affected) > 0:
            continue
        return True
    return False
