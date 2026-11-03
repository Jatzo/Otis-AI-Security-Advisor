"""The secret-scan self-test must pass when the scanner finds the planted key and fail when it
does not. A stand-in `gitleaks` on PATH plays each part, so these run without the real tool."""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_secret_scan.sh"
BASH = shutil.which("bash")

# Exits 99 (the script's leak-found code) only if the folder holds a token-shaped string.
SCANNER_THAT_FINDS_IT = '#!/bin/sh\ngrep -rqE "ghp_[A-Za-z0-9]{36}" "$2" && exit 99 || exit 0\n'
SCANNER_THAT_MISSES_IT = "#!/bin/sh\nexit 0\n"
# Fails the way a renamed subcommand or bad flag would: exit 1, which real gitleaks
# also uses for "leak found" unless told otherwise.
SCANNER_THAT_CRASHES = '#!/bin/sh\necho "unknown command" >&2\nexit 1\n'

pytestmark = pytest.mark.skipif(BASH is None, reason="bash is needed to run the script")


def run_with_stand_in_scanner(tmp_path: Path, stand_in: str) -> subprocess.CompletedProcess:
    stub = tmp_path / "gitleaks"
    stub.write_text(stand_in, newline="\n")
    stub.chmod(0o755)
    # Let bash prepend the stub folder in its own path format, which differs on Windows.
    stub_dir = subprocess.run(  # noqa: S603
        [BASH, "-c", 'cd "$1" && pwd', "_", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'PATH="{stub_dir}:$PATH" bash "$0"', SCRIPT.as_posix()],
        capture_output=True,
        text=True,
    )


def test_the_self_test_passes_when_the_scanner_reports_the_planted_key(tmp_path):
    result = run_with_stand_in_scanner(tmp_path, SCANNER_THAT_FINDS_IT)
    assert result.returncode == 0, result.stderr
    assert "caught the planted token" in result.stdout


def test_the_self_test_fails_when_the_scanner_misses_the_planted_key(tmp_path):
    result = run_with_stand_in_scanner(tmp_path, SCANNER_THAT_MISSES_IT)
    assert result.returncode == 1
    assert "cannot be trusted" in result.stderr


def test_the_self_test_fails_when_the_scanner_crashes_instead_of_scanning(tmp_path):
    result = run_with_stand_in_scanner(tmp_path, SCANNER_THAT_CRASHES)
    assert result.returncode == 1
    assert "did not run (exit code 1)" in result.stderr


def test_the_scan_config_keeps_the_default_rules_and_allows_one_rule_in_two_files():
    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True
    (allowed,) = config["allowlists"]
    assert allowed["targetRules"] == ["generic-api-key"]
    paths = allowed["paths"]
    assert all(re.search(p, "redteam/attacks.jsonl") for p in paths)
    assert all(re.search(p, "redteam/attacks-heldout.jsonl") for p in paths)
    for other in (
        "redteam/other.jsonl",
        "tests/redteam/attacks.jsonl",
        "src/attacks.jsonl",
        ".env",
    ):
        assert not any(re.search(p, other) for p in paths), other
