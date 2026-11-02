"""The guards that keep the test split scored once. No test here reads a test question."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = load("phase5_preflight_for_tests", "scripts/phase5_preflight.py")
runner = load("run_generation_for_phase5_tests", "scripts/run_generation.py")


def fake_git(tag_exists=True, differs=False, untracked=""):
    def run_git(*args):
        if args[0] == "rev-parse":
            return SimpleNamespace(returncode=0 if tag_exists else 1, stdout="")
        if args[0] == "diff":
            return SimpleNamespace(returncode=1 if differs else 0, stdout="")
        if args[0] == "ls-files":
            return SimpleNamespace(returncode=0, stdout=untracked)
        raise AssertionError(args)

    return run_git


def test_the_system_must_be_tagged_and_unchanged_before_a_test_row_runs():
    assert preflight.problems("t", fake_git()) == []
    assert "does not exist" in preflight.problems("t", fake_git(tag_exists=False))[0]
    assert "differs from t" in preflight.problems("t", fake_git(differs=True))[0]
    assert "src/new.py" in preflight.problems("t", fake_git(untracked="src/new.py\n"))[0]


def test_the_check_leaves_results_and_errata_free_to_grow():
    assert ":(exclude)eval/results" in preflight.FROZEN
    assert ":(exclude)eval/errata.jsonl" in preflight.FROZEN


def test_a_row_with_a_reply_for_every_test_question_is_complete(tmp_path):
    path = tmp_path / "row.jsonl"
    assert not preflight.row_complete(path, {"a", "b"})
    path.write_text(json.dumps({"id": "a"}) + "\n", encoding="utf-8")
    assert not preflight.row_complete(path, {"a", "b"})
    path.write_text(
        json.dumps({"id": "a"}) + "\n" + json.dumps({"id": "b"}) + "\n", encoding="utf-8"
    )
    assert preflight.row_complete(path, {"a", "b"})


def args(**more):
    base = {"allow_test": True, "runs": 1, "dry_run": False, "recheck": False}
    return SimpleNamespace(**{**base, **more})


QUESTIONS = [{"id": "x-1"}, {"id": "x-2"}]


def test_the_test_run_needs_its_flag_a_single_run_and_never_a_dry_run(tmp_path):
    raw = tmp_path / "raw.jsonl"
    clean = lambda: []  # noqa: E731

    assert runner.test_problem(args(), raw, QUESTIONS, clean) is None
    assert "--allow-test" in runner.test_problem(args(allow_test=False), raw, QUESTIONS, clean)
    assert "single run" in runner.test_problem(args(runs=3), raw, QUESTIONS, clean)
    assert "dry run" in runner.test_problem(args(dry_run=True), raw, QUESTIONS, clean)


def test_the_test_run_refuses_a_second_pass_and_an_untagged_system(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.write_text("".join(json.dumps(q) + "\n" for q in QUESTIONS), encoding="utf-8")

    assert "scored once" in runner.test_problem(args(), raw, QUESTIONS, lambda: [])
    raw.unlink()
    assert runner.test_problem(args(), raw, QUESTIONS, lambda: ["no tag"]) == "no tag"


def test_the_test_files_are_their_own_and_cannot_take_a_smoke_run_or_a_label():
    raw, checked = runner.result_paths(False, None, "test")
    assert (raw.name, checked.name) == (
        "test-generation-raw.jsonl",
        "test-generation-checked.jsonl",
    )
    with pytest.raises(SystemExit):
        runner.result_paths(True, None, "test")
    with pytest.raises(SystemExit):
        runner.result_paths(False, "v2", "test")


def test_each_phase_counts_its_own_spend_and_not_the_others(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    for name, cost in [
        ("generation-dev-raw.jsonl", 3.0),
        ("generation-v2-dev-raw.jsonl", 2.0),
        ("test-generation-raw.jsonl", 1.0),
        ("test-longcontext-raw.jsonl", 0.5),
        ("baseline-test.jsonl", 0.25),
        ("phase5-l-smoke-dev-raw.jsonl", 0.125),
    ]:
        (tmp_path / name).write_text(
            json.dumps({"id": "q", "cost_usd": cost}) + "\n", encoding="utf-8"
        )

    assert runner.phase_spent("dev") == 5.0
    assert runner.phase_spent("test") == 1.875
