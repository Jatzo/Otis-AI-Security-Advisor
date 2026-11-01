"""The independent gold for the evaluation: facts read from GitHub's REST API, raw NVD files
and the raw KEV catalogue, by code that shares nothing with the system under test.

This script must not import the advisor package, its store, its fetchers or its version
comparators. A test reads this file and fails if it does. The package list is repeated
below for the same reason.

What is and is not independent (see eval/rules.md, section 1): the code and the formats
are separate. The facts are not, because GitHub's REST API and OSV.dev serve the same
advisory database.

Usage: python eval/make_gold.py fetch | routes
"""

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import semver
from packaging.version import Version
from univers.versions import MavenVersion

REST_URL = "https://api.github.com/advisories"
ECOSYSTEM_PARAMETER = {"PyPI": "pip", "npm": "npm", "Maven": "maven"}
# GitHub's REST API names ecosystems in lower case ("pip", "maven"). The rest of this file
# and OSV say PyPI and Maven.
REST_ECOSYSTEM = {"pip": "PyPI", "npm": "npm", "maven": "Maven"}
# Repeated from the advisor package on purpose: importing it would end the independence.
PACKAGES = (
    ("PyPI", "django"),
    ("PyPI", "flask"),
    ("PyPI", "jinja2"),
    ("PyPI", "requests"),
    ("PyPI", "urllib3"),
    ("PyPI", "pillow"),
    ("PyPI", "pyyaml"),
    ("PyPI", "cryptography"),
    ("PyPI", "aiohttp"),
    ("npm", "lodash"),
    ("npm", "express"),
    ("npm", "axios"),
    ("npm", "jsonwebtoken"),
    ("npm", "ws"),
    ("npm", "minimist"),
    ("Maven", "org.apache.logging.log4j:log4j-core"),
    ("Maven", "org.springframework:spring-webmvc"),
    ("Maven", "org.apache.struts:struts2-core"),
)
GHSA_ID = re.compile(r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}")
ROOT = Path(__file__).resolve().parent.parent
REST_CACHE = ROOT / "data" / "rest_cache"  # full fetch, not committed
MAVEN_JAR = ROOT / "data" / "tools" / "maven-artifact-3.9.9" / "maven-artifact-3.9.9.jar"

Get = Callable[[str], tuple[list[dict], str | None]]


# --- fetching GitHub's REST advisories -------------------------------------------------


def next_page(link_header: str) -> str | None:
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    return match.group(1) if match else None


def http_get(url: str) -> tuple[list[dict], str | None]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "otis-eval-gold",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return json.load(response), next_page(response.headers.get("Link", ""))
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise RuntimeError(
                "GitHub refused the request, probably the rate limit (60 an hour without a"
                " token). Set GITHUB_TOKEN and run it again."
            ) from error
        raise


def fetch_package(ecosystem: str, name: str, get: Get) -> list[dict]:
    query = urllib.parse.urlencode(
        {"ecosystem": ECOSYSTEM_PARAMETER[ecosystem], "affects": name, "per_page": 100}
    )
    records: list[dict] = []
    url: str | None = f"{REST_URL}?{query}"
    while url:
        page, url = get(url)
        records += page
    return records


def write_json(path: Path, value: object) -> None:
    text = json.dumps(value, sort_keys=True, indent=1) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def fetch_all(cache_dir: Path, get: Get = http_get) -> dict[str, int]:
    """Fetch every package, check every ID, and only then replace the cache, so a failure
    part-way leaves the previous cache whole. Returns the advisories per package."""
    per_package: dict[str, int] = {}
    by_id: dict[str, dict] = {}
    for ecosystem, name in PACKAGES:
        records = fetch_package(ecosystem, name, get)
        per_package[name] = len(records)
        by_id.update({r["ghsa_id"]: r for r in records})
    bad = [i for i in by_id if not GHSA_ID.fullmatch(i)]
    if bad:
        raise ValueError(f"GitHub returned unexpected advisory IDs: {bad[:5]}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for old in cache_dir.glob("*.json"):
        old.unlink()
    for ghsa_id, record in by_id.items():
        write_json(cache_dir / f"{ghsa_id}.json", record)
    return per_package


def read_cache(cache_dir: Path) -> dict[str, dict]:
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(cache_dir.glob("*.json"))
    }


# --- reading an advisory -------------------------------------------------------------------


@dataclass(frozen=True)
class RangeEntry:
    ecosystem: str
    package: str
    range_text: str
    first_patched: str | None


