"""The freeze guard, run against small throwaway git repositories. No network."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_eval_frozen", Path("scripts/check_eval_frozen.py")
)
guard = importlib.util.module_from_spec(spec)
sys.modules["check_eval_frozen"] = guard
spec.loader.exec_module(guard)


def git(repo, *args):
    done = subprocess.run(  # noqa: S603
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", "-c",  # noqa: S607
         "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return done.stdout


def write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def commit(repo, message="change"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "eval/questions.jsonl", "q1\n")
    write(tmp_path, "eval/score.py", "print(1)\n")
    write(tmp_path, "eval/errata.jsonl", "")
    write(tmp_path, "src/other.py", "x = 1\n")
    commit(tmp_path, "freeze")
    git(tmp_path, "tag", "eval-freeze-v1")
    return tmp_path


def test_a_repo_that_matches_its_freeze_tag_passes(repo):
    assert guard.check(repo) == []


def test_a_change_outside_eval_is_not_a_problem(repo):
    write(repo, "src/other.py", "x = 2\n")
    commit(repo)

    assert guard.check(repo) == []


def test_results_and_appended_errata_are_allowed(repo):
    write(repo, "eval/results/baseline-dev.jsonl", "{}\n")
    write(repo, "eval/errata.jsonl", '{"id": "lk-001"}\n')
    commit(repo)
    write(repo, "eval/errata.jsonl", '{"id": "lk-001"}\n{"id": "lk-002"}\n')
    commit(repo)

    assert guard.check(repo) == []


def test_a_frozen_file_edited_after_the_tag_is_named(repo):
    write(repo, "eval/questions.jsonl", "q1 changed\n")
    commit(repo)

    (problem,) = guard.check(repo)

    assert "eval/questions.jsonl was changed after eval-freeze-v1" in problem
    assert "errata" in problem


def test_a_frozen_file_deleted_or_added_after_the_tag_is_named(repo):
    (repo / "eval/score.py").unlink()
    write(repo, "eval/extra.py", "y = 1\n")
    commit(repo)

    problems = guard.check(repo)

    assert any("eval/score.py was deleted" in p for p in problems)
    assert any("eval/extra.py is new" in p for p in problems)


def test_errata_rewritten_rather_than_appended_fails(repo):
    write(repo, "eval/errata.jsonl", '{"id": "lk-001"}\n')
    commit(repo)
    git(repo, "tag", "eval-freeze-v1.1")
    write(repo, "eval/errata.jsonl", '{"id": "lk-999"}\n')
    commit(repo)

    problems = guard.check(repo, "eval-freeze-v1.1")

    assert any("edited, not appended to" in p for p in problems)


def test_a_missing_tag_fails_and_says_how_to_fix_it(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "eval/questions.jsonl", "q1\n")
    commit(tmp_path)

    (problem,) = guard.check(tmp_path)

    assert "does not exist" in problem and "fetch" in problem


def test_a_rewritten_history_that_drops_the_tag_commit_fails(repo):
    git(repo, "checkout", "-q", "--orphan", "rewritten")
    commit(repo, "same files, new history")

    problems = guard.check(repo)

    assert any("not an ancestor" in p for p in problems)


def test_the_newest_freeze_tag_is_the_one_held_to_and_v1_1_sorts_after_v1(repo):
    write(repo, "eval/score.py", "print(2)\n")
    commit(repo, "fix the scorer")
    git(repo, "tag", "eval-freeze-v1.1")

    assert guard.freeze_tags(repo) == ["eval-freeze-v1", "eval-freeze-v1.1"]
    assert guard.check(repo) == []
    assert guard.check(repo, "eval-freeze-v1") != []


def test_the_command_exits_one_with_the_reason_on_stderr(repo, monkeypatch, capsys):
    write(repo, "eval/questions.jsonl", "q1 changed\n")
    commit(repo)
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["check_eval_frozen.py"])

    assert guard.main() == 1
    assert "FAIL: eval/questions.jsonl" in capsys.readouterr().err


def test_the_command_exits_zero_when_all_is_frozen(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["check_eval_frozen.py"])

    assert guard.main() == 0
    assert capsys.readouterr().out.startswith("OK")
