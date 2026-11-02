"""The long-context row: the model is given every record of the package a question names.

It asks whether reading everything beats retrieving (docs/test-plan.md).
There is no claims field and no checker. The package records go in a cached system block so that
consecutive questions about one package share a prefix; caching changes the price and nothing else.
"""

from pathlib import Path

from advisor.generation.answer import EFFORT, MAX_TOKENS, MODEL, TASK_FILE
from advisor.generation.evidence import render_unit
from advisor.retrieval.query import named_packages
from advisor.retrieval.units import Unit

ADDENDUM_FILE = Path(__file__).resolve().parent / "addendum.md"


def packages_named(question: str) -> list[str]:
    return sorted(named_packages(question))


def package_records(units: list[Unit], packages: list[str]) -> list[Unit]:
    """Every unit of the named packages, in unit id order, so the same package always gives the same
    prefix and the cache can hold it."""
    wanted = set(packages)
    return sorted((u for u in units if u.packages & wanted), key=lambda u: u.unit_id)


def instructions() -> str:
    return TASK_FILE.read_text(encoding="utf-8") + "\n" + ADDENDUM_FILE.read_text(encoding="utf-8")


def system_blocks(records: list[Unit]) -> list[dict]:
    text = "\n\n".join(render_unit(unit) for unit in records) or "No records were found."
    return [
        {"type": "text", "text": instructions()},
        {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}},
    ]


def build_request(blocks: list[dict], question: str) -> dict:
    """The baseline's settings: no temperature, no prefill, no fallback model."""
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": blocks,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
        "messages": [{"role": "user", "content": f"Question: {question}"}],
    }
