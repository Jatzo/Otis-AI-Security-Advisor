"""The Dev-R freeze guard, run against small throwaway git repositories. No network."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_eval_retrieval_frozen", Path("scripts/check_eval_retrieval_frozen.py")
)
guard = importlib.util.module_from_spec(spec)
sys.modules["check_eval_retrieval_frozen"] = guard
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
    write(tmp_path, "eval-retrieval/questions.jsonl", "q1\n")
    write(tmp_path, "eval-retrieval/errata.jsonl", '{"id": "dr-lk-000"}\n')
    write(tmp_path, "eval/questions.jsonl", "v1\n")
    commit(tmp_path, "freeze")
    git(tmp_path, "tag", "eval-freeze-retrieval-v1")
    return tmp_path


def test_a_repo_that_matches_its_tag_passes(repo):
    assert guard.check(repo) == []


def test_a_change_to_v1_is_not_this_guards_business(repo):
    write(repo, "eval/questions.jsonl", "v1 changed\n")
    commit(repo)

    assert guard.check(repo) == []


def test_results_and_appended_errata_are_allowed(repo):
    write(repo, "eval-retrieval/results/run.jsonl", "{}\n")
    write(repo, "eval-retrieval/errata.jsonl", '{"id": "dr-lk-000"}\n{"id": "dr-lk-001"}\n')
    commit(repo)
    write(
        repo,
        "eval-retrieval/errata.jsonl",
        '{"id": "dr-lk-000"}\n{"id": "dr-lk-001"}\n{"id": "dr-lk-002"}\n',
    )
    commit(repo)

    assert guard.check(repo) == []


def test_a_frozen_file_edited_after_the_tag_is_named(repo):
    write(repo, "eval-retrieval/questions.jsonl", "q1 changed\n")
    commit(repo)

    (problem,) = guard.check(repo)

    assert "eval-retrieval/questions.jsonl was changed after eval-freeze-retrieval-v1" in problem


def test_a_new_file_and_a_deleted_file_are_named(repo):
    write(repo, "eval-retrieval/extra.jsonl", "x\n")
    (repo / "eval-retrieval" / "questions.jsonl").unlink()
    commit(repo)

    problems = guard.check(repo)

    assert any("eval-retrieval/extra.jsonl is new" in p for p in problems)
    assert any("eval-retrieval/questions.jsonl was deleted" in p for p in problems)


def test_edited_errata_is_named(repo):
    write(repo, "eval-retrieval/errata.jsonl", '{"id": "dr-lk-999"}\n')
    commit(repo)

    assert any("edited, not appended to" in p for p in guard.check(repo))


def test_a_missing_tag_fails(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "eval-retrieval/questions.jsonl", "q1\n")
    commit(tmp_path)

    (problem,) = guard.check(tmp_path)

    assert "does not exist" in problem
