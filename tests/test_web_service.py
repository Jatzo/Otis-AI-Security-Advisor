"""The demo's wiring to a real store, with a stand-in model client. No test here calls the API."""

import json
import sqlite3
import threading

import pytest
from generation_world import DB, A, B, StubClient, reply

from advisor.generation import answer
from advisor.retrieval.units import build_units
from advisor.web import ask, service
from advisor.web.limits import Limits

DB.commit()  # the shared test store has an open write transaction, which blocks a backup
PASSES = {"ids": [A], "claims": [{"kind": "package", "record": A, "package": "django"}]}
GOOD = json.dumps({"question": f"Which versions of django does {A} affect?"}).encode()


@pytest.fixture
def store(tmp_path):
    """The small test store, written to a file, as the demo reads its own."""
    path = tmp_path / "advisor.db"
    disk = sqlite3.connect(path)
    DB.backup(disk)
    disk.close()
    return path


def test_the_demo_will_not_start_without_a_store(tmp_path):
    with pytest.raises(service.StartupError, match="no store at"):
        service.build_deps(tmp_path / "missing.db", StubClient())


def test_the_demo_will_not_start_on_a_store_with_no_records(tmp_path):
    empty = tmp_path / "empty.db"
    from advisor import store as schema

    disk = sqlite3.connect(empty)
    disk.executescript(schema.SCHEMA)
    disk.close()
    with pytest.raises(service.StartupError, match="no records"):
        service.build_deps(empty, StubClient())


def test_the_demo_will_not_start_without_a_key(store, monkeypatch):
    monkeypatch.setattr(answer, "read_key", lambda: None)
    with pytest.raises(service.StartupError, match="ANTHROPIC_API_KEY"):
        service.from_environment(store)


def test_a_key_in_the_environment_is_used_and_never_in_the_error(store, monkeypatch):
    monkeypatch.setattr(answer, "read_key", lambda: "key-for-this-test-only")  # noqa: S106
    deps = service.from_environment(store, Limits(timeout_s=45))
    assert deps.client.timeout == 45 and deps.client.max_retries == 0
    monkeypatch.setattr(answer, "read_key", lambda: None)
    with pytest.raises(service.StartupError) as caught:
        service.from_environment(store)
    assert "key-for-this-test-only" not in str(caught.value)


def test_the_index_is_built_at_startup_and_not_on_the_first_question():
    units = build_units(DB)
    _, pipeline = service.build_retrieve(units)
    assert ("header", False) in pipeline.indexes


def test_retrieval_puts_the_record_a_question_names_first_and_returns_at_most_ten():
    retrieve, _ = service.build_retrieve(build_units(DB))
    shown = retrieve(f"Which versions of django does {A} affect?")
    assert shown[0].unit_id == f"ghsa:{A}"
    assert len(shown) <= service.SHOWN
    assert retrieve(f"What does {B} cover?")[0].unit_id == f"ghsa:{B}"


def test_a_question_goes_through_the_real_retrieval_to_the_model_and_back(store):
    client = StubClient(reply(explanation="Fixed in 3.0.5.", **PASSES))
    deps = service.build_deps(store, client, clock=lambda: 1_000_000.0)
    status, body = ask.handle(deps, "1.2.3.4", None, GOOD)
    assert status == 200 and body["state"] == "answer"
    sent = client.requests[0]["messages"][0]["content"]
    assert f'<evidence id="ghsa:{A}">' in sent  # the real unit, from the store on disk


def test_many_visitors_at_once_all_get_an_answer_from_one_shared_store(store):
    client = StubClient(reply(explanation="Fixed in 3.0.5.", **PASSES))
    # A cap high enough that the money held for 40 requests at once is not what is being tested.
    limits = Limits(daily_spend_usd=1000.0)
    deps = service.build_deps(store, client, clock=lambda: 1_000_000.0, limits=limits)
    results, errors = [], []

    def visitor(number):
        try:
            results.append(ask.handle(deps, f"10.0.0.{number}", None, GOOD)[0])
        except Exception as caught:  # a thread's failure would otherwise vanish
            errors.append(caught)

    threads = [threading.Thread(target=visitor, args=(n,)) for n in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [] and results == [200] * 40
    assert len(client.requests) == 40


def test_the_store_is_opened_read_only(store):
    deps = service.build_deps(store, StubClient())
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        deps.facts.db.execute("DELETE FROM records")
