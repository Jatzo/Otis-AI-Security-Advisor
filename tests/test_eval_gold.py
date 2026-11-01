"""The independent gold script, run against small synthetic records. No network."""

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path("eval/make_gold.py")
spec = importlib.util.spec_from_file_location("make_gold", SCRIPT)
gold = importlib.util.module_from_spec(spec)
sys.modules["make_gold"] = gold  # dataclasses look their own module up by name
spec.loader.exec_module(gold)


def rest_record(ghsa_id, ecosystem="pip", name="Pillow", range_text="< 2.0", **extra):
    return {
        "ghsa_id": ghsa_id,
        "cve_id": extra.pop("cve_id", None),
        "published_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "withdrawn_at": extra.pop("withdrawn_at", None),
        "summary": "A flaw",
        "severity": "high",
        "cvss_severities": extra.pop(
            "cvss_severities",
            {
                "cvss_v3": {
                    "vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                    "score": 9.8,
                }
            },
        ),
        "vulnerabilities": extra.pop(
            "vulnerabilities",
            [
                {
                    "package": {"ecosystem": ecosystem, "name": name},
                    "vulnerable_version_range": range_text,
                    "first_patched_version": "2.0",
                }
            ],
        ),
        **extra,
    }


def test_the_gold_script_imports_nothing_from_the_system_under_test():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])

    assert "advisor" not in imported


def test_its_package_list_is_the_systems_package_list():
    # Repeated in the script on purpose; this test is the only place the two meet.
    from advisor.packages import PACKAGES

    assert gold.PACKAGES == tuple((p.ecosystem, p.name) for p in PACKAGES)


def test_the_next_page_link_is_read_from_the_header():
    header = '<https://api.github.com/advisories?after=abc>; rel="next", <https://x>; rel="last"'

    assert gold.next_page(header) == "https://api.github.com/advisories?after=abc"
    assert gold.next_page('<https://x>; rel="last"') is None


GHSA_A = "GHSA-2222-3333-4444"
GHSA_B = "GHSA-5555-6666-7777"


def fake_get(pages):
    asked = []

    def get(url):
        asked.append(url)
        return pages[len(asked) - 1] if len(asked) <= len(pages) else ([], None)

    get.asked = asked
    return get


def test_fetching_follows_every_page_and_keeps_one_copy_of_an_advisory(tmp_path):
    first = ([rest_record(GHSA_A)], "https://next")
    second = ([rest_record(GHSA_A), rest_record(GHSA_B)], None)  # A is listed under two packages

    counts = gold.fetch_all(tmp_path, fake_get([first, second]))

    assert sorted(p.stem for p in tmp_path.glob("*.json")) == [GHSA_A, GHSA_B]
    assert counts["django"] == 3
    text = (tmp_path / f"{GHSA_A}.json").read_bytes()
    assert text.endswith(b"\n") and b"\r" not in text


def test_an_unexpected_advisory_id_changes_nothing_on_disk(tmp_path):
    (tmp_path / f"{GHSA_A}.json").write_text("{}")
    pages = [([rest_record("GHSA-../../escape")], None)]

    with pytest.raises(ValueError, match="unexpected advisory IDs"):
        gold.fetch_all(tmp_path, fake_get(pages))

    assert [p.name for p in tmp_path.iterdir()] == [f"{GHSA_A}.json"]


def test_rest_ecosystem_and_package_names_are_put_in_osv_form():
    advisory = gold.parse_advisory(rest_record(GHSA_A, ecosystem="pip", name="Pillow"))

    assert (advisory.ranges[0].ecosystem, advisory.ranges[0].package) == ("PyPI", "pillow")


def test_a_null_v3_vector_means_no_v3_score_whatever_the_score_field_says():
    record = rest_record(GHSA_A, cvss_severities={"cvss_v3": {"vector_string": None, "score": 0.0}})

    assert gold.parse_advisory(record).v3_score is None


def test_a_withdrawn_advisory_is_marked_withdrawn():
    assert gold.parse_advisory(
        rest_record(GHSA_A, withdrawn_at="2026-02-01T00:00:00Z")
    ).withdrawn_at


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (">= 1.0, < 2.0", [(">=", "1.0"), ("<", "2.0")]),
        ("<= 3", [("<=", "3")]),
        ("= 4.1", [("=", "4.1")]),
    ],
)
def test_github_range_text_is_split_into_bounds(text, expected):
    assert gold.parse_range(text) == expected


def test_a_range_shape_nobody_planned_for_is_refused():
    with pytest.raises(ValueError, match="Unexpected version range"):
        gold.parse_range("~> 1.2")


@pytest.mark.parametrize(
    ("ecosystem", "range_text", "version", "expected"),
    [
        ("PyPI", ">= 2.0, < 2.25.0", "2.0", True),
        ("PyPI", ">= 2.0, < 2.25.0", "2.24.9", True),
        ("PyPI", ">= 2.0, < 2.25.0", "2.25", False),  # 2.25 is 2.25.0
        ("PyPI", ">= 2.0, < 2.25.0", "1.9", False),
        ("PyPI", "= 1.2.3", "1.2.3", True),
        # pip refuses to match a pre-release of the bound; a vulnerability range does not.
        ("PyPI", "< 3.10.11", "3.10.11rc0", True),
        ("npm", "<= 8.5.1", "8.5.1", True),
        ("npm", "<= 8.5.1", "8.5.2", False),
        ("npm", ">= 1.0.0, < 2.0.0-beta.1", "2.0.0-alpha", True),
    ],
)
def test_a_version_is_affected_only_inside_the_range_text(ecosystem, range_text, version, expected):
    assert gold.affected(ecosystem, range_text, version) is expected


