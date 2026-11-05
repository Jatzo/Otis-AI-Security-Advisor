"""Release lists: the versions each registry has published for the corpus packages.

The ingest check (src/advisor/integrity) asks whether a record's fixed version was ever released.
A registry's list grows over time, so a list fetched later is a different list. They are stored in
data/releases/, apart from the snapshot, with the date they were fetched and a hash of each file.
Tests read a small committed sample and never fetch.
"""

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from advisor.ingest.http import get_json
from advisor.packages import PACKAGES, Package

PYPI = "https://pypi.org/pypi/{name}/json"
NPM = "https://registry.npmjs.org/{name}"
NPM_HEADERS = {"Accept": "application/vnd.npm.install-v1+json"}  # the short form: versions only
MAVEN = "https://repo1.maven.org/maven2/{path}/{artifact}/maven-metadata.xml"
MAVEN_VERSION = re.compile(r"<version>([^<]+)</version>")
LF = "\n"


def url_for(package: Package) -> str:
    if package.ecosystem == "PyPI":
        return PYPI.format(name=package.name)
    if package.ecosystem == "npm":
        return NPM.format(name=package.name)
    group, artifact = package.name.split(":")
    return MAVEN.format(path=group.replace(".", "/"), artifact=artifact)


def versions_from(package: Package, payload: Any) -> list[str]:
    """The released versions in a registry's answer. PyPI keeps a version in `releases` after its
    files are deleted, so a version with no files is not counted as released."""
    if package.ecosystem == "PyPI":
        return sorted(version for version, files in payload["releases"].items() if files)
    if package.ecosystem == "npm":
        return sorted(payload["versions"])
    block = payload.split("<versions>", 1)[-1].split("</versions>", 1)[0]
    return sorted(MAVEN_VERSION.findall(block))


def file_for(directory: Path, package: Package) -> Path:
    return directory / package.ecosystem / (package.name.replace(":", "__") + ".json")


def fetch_one(package: Package, get: Callable[..., Any] = get_json) -> list[str]:
    if package.ecosystem == "npm":
        payload = get(url_for(package), headers=NPM_HEADERS)
    elif package.ecosystem == "Maven":
        payload = get(url_for(package), headers={"Accept": "application/xml"}, parse=_read_text)
    else:
        payload = get(url_for(package))
    return versions_from(package, payload)


def _read_text(response: Any) -> str:
    return response.read().decode("utf-8")


def fetch_all(
    directory: Path, get: Callable[..., Any] = get_json, today: date | None = None
) -> dict:
    """Fetches every corpus package's list and writes the files and a manifest."""
    fetched = (today or date.today()).isoformat()
    manifest: dict[str, Any] = {"fetched": fetched, "files": {}}
    for package in PACKAGES:
        versions = fetch_one(package, get)
        if not versions:
            raise RuntimeError(f"The registry listed no versions for {package.name}")
        path = file_for(directory, package)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(
            {
                "ecosystem": package.ecosystem,
                "package": package.name,
                "source": url_for(package),
                "fetched": fetched,
                "versions": versions,
            },
            indent=1,
        )
        path.write_text(text + LF, encoding="utf-8", newline=LF)
        manifest["files"][path.relative_to(directory).as_posix()] = {
            "sha256": hashlib.sha256((text + LF).encode()).hexdigest(),
            "versions": len(versions),
        }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + LF, encoding="utf-8", newline=LF
    )
    return manifest


def load(directory: Path) -> dict[tuple[str, str], list[str]]:
    """Every stored list, by (ecosystem, package). A package with no file is simply absent."""
    found = {}
    for package in PACKAGES:
        path = file_for(directory, package)
        if path.exists():
            found[(package.ecosystem, package.name)] = json.loads(path.read_text("utf-8"))[
                "versions"
            ]
    return found