@dataclass(frozen=True)
class Advisory:
    ghsa_id: str
    cve_id: str | None
    published: str
    updated: str
    withdrawn_at: str | None
    summary: str
    label: str | None
    v3_score: float | None  # GitHub's own CVSS v3 score; never v4
    v3_vector: str | None
    nvd_published_at: str | None
    ranges: tuple[RangeEntry, ...]


def canonical_package(ecosystem: str, name: str) -> str:
    """PyPI names are case and separator blind (PEP 503); REST says 'Pillow', OSV says 'pillow'."""
    return re.sub(r"[-_.]+", "-", name).lower() if ecosystem == "PyPI" else name


def parse_advisory(record: dict) -> Advisory:
    v3 = (record.get("cvss_severities") or {}).get("cvss_v3") or {}
    has_v3 = bool(v3.get("vector_string"))  # a null vector comes with a score of 0.0
    ranges = tuple(
        RangeEntry(
            REST_ECOSYSTEM.get(v["package"]["ecosystem"], v["package"]["ecosystem"]),
            canonical_package(
                REST_ECOSYSTEM.get(v["package"]["ecosystem"], v["package"]["ecosystem"]),
                v["package"]["name"],
            ),
            v.get("vulnerable_version_range") or "",
            v.get("first_patched_version"),
        )
        for v in record.get("vulnerabilities") or []
    )
    return Advisory(
        record["ghsa_id"],
        record.get("cve_id"),
        record["published_at"],
        record["updated_at"],
        record.get("withdrawn_at"),
        record.get("summary") or "",
        record.get("severity"),
        v3["score"] if has_v3 else None,
        v3["vector_string"] if has_v3 else None,
        record.get("nvd_published_at"),
        ranges,
    )


# --- is a version affected? -----------------------------------------------------------------

_COMPARATOR = re.compile(r"(>=|<=|>|<|=)\s*(\S+)")


def parse_range(range_text: str) -> list[tuple[str, str]]:
    """GitHub writes ranges as comma-separated bounds: '>= 1.0, < 2.0', '<= 3', '= 4.1'."""
    bounds = []
    for piece in range_text.split(","):
        match = _COMPARATOR.fullmatch(piece.strip())
        if not match:
            raise ValueError(f"Unexpected version range: {range_text!r}")
        bounds.append((match.group(1), match.group(2)))
    return bounds


def holds(operator: str, order: int) -> bool:
    """Whether 'version OPERATOR bound' is true, given the sign of version minus bound."""
    return {">=": order >= 0, "<=": order <= 0, ">": order > 0, "<": order < 0, "=": order == 0}[
        operator
    ]


def sign(left, right) -> int:
    return (left > right) - (left < right)


@cache
def univers_maven(version: str) -> MavenVersion:
    return MavenVersion(version)


def univers_maven_compare(left: str, right: str) -> int:
    return sign(univers_maven(left), univers_maven(right))


def affected(
    ecosystem: str,
    range_text: str,
    version: str,
    maven_compare: Callable[[str, str], int] = univers_maven_compare,
) -> bool:
    """Whether the version falls inside GitHub's range text, read with libraries that are
    not the ones the system uses: packaging's Version, python-semver, and for Maven a
    comparison function you pass in (univers by default, or the real Maven jar)."""
    bounds = parse_range(range_text)
    if ecosystem == "PyPI":
        # Plain version ordering, not packaging.specifiers: pip's rule that '< 3.10.11' must
        # not match 3.10.11rc0 is right for installing and wrong for "was it vulnerable".
        target = Version(version)
        return all(holds(op, sign(target, Version(v))) for op, v in bounds)
    if ecosystem == "npm":
        target = semver.Version.parse(version)
        return all(holds(op, target.compare(semver.Version.parse(v))) for op, v in bounds)
    if ecosystem == "Maven":
        return all(holds(op, maven_compare(version, v)) for op, v in bounds)
    raise ValueError(f"No version rules for ecosystem {ecosystem!r}")


