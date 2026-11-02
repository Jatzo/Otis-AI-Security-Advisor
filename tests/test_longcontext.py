"""The long-context row: the prompt, the request and the runner, against a stub client."""

import importlib.util
import json
import sys
from pathlib import Path

import anthropic
import httpx2
import pytest
from generation_world import UNITS, A, B, StubClient

from advisor.generation import answer
from advisor.longcontext import (
    ADDENDUM_FILE,
    build_request,
    package_records,
    packages_named,
    system_blocks,
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rows = load("run_longcontext_for_tests", "scripts/run_longcontext.py")
runner = rows.load_runner()
UNIT_LIST = list(UNITS.values())
PROOF = {
    "commit": "abc",
    "dirty": False,
    "hashes": {"task.md": "1", "longcontext_addendum.md": "2"},
}
QUESTION = {"id": "q-1", "split": "dev", "question": f"Is django 3.0.4 affected by {A}?"}
OTHER = {"id": "q-2", "split": "dev", "question": f"Is axios 1.3.2 affected by {B}?"}


def test_the_addendum_is_the_one_written_in_the_plan():
    plan = Path("docs/test-plan.md").read_text(encoding="utf-8")
    block = plan.split("The addendum for this row, word for word:")[1].split("```")[1]

    assert block.strip() == ADDENDUM_FILE.read_text(encoding="utf-8").strip()


def test_the_prompt_holds_every_record_of_the_named_package_and_no_other():
    records = package_records(UNIT_LIST, packages_named(QUESTION["question"]))

    assert [u.unit_id for u in records] == [f"ghsa:{A}", "nvd:CVE-2020-0001"]
    assert all("django" in u.packages for u in records)


def test_the_records_are_in_a_cached_block_after_the_instructions_and_the_order_is_fixed():
    records = package_records(UNIT_LIST, ["django"])
    first, second = system_blocks(records), system_blocks(list(reversed(records)))

    assert first[0] == {
        "type": "text",
        "text": rows.answer.TASK_FILE.read_text("utf-8") + "\n" + ADDENDUM_FILE.read_text("utf-8"),
    }
    assert first[1]["cache_control"] == {"type": "ephemeral"} and "cache_control" not in first[0]
    assert "<evidence id=" in first[1]["text"]
    assert first == system_blocks(records) and second[1]["text"] != ""


def test_the_request_has_the_baselines_settings_and_the_question_alone_in_the_user_turn():
    request = build_request(system_blocks([]), "What?")

    assert request["model"] == answer.MODEL and request["max_tokens"] == answer.MAX_TOKENS
    assert request["output_config"] == {"effort": answer.EFFORT}
    assert request["messages"] == [{"role": "user", "content": "Question: What?"}]
    assert not {"temperature", "top_p", "top_k", "tools", "fallbacks"} & set(request)


def test_the_worst_case_is_every_token_at_full_price_plus_the_whole_output_limit():
    assert rows.worst_case(1_000_000) == pytest.approx(2.0 + 0.16)


def start(tmp_path, monkeypatch, client, questions, **caps):
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    raw, missed = tmp_path / "raw.jsonl", tmp_path / "missed.json"
    settings = {"max_spend": 10.0, "phase_cap": 10.0, **caps}
    message = rows.run_questions(
        runner, questions, UNIT_LIST, raw, missed, client, proof=PROOF, **settings
    )
    return raw, missed, message


def test_the_runner_writes_a_baseline_format_line_and_names_the_packages(tmp_path, monkeypatch):
    client = StubClient("{}")

    raw, _, message = start(tmp_path, monkeypatch, client, [QUESTION])

    (line,) = [json.loads(x) for x in raw.read_text("utf-8").splitlines()]
    assert message.startswith("Done.") and len(client.requests) == 1
    assert line["id"] == "q-1" and line["packages"] == ["django"] and line["shown"] == []
    assert line["cost_usd"] > 0 and line["hashes"] == PROOF["hashes"]
    system = client.requests[0]["system"]
    assert isinstance(system, list) and system[1]["cache_control"]


def test_a_question_the_api_refuses_is_listed_as_not_asked_and_is_not_a_reply(
    tmp_path, monkeypatch
):
    refusal = anthropic.BadRequestError(
        "prompt is too long",
        response=httpx2.Response(400, request=httpx2.Request("POST", "https://example.test")),
        body=None,
    )

    class Refusing(StubClient):
        def create(self, **request):
            raise refusal

    raw, missed, _ = start(tmp_path, monkeypatch, Refusing(), [QUESTION])

    assert not raw.exists() or raw.read_text("utf-8") == ""
    assert [m["id"] for m in json.loads(missed.read_text("utf-8"))] == ["q-1"]


def test_the_runner_stops_before_a_call_that_could_pass_a_cap_and_does_not_resume_twice(
    tmp_path, monkeypatch
):
    stopped = StubClient("{}")
    _, _, message = start(tmp_path, monkeypatch, stopped, [QUESTION], max_spend=0.01)
    first = StubClient("{}")
    raw, _, _ = start(tmp_path, monkeypatch, first, [QUESTION, OTHER])
    again = StubClient("{}")
    rows.run_questions(
        runner,
        [QUESTION, OTHER],
        UNIT_LIST,
        raw,
        raw.with_name("missed.json"),
        again,
        10.0,
        10.0,
        PROOF,
    )

    assert stopped.requests == [] and message.startswith("Stopped")
    assert len(first.requests) == 2 and again.requests == []


def test_a_file_made_with_another_prompt_is_never_appended_to(tmp_path, monkeypatch):
    raw, _, _ = start(tmp_path, monkeypatch, StubClient("{}"), [QUESTION])
    changed = {**PROOF, "hashes": {"task.md": "1", "longcontext_addendum.md": "9"}}

    with pytest.raises(SystemExit):
        rows.run_questions(
            runner,
            [OTHER],
            UNIT_LIST,
            raw,
            raw.with_name("m.json"),
            StubClient("{}"),
            10.0,
            10.0,
            changed,
        )


def test_the_smoke_run_takes_five_small_package_dev_questions_and_the_test_run_is_guarded():
    smoke = rows.package_questions(runner, "dev", smoke=True)

    assert len(smoke) == 5 and {q["split"] for q in smoke} == {"dev"}
    assert all(packages_named(q["question"]) for q in smoke)
    assert rows.paths(True)[0].name == "phase5-l-smoke-dev-raw.jsonl"
    assert rows.paths(False)[0].name == "test-longcontext-raw.jsonl"
