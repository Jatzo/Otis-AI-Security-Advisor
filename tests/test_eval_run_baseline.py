"""The baseline runner, run against a fake client. No network, no key, no spend."""

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

spec = importlib.util.spec_from_file_location("run_baseline", Path("eval/run_baseline.py"))
runner = importlib.util.module_from_spec(spec)
sys.modules["run_baseline"] = runner
spec.loader.exec_module(runner)

PROOF = {"commit": "abc123", "hashes": {"task.md": "00"}}
ID_PATTERN = re.compile(r"GHSA(?:-[0-9a-z]{4}){3}|CVE-\d{4}-\d{4,}", re.IGNORECASE)


def reply(text="{}", stop="end_turn", out=1000, category=None, extra_blocks=()):
    blocks = [*extra_blocks, SimpleNamespace(type="text", text=text)]
    details = SimpleNamespace(category=category) if category else None
    return SimpleNamespace(
        content=blocks, stop_reason=stop, stop_details=details, model="claude-sonnet-5-5",
        usage=SimpleNamespace(input_tokens=1000, output_tokens=out,
                              cache_read_input_tokens=0, cache_creation_input_tokens=None),
        _request_id="req_1",
    )  # fmt: skip


class FakeClient:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else reply()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def questions(n=3):
    return [{"id": f"q-{i}", "split": "dev", "question": f"Question {i}?"} for i in range(n)]


def run(tmp_path, client, qs=None, runs=1, cap=100.0):
    results = tmp_path / "baseline-dev.jsonl"
    message = runner.run_split(
        qs or questions(), results, client, runs, cap, PROOF, say=lambda _: 0
    )
    return results, message


def lines(path):
    return [json.loads(x) for x in path.read_text("utf-8").splitlines()]


# --- the request ---


def test_the_request_is_one_model_at_fixed_settings_with_only_the_question_as_the_user_turn():
    request = runner.build_request("What is the first patched version?", "SYSTEM")

    assert request["model"] == "claude-sonnet-5-5"
    assert request["max_tokens"] == 16000
    assert request["output_config"] == {"effort": "high"}
    assert request["messages"] == [
        {"role": "user", "content": "What is the first patched version?"}
    ]
    assert not {"temperature", "top_p", "top_k", "fallbacks", "betas", "tools"} & set(request)


def test_the_system_prompt_holds_no_id_and_no_question_from_the_set():
    system = runner.system_prompt()
    committed = "".join(
        (Path("eval") / name).read_text("utf-8") for name in ("questions.jsonl", "gold.jsonl")
    )
    asked = [
        json.loads(x)["question"]
        for x in (Path("eval/questions.jsonl")).read_text("utf-8").split("\n")
        if x
    ]

    assert ID_PATTERN.findall(system) == []
    assert [q for q in asked if q in system] == []
    assert "django" in system and committed


def test_the_system_prompt_gives_the_scope_and_says_there_is_no_retrieval():
    system = runner.system_prompt()

    assert "1 November 2026" in system and "18 packages" in system
    assert "no documents, no search and no tools" in system


# --- cost ---


def test_cost_follows_the_stored_price_per_million_tokens():
    usage = {"input": 1000, "output": 2000, "cache_read": 0, "cache_write": 0}

    assert runner.cost_of(usage) == pytest.approx(0.022)


def test_the_worst_case_for_one_call_is_about_the_full_output_limit():
    worst = runner.worst_case_call(runner.system_prompt(), "A question?")

    assert 0.16 < worst < 0.17


# --- running ---


def test_every_reply_is_written_with_its_cost_proof_and_request_details(tmp_path):
    results, message = run(tmp_path, FakeClient(reply('{"abstain": true}')), questions(1))

    (line,) = lines(results)

    assert message.startswith("Done")
    assert line["id"] == "q-0" and line["run"] == 1 and line["text"] == '{"abstain": true}'
    assert line["commit"] == "abc123" and line["hashes"] == {"task.md": "00"}
    assert line["price"]["output"] == 10.0 and line["cost_usd"] == pytest.approx(0.012)
    assert line["attempts"] == 1 and line["request_id"] == "req_1"
    assert line["model"] == "claude-sonnet-5-5" and line["effort"] == "high"


def test_only_the_text_blocks_of_a_reply_are_kept_in_order(tmp_path):
    thinking = SimpleNamespace(type="thinking", thinking="private")
    results, _ = run(tmp_path, FakeClient(reply("{}", extra_blocks=[thinking])), questions(1))

    assert lines(results)[0]["text"] == "{}"


def test_a_refusal_and_a_cut_short_reply_are_recorded_as_they_came(tmp_path):
    client = FakeClient(reply("", "refusal", category="cyber"), reply("{", "max_tokens", out=16000))

    results, _ = run(tmp_path, client, questions(2))

    refused, cut = lines(results)
    assert (refused["stop_reason"], refused["stop_category"]) == ("refusal", "cyber")
    assert cut["stop_reason"] == "max_tokens" and cut["stop_category"] is None