class MavenJar:
    """Apache Maven 3.9.9's own ComparableVersion, run through its main method, as an outside
    check on the Maven cases. The jar's SHA-1 was checked against Maven Central's."""

    def __init__(self, jar: Path = MAVEN_JAR, run: Callable = subprocess.run) -> None:
        self.jar, self.run = jar, run
        self.seen: dict[tuple[str, str], int] = {}

    def compare(self, left: str, right: str) -> int:
        if (left, right) not in self.seen:
            done = self.run(
                [
                    "java",
                    "-cp",
                    str(self.jar),
                    "org.apache.maven.artifact.versioning.ComparableVersion",
                    left,
                    right,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=30,
            )
            match = re.search(r"^\s+\S+ (==|<|>) \S+$", done.stdout, re.MULTILINE)
            if not match:
                raise RuntimeError(f"Maven printed no comparison for {left!r} and {right!r}")
            self.seen[(left, right)] = {"==": 0, "<": -1, ">": 1}[match.group(1)]
        return self.seen[(left, right)]


# --- NVD and KEV, read from the raw files ---------------------------------------------------


def nvd_primary_v3(record: dict) -> tuple[float, str] | None:
    """NVD's own published v3 base score and vector. Never recomputed from the vector."""
    for key in ("cvssMetricV31", "cvssMetricV30"):
        for metric in (record.get("metrics") or {}).get(key, []):
            if metric.get("type") == "Primary":
                return metric["cvssData"]["baseScore"], metric["cvssData"]["vectorString"]
    return None


def nvd_end_excluding(record: dict) -> set[str]:
    ends = set()
    for configuration in record.get("configurations", []):
        for node in configuration.get("nodes", []):
            for match in node.get("cpeMatch", []):
                if match.get("vulnerable") and match.get("versionEndExcluding"):
                    ends.add(match["versionEndExcluding"])
    return ends


def kev_cve_ids(catalogue: dict) -> set[str]:
    return {entry["cveID"] for entry in catalogue["vulnerabilities"]}


# --- checking the routes against each other ------------------------------------------------


def osv_listed_versions(osv_record: dict, ecosystem: str, package: str) -> set[str] | None:
    """The versions OSV lists as affected for one package, taken from the registries.
    None when OSV gives no list, so no verdict can be made."""
    found: set[str] | None = None
    for entry in osv_record.get("affected", []):
        name = canonical_package(entry["package"]["ecosystem"], entry["package"]["name"])
        if (entry["package"]["ecosystem"], name) == (ecosystem, package):
            if entry.get("versions"):
                found = (found or set()) | set(entry["versions"])
    return found


def affected_by_any(
    entries: Iterable[RangeEntry], version: str, maven_compare: Callable[[str, str], int]
) -> bool:
    """An advisory can give one package several ranges; the version is affected if any holds."""
    return any(affected(e.ecosystem, e.range_text, version, maven_compare) for e in entries)


def route_agreement(
    advisories: Iterable[Advisory],
    osv_records: dict[str, dict],
    maven_compare: Callable[[str, str], int] = univers_maven_compare,
    jar_compare: Callable[[str, str], int] | None = None,
) -> Counter:
    """For each advisory and corpus package that OSV lists versions for: does the REST range
    agree with OSV's list on every version known for that package? Counts agreements and
    disagreements, and for Maven disagreements, which side the jar (if given) supports.
    OSV lists no versions for npm, so npm has no second route and is not counted."""
    advisories = [a for a in advisories if not a.withdrawn_at and a.ghsa_id in osv_records]
    per_package: list[tuple[Advisory, str, str, list[RangeEntry], set[str]]] = []
    universe: dict[tuple[str, str], set[str]] = {}
    for adv in advisories:
        for ecosystem, package in {(e.ecosystem, e.package) for e in adv.ranges}:
            listed = osv_listed_versions(osv_records[adv.ghsa_id], ecosystem, package)
            if listed:
                entries = [
                    e for e in adv.ranges if (e.ecosystem, e.package) == (ecosystem, package)
                ]
                per_package.append((adv, ecosystem, package, entries, listed))
                universe.setdefault((ecosystem, package), set()).update(listed)
    result: Counter = Counter()
    for _, ecosystem, package, entries, listed in per_package:
        for version in universe[(ecosystem, package)]:
            said = affected_by_any(entries, version, maven_compare)
            if said == (version in listed):
                result[f"{ecosystem} agree"] += 1
                continue
            result[f"{ecosystem} differ"] += 1
            if ecosystem == "Maven" and jar_compare:
                by_jar = affected_by_any(entries, version, jar_compare)
                side = "univers" if by_jar == said else "the OSV list"
                result[f"Maven differ, the Maven jar agrees with {side}"] += 1
    return result


def main() -> None:
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "fetch":
        print(json.dumps(fetch_all(REST_CACHE), indent=1))  # noqa: T201
    elif step == "routes":
        advisories = [parse_advisory(r) for r in read_cache(REST_CACHE).values()]
        osv_records = {
            p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in (ROOT / "data" / "raw" / "osv").glob("GHSA-*.json")
        }
        jar = MavenJar()
        report = route_agreement(advisories, osv_records, jar_compare=jar.compare)
        print(json.dumps(dict(sorted(report.items())), indent=1))  # noqa: T201
    else:
        sys.exit("Usage: python eval/make_gold.py fetch | routes")


if __name__ == "__main__":
    main()
