"""The demo's handler, wired to the real store and a real model client.

The handler in ask.py takes its retrieval and its client as arguments. This module builds them from
the store on disk and the key in the environment, and refuses to start when either is missing, so a
demo that cannot answer fails when it starts and not on the first visitor's question. The keyword
index is built here, once, and never on a request.
"""

import sqlite3
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic

from advisor.generation import answer
from advisor.generation.facts import Facts
from advisor.retrieval.pipeline import Pipeline, Spec
from advisor.retrieval.units import Unit, build_units
from advisor.web.ask import Deps
from advisor.web.limits import DEFAULT, Limits

SHOWN = 10  # the adopted rung's top 10, whole, as in every measured run
R1 = Spec("R1", bm25="header")
ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "data" / "advisor.db"


class StartupError(RuntimeError):
    """Raised when the demo cannot answer a question, with what to do about it."""


def build_retrieve(units: list[Unit]) -> tuple[Callable[[str], list[Unit]], Pipeline]:
    """Retrieval over the units by the adopted rung. The index is built now, so the first request
    does not pay for it and two first requests cannot both try to build it.

    The keyword index is an in-memory SQLite database that can only be used by the thread that
    opened it, and its code is part of the tagged system, so it is not changed. All retrieval runs
    on one worker thread instead. A search takes a few milliseconds, so queueing them costs
    nothing next to the model call that follows."""
    worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="retrieval")

    def build() -> Pipeline:
        built = Pipeline(units)
        built.index("header", False)
        return built

    pipeline = worker.submit(build).result()
    by_id = {unit.unit_id: unit for unit in units}

    def retrieve(question: str) -> list[Unit]:
        ranked = worker.submit(pipeline.rank, R1, question).result()
        return [by_id[unit_id] for unit_id in ranked[:SHOWN]]

    return retrieve, pipeline


def make_client(key: str, limits: Limits = DEFAULT) -> anthropic.Anthropic:
    """No retries of its own: answer.ask retries what is worth retrying and counts each attempt."""
    return anthropic.Anthropic(api_key=key, timeout=limits.timeout_s, max_retries=0)


def open_store(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


class PerThreadFacts:
    """The checker's facts, with one read-only connection for each thread that asks. Sharing one
    SQLite connection between request threads failed under load with "bad parameter or other API
    misuse", so no connection is ever used by two threads. It stands in for Facts everywhere."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.local = threading.local()

    def current(self) -> Facts:
        if not hasattr(self.local, "facts"):
            self.local.facts = Facts(open_store(self.path))
        return self.local.facts

    def __getattr__(self, name: str):
        return getattr(self.current(), name)


def build_deps(
    store: Path | str,
    client,
    clock: Callable[[], float] = time.time,
    limits: Limits = DEFAULT,
    trusted_hops: int = 0,
) -> Deps:
    path = Path(store)
    if not path.is_file():
        raise StartupError(f"There is no store at {path}. Build it, or copy data/advisor.db there.")
    db = open_store(path)
    units = build_units(db)
    db.close()
    if not units:
        raise StartupError(f"The store at {path} holds no records.")
    retrieve, _ = build_retrieve(units)
    return Deps(
        facts=PerThreadFacts(path),
        retrieve=retrieve,
        client=client,
        system=answer.system_prompt(),
        clock=clock,
        limits=limits,
        trusted_hops=trusted_hops,
    )


def from_environment(
    store: Path | str = STORE, limits: Limits = DEFAULT, trusted_hops: int = 0
) -> Deps:
    """What the deployed demo calls. The key comes from the environment and is never printed."""
    key = answer.read_key()
    if not key:
        raise StartupError("No ANTHROPIC_API_KEY. Set it as a secret, then start again.")
    return build_deps(store, make_client(key, limits), time.time, limits, trusted_hops)