def test_a_second_start_asks_only_the_questions_not_yet_answered(tmp_path):
    results, _ = run(tmp_path, FakeClient(), questions(2))
    client = FakeClient()

    run(tmp_path, client, questions(3))

    assert [r["messages"][0]["content"] for r in client.requests] == ["Question 2?"]
    assert len(lines(results)) == 3


def test_repeat_runs_are_numbered_and_each_question_is_asked_once_per_run(tmp_path):
    client = FakeClient()

    results, _ = run(tmp_path, client, questions(2), runs=3)

    assert [(x["run"], x["id"]) for x in lines(results)] == [
        (1, "q-0"), (1, "q-1"), (2, "q-0"), (2, "q-1"), (3, "q-0"), (3, "q-1"),
    ]  # fmt: skip


def test_the_spend_cap_stops_the_run_before_a_call_that_could_pass_it(tmp_path):
    client = FakeClient(*[reply(out=16000)] * 5)

    results, message = run(tmp_path, client, questions(5), cap=0.30)

    assert message.startswith("Stopped") and "cap $0.30" in message
    assert len(client.requests) == len(lines(results)) == 1


def test_the_cap_counts_what_earlier_runs_already_spent(tmp_path):
    run(tmp_path, FakeClient(reply(out=16000)), questions(1))
    client = FakeClient()

    _, message = run(tmp_path, client, questions(3), cap=0.20)

    assert message.startswith("Stopped") and client.requests == []


def connection_error():
    return anthropic.APIConnectionError(request=httpx2.Request("POST", "https://example.test"))


def test_a_dropped_connection_is_retried_and_the_attempts_are_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    client = FakeClient(connection_error(), connection_error(), reply())

    results, _ = run(tmp_path, client, questions(1))

    assert lines(results)[0]["attempts"] == 3


def test_a_third_failure_stops_the_run_with_what_was_already_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)
    client = FakeClient(reply(), connection_error(), connection_error(), connection_error())

    with pytest.raises(anthropic.APIConnectionError):
        run(tmp_path, client, questions(3))

    assert len(lines(tmp_path / "baseline-dev.jsonl")) == 1


# --- the freeze check ---


class FakeGit:
    def __init__(self, tag=True, diff=0, untracked=""):
        self.tag, self.diff, self.untracked = tag, diff, untracked

    def __call__(self, *args):
        code, out = 0, ""
        if args[0] == "rev-parse":
            code = 0 if self.tag else 1
        elif args[0] == "diff":
            code = self.diff
        elif args[0] == "ls-files":
            out = self.untracked
        return subprocess.CompletedProcess(args, code, stdout=out)


def test_a_real_run_needs_the_freeze_tag_and_untouched_frozen_files():
    assert runner.frozen_problem("t", FakeGit()) is None
    assert "does not exist" in runner.frozen_problem("t", FakeGit(tag=False))
    assert "differs" in runner.frozen_problem("t", FakeGit(diff=1))
    assert "Untracked" in runner.frozen_problem("t", FakeGit(untracked="eval/new.py\n"))


def test_results_and_errata_are_outside_the_freeze_check():
    seen = []

    def spy(*args):
        seen.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="")

    runner.frozen_problem("t", spy)

    diff = next(a for a in seen if a[0] == "diff")
    assert ":(exclude)eval/results" in diff and ":(exclude)eval/errata.jsonl" in diff


# --- the command line ---


def call(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["run_baseline.py", *argv])
    return runner.main()


def test_a_dry_run_prints_the_request_and_calls_nothing(monkeypatch, capsys):
    def no_client(*a, **k):
        raise AssertionError("a dry run must not build a client")

    monkeypatch.setattr(runner.anthropic, "Anthropic", no_client)

    assert call(monkeypatch, "--dry-run") == 0
    printed = capsys.readouterr().out
    assert "claude-sonnet-5-5" in printed and "Worst case" in printed


def test_test_questions_need_the_flag_and_a_single_run(monkeypatch, capsys):
    assert call(monkeypatch, "--split", "test", "--max-spend", "5") == 1
    assert (
        call(monkeypatch, "--split", "test", "--allow-test", "--runs", "2", "--max-spend", "5") == 1
    )
    assert "scored once" in capsys.readouterr().out


def test_a_real_run_without_a_spend_cap_is_refused(monkeypatch, capsys):
    assert call(monkeypatch) == 1
    assert "--max-spend" in capsys.readouterr().out


def test_a_missing_key_says_where_to_put_it_and_the_key_is_never_printed(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(runner, "frozen_problem", lambda tag: None)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert call(monkeypatch, "--max-spend", "5") == 1
    assert ".env" in capsys.readouterr().out

    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY='sk-test-123'\n")
    assert runner.read_key() == "sk-test-123"


def test_a_key_file_with_a_byte_order_mark_is_still_read(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_bytes(("\ufeffANTHROPIC_API_KEY=sk-test-456\r\n").encode())

    assert runner.read_key() == "sk-test-456"