def test_a_maven_comparison_function_can_be_passed_in():
    def by_length(left, right):  # a stand-in order, to show the function is what decides
        return (len(left) > len(right)) - (len(left) < len(right))

    assert gold.affected("Maven", "< 1.0.0", "9.9", maven_compare=by_length) is True


def test_an_ecosystem_with_no_rules_is_refused():
    with pytest.raises(ValueError, match="No version rules"):
        gold.affected("RubyGems", "< 1.0", "0.5")


class FakeRun:
    def __init__(self, stdout):
        self.stdout, self.calls = stdout, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return type("Done", (), {"stdout": self.stdout})()


MAVEN_OUTPUT = "\n".join(
    [
        "1. 5.2.20.RELEASE -> 5.2.20; tokens: [5, 2, 20]",
        "   5.2.20.RELEASE == 5.2.20",
        "2. 5.2.20 -> 5.2.20",
    ]
)


def test_the_maven_jar_comparison_is_read_from_its_output_and_asked_only_once():
    run = FakeRun(MAVEN_OUTPUT)
    jar = gold.MavenJar(Path("jar"), run)

    assert jar.compare("5.2.20.RELEASE", "5.2.20") == 0
    assert jar.compare("5.2.20.RELEASE", "5.2.20") == 0
    assert run.calls == 1


def test_a_jar_that_prints_no_comparison_is_an_error_not_a_zero():
    with pytest.raises(RuntimeError, match="no comparison"):
        gold.MavenJar(Path("jar"), FakeRun("nothing useful\n")).compare("1", "2")


def osv_record(ecosystem, name, versions):
    return {"affected": [{"package": {"ecosystem": ecosystem, "name": name}, "versions": versions}]}


def test_two_ranges_for_one_package_are_read_as_one_affected_set():
    # Regression: each range was once compared with the whole listed set on its own, so a
    # version in the second range looked like a disagreement.
    two_ranges = rest_record(
        GHSA_A,
        vulnerabilities=[
            {
                "package": {"ecosystem": "pip", "name": "Pillow"},
                "vulnerable_version_range": "< 1.5",
            },
            {
                "package": {"ecosystem": "pip", "name": "Pillow"},
                "vulnerable_version_range": ">= 2.0, < 2.5",
            },
        ],
    )
    osv = {GHSA_A: osv_record("PyPI", "pillow", ["1.0", "2.0", "2.4", "3.0"])}

    result = gold.route_agreement([gold.parse_advisory(two_ranges)], osv)

    assert result == {
        "PyPI agree": 3,
        "PyPI differ": 1,
    }  # 3.0 is in the list but out of both ranges


def test_a_version_the_range_covers_but_osv_does_not_list_is_a_difference():
    one = gold.parse_advisory(rest_record(GHSA_A, range_text="< 5"))
    other = gold.parse_advisory(rest_record(GHSA_B, range_text="< 1"))
    osv = {
        GHSA_A: osv_record("PyPI", "pillow", ["1", "2"]),
        GHSA_B: osv_record("PyPI", "pillow", ["0"]),
    }

    result = gold.route_agreement([one, other], osv)

    # Versions known for the package: 0, 1, 2. A's range covers 0 but A does not list it.
    assert result == {"PyPI agree": 5, "PyPI differ": 1}


def test_withdrawn_advisories_and_npm_without_a_version_list_are_not_counted():
    withdrawn = gold.parse_advisory(rest_record(GHSA_A, withdrawn_at="2026-02-01T00:00:00Z"))
    npm = gold.parse_advisory(rest_record(GHSA_B, ecosystem="npm", name="lodash"))
    osv = {GHSA_A: osv_record("PyPI", "pillow", ["1"]), GHSA_B: osv_record("npm", "lodash", None)}

    assert gold.route_agreement([withdrawn, npm], osv) == {}


def test_nvd_score_is_the_primary_one_as_published():
    record = {
        "metrics": {
            "cvssMetricV31": [
                {"type": "Secondary", "cvssData": {"baseScore": 9.8, "vectorString": "CVSS:3.1/A"}},
                {"type": "Primary", "cvssData": {"baseScore": 7.5, "vectorString": "CVSS:3.1/B"}},
            ]
        }
    }

    assert gold.nvd_primary_v3(record) == (7.5, "CVSS:3.1/B")
    assert gold.nvd_primary_v3({"id": "CVE-2099-1", "notInNvd": True}) is None


def test_nvd_end_excluding_versions_come_only_from_vulnerable_matches():
    record = {
        "configurations": [
            {
                "nodes": [
                    {
                        "cpeMatch": [
                            {"vulnerable": True, "versionEndExcluding": "2.0"},
                            {"vulnerable": False, "versionEndExcluding": "9.9"},
                            {"vulnerable": True},
                        ]
                    }
                ]
            }
        ]
    }

    assert gold.nvd_end_excluding(record) == {"2.0"}


def test_kev_ids_are_read_from_the_raw_catalogue():
    catalogue = {"vulnerabilities": [{"cveID": "CVE-2021-44228"}, {"cveID": "CVE-2022-22965"}]}

    assert gold.kev_cve_ids(catalogue) == {"CVE-2021-44228", "CVE-2022-22965"}
    json.dumps(sorted(gold.kev_cve_ids(catalogue)))
