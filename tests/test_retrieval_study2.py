"""The Dev-R run script's rules, on made-up rows. It never touches Dev-R."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "retrieval_study2", Path("scripts/retrieval_study2.py")
)
study = importlib.util.module_from_spec(spec)
sys.modules["retrieval_study2"] = study
spec.loader.exec_module(study)


def cell(hit: bool, chars: int = 100) -> dict:
    return {"all": hit, "recall": 1.0 if hit else 0.0, "chars": chars, "ids": []}


def row(n, base, deep, linked=None, scoped=False, seen_dev=False, typ="multihop", names_id=False):
    """base: R1 at 10 hit. deep: R1 at 20 hit. linked: R9 hit (defaults to base)."""
    linked = base if linked is None else linked
    out = {
        "id": f"dr-{n}", "type": typ, "subtype": "x", "names_id": names_id,
        "seen_dev": seen_dev, "primary": typ != "lookup", "scoped": scoped,
    }  # fmt: skip
    for name, hit in {
        "R1@10": base, "R1@15": deep, "R1@20": deep, "R1@25": deep,
        "R9": linked, "R9x": linked, "R10": deep if scoped else base,
    }.items():  # fmt: skip
        out[name] = cell(hit)
    return out


def rows_with(gain: int, total: int = 150, lost: int = 0) -> list[dict]:
    rows = [row(i, False, True) for i in range(gain)]
    rows += [row(1000 + i, True, False) for i in range(lost)]
    rows += [row(2000 + i, True, True) for i in range(total - gain - lost)]
    return rows


def test_a_large_clean_gain_passes_rules_1_to_3_for_r11():
    report = study.analyse(rows_with(gain=12))

    assert report["rule1_enough_primary"]
    assert report["passes_rules_1_to_3"]["R11"]
    assert report["tests"]["R11"]["p"] < 0.05 / 2


def test_a_gain_under_the_floor_does_not_pass():
    report = study.analyse(rows_with(gain=7))  # 5 points of 150 is 7.5

    assert not report["passes_rules_1_to_3"]["R11"]


def test_fewer_than_140_primary_questions_is_descriptive_only():
    report = study.analyse(rows_with(gain=12, total=130))

    assert not report["rule1_enough_primary"]
    assert not any(report["passes_rules_1_to_3"].values())


def test_seen_dev_questions_are_held_out_of_every_test():
    rows = rows_with(gain=12) + [row(5000 + i, False, True, seen_dev=True) for i in range(30)]

    report = study.analyse(rows)

    assert report["tests"]["R11"]["n"] == 150
    assert report["seen_dev_questions"] == 30


def test_r10_is_judged_only_when_it_scopes_forty_primary_questions():
    few = study.analyse(rows_with(gain=12))
    scoped = [row(i, False, True, scoped=True) for i in range(40)]
    many = study.analyse(scoped + rows_with(gain=0, total=110))

    assert not few["r10_judged"]
    assert "R10" not in few["tests"]
    assert many["r10_judged"]
    assert "R10" in many["tests"]


def test_a_candidate_that_loses_two_questions_in_a_slice_fails_do_no_harm():
    rows = rows_with(gain=14)
    rows[-1] = row(9001, True, True, linked=False)
    rows[-2] = row(9002, True, True, linked=False)

    report = study.analyse(rows)

    assert report["tests"]["R9"]["lost"] == 2
    assert not report["do_no_harm"]["R9"]["passes"]
    assert not report["passes_rules_1_to_3"]["R9"]


def test_r11_cannot_lose_a_question_so_do_no_harm_holds_for_it():
    report = study.analyse(rows_with(gain=12))

    assert report["do_no_harm"]["R11"]["passes"]
    assert report["tests"]["R11"]["lost"] == 0


def test_holm_stops_at_the_first_failure():
    assert study.holm({"a": 0.01, "b": 0.04}) == {"a": True, "b": True}
    assert study.holm({"a": 0.04, "b": 0.045}) == {"a": False, "b": False}
    assert study.holm({"a": 0.001, "b": 0.2}) == {"a": True, "b": False}


def test_ties_between_passing_candidates_go_to_the_cheaper_one():
    rows = [row(i, False, True, linked=True) for i in range(14)]
    rows += [row(2000 + i, True, True) for i in range(136)]

    report = study.analyse(rows)

    assert report["passes_rules_1_to_3"]["R9"] and report["passes_rules_1_to_3"]["R11"]
    assert report["leading_candidate"] == "R9"


def test_r10_is_held_to_its_own_control_as_well_as_to_r1_at_10():
    scoped = [row(i, False, True, scoped=True) for i in range(40)]
    for r in scoped[:2]:  # R10 drops what R1@20 held, but R1@10 never held it
        r["R10"] = cell(False)
    rest = rows_with(gain=0, total=110)

    report = study.analyse(scoped + rest)

    harm = report["do_no_harm"]["R10"]
    assert harm["against_R1@10"]["passes"]
    assert not harm["against_R1@20"]["passes"]
    assert not harm["passes"]


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


@pytest.fixture
def tagged(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "eval-retrieval/questions.jsonl", "q\n")
    write(tmp_path, "scripts/retrieval_study2.py", "run\n")
    write(tmp_path, "src/advisor/retrieval/candidates.py", "cand\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "freeze")
    git(tmp_path, "tag", "eval-freeze-retrieval-v1")
    monkeypatch.setattr(study, "ROOT", tmp_path)
    monkeypatch.setattr(study, "OUT", tmp_path / "eval-retrieval" / "results" / "study2.json")
    return tmp_path


def test_a_tagged_unchanged_checkout_may_run(tagged):
    assert study.problems() == []


def test_the_run_refuses_without_the_freeze_tag(tagged):
    git(tagged, "tag", "-d", "eval-freeze-retrieval-v1")

    assert "does not exist" in study.problems()[0]


def test_the_run_refuses_when_a_frozen_file_is_edited_but_not_committed(tagged):
    write(tagged, "eval-retrieval/questions.jsonl", "edited\n")

    assert any("questions.jsonl" in line for line in study.problems())


def test_the_run_refuses_a_new_file_in_the_frozen_folder(tagged):
    write(tagged, "eval-retrieval/extra.jsonl", "x\n")

    assert any("extra.jsonl" in line for line in study.problems())


def test_the_run_refuses_when_the_script_or_candidates_changed_after_the_tag(tagged):
    write(tagged, "src/advisor/retrieval/candidates.py", "changed\n")
    git(tagged, "add", "-A")
    git(tagged, "commit", "-q", "-m", "later")

    assert any("committed again" in line for line in study.problems())


def test_the_run_refuses_to_run_twice_but_ignores_the_results_folder(tagged):
    write(tagged, "eval-retrieval/results/notes.txt", "scratch\n")
    assert study.problems() == []

    write(tagged, "eval-retrieval/results/study2.json", "{}\n")

    assert any("exists" in line for line in study.problems())
