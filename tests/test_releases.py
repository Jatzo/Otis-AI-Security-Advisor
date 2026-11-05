"""Release lists: how each registry's answer is read, and what is written. Nothing is fetched."""

import io
from datetime import date

from advisor.ingest import http, releases
from advisor.packages import PACKAGES, Package

PYPI_ANSWER = {"releases": {"1.0": [{"filename": "a.whl"}], "1.1": [], "2.0": [{"filename": "b"}]}}
NPM_ANSWER = {"name": "axios", "versions": {"1.4.0": {}, "0.9.1": {}}}
MAVEN_ANSWER = (
    "<metadata><versioning><latest>2.1</latest><versions>"
    "<version>2.0</version><version>2.1</version></versions></versioning></metadata>"
)


def test_a_pypi_version_with_no_files_left_is_not_counted_as_released():
    package = Package("PyPI", "django")
    assert releases.versions_from(package, PYPI_ANSWER) == ["1.0", "2.0"]


def test_the_npm_and_maven_answers_are_read_into_sorted_lists():
    assert releases.versions_from(Package("npm", "axios"), NPM_ANSWER) == ["0.9.1", "1.4.0"]
    maven = Package("Maven", "org.example:thing")
    assert releases.versions_from(maven, MAVEN_ANSWER) == ["2.0", "2.1"]


def test_a_maven_package_is_looked_up_by_its_group_path_and_artifact():
    url = releases.url_for(Package("Maven", "org.apache.logging.log4j:log4j-core"))
    assert url.endswith("/org/apache/logging/log4j/log4j-core/maven-metadata.xml")


def fake_get(url, **kwargs):
    if "pypi.org" in url:
        return PYPI_ANSWER
    if "registry.npmjs.org" in url:
        assert kwargs["headers"] == releases.NPM_HEADERS  # the short form, versions only
        return NPM_ANSWER
    assert kwargs["parse"] is releases._read_text
    return MAVEN_ANSWER


def test_every_corpus_package_is_written_with_the_date_and_a_hash_and_read_back(tmp_path):
    manifest = releases.fetch_all(tmp_path, fake_get, today=date(2026, 11, 5))
    assert manifest["fetched"] == "2026-11-05"
    assert len(manifest["files"]) == len(PACKAGES) == 18
    stored = releases.load(tmp_path)
    assert stored[("PyPI", "django")] == ["1.0", "2.0"]
    assert stored[("Maven", "org.apache.struts:struts2-core")] == ["2.0", "2.1"]
    assert all(entry["sha256"] and entry["versions"] == 2 for entry in manifest["files"].values())


def test_get_json_can_return_the_text_of_an_answer_that_is_not_json(monkeypatch):
    def urlopen(request, timeout):
        return io.BytesIO(MAVEN_ANSWER.encode())

    monkeypatch.setattr(http.urllib.request, "urlopen", urlopen)
    assert http.get_json("https://example.invalid", parse=releases._read_text) == MAVEN_ANSWER
