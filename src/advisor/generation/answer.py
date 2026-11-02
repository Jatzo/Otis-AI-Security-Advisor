"""The answer call: one model at the baseline's settings, with retrieved evidence in front of it.

The settings are the baseline's (eval/run_baseline.py) and a test holds them equal, so the only
differences from the baseline are the ones docs/generation-plan.md names: the evidence, the
addendum, the claims field and the checker.
"""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import anthropic

from advisor.generation.checker import Checked, check
from advisor.generation.evidence import user_message
from advisor.generation.facts import Facts
from advisor.generation.reading import ids_in
from advisor.retrieval.units import Unit

ROOT = Path(__file__).resolve().parents[3]
TASK_FILE = ROOT / "eval" / "task.md"
ADDENDUM_FILE = Path(__file__).resolve().parent / "addendum.md"
MODEL = "claude-sonnet-5-5"
EFFORT = "high"
MAX_TOKENS = 16000
ATTEMPTS = 3
# Dollars per million tokens, stored on every result line so a later price change cannot rewrite
# what an old run cost.
PRICE = {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50}
RETRYABLE = (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError)


def system_prompt() -> str:
    """The task (scope and the scored reply), then the addendum in place of the baseline's."""
    return TASK_FILE.read_text(encoding="utf-8") + "\n" + ADDENDUM_FILE.read_text(encoding="utf-8")


def build_request(system: str, message: str) -> dict:
    """No temperature, no prefill, no fallback model: one model, as it came."""
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": EFFORT},
        "messages": [{"role": "user", "content": message}],
    }


def cost_of(usage: dict) -> float:
    return (
        usage["input"] * PRICE["input"]
        + usage["output"] * PRICE["output"]
        + usage["cache_read"] * PRICE["cache_read"]
        + usage["cache_write"] * PRICE["cache_write"]
    ) / 1_000_000


def worst_case_call(system: str, message: str) -> float:
    """The most one call can cost: every input token at the full price (three characters a token
    is generous) and the whole output limit spent."""
    tokens_in = (len(system) + len(message)) // 3
    return (tokens_in * PRICE["input"] + MAX_TOKENS * PRICE["output"]) / 1_000_000


def read_key() -> str | None:
    """ANTHROPIC_API_KEY from the environment or from .env. Never printed."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env_file = ROOT / ".env"
    if env_file.exists():
        # utf-8-sig, because PowerShell and Notepad can write a byte-order mark.
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY" and value.strip():
                return value.strip().strip("\"'")
    return None


def ask(client, request: dict, sleep: Callable = time.sleep) -> tuple[object, int, float]:
    """One reply, retrying only what is worth retrying. Returns the reply, the attempts used and the
    seconds the successful attempt took. The SDK's own retries are off, so every attempt counts."""
    for attempt in range(1, ATTEMPTS + 1):
        started = time.monotonic()
        try:
            reply = client.messages.create(**request)
        except RETRYABLE:
            if attempt == ATTEMPTS:
                raise
            sleep(2**attempt)
        else:
            return reply, attempt, time.monotonic() - started
    raise AssertionError("unreachable")


def result_line(
    question: dict, run: int, reply, attempts: int, seconds: float, shown: list[Unit], proof: dict
) -> dict:
    """A line in the baseline's format, plus the units shown, which a re-check needs."""
    usage = {
        "input": reply.usage.input_tokens or 0,
        "output": reply.usage.output_tokens or 0,
        "cache_read": getattr(reply.usage, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(reply.usage, "cache_creation_input_tokens", 0) or 0,
    }
    details = getattr(reply, "stop_details", None)
    return {
        "id": question["id"], "run": run, "split": question["split"],
        "text": "".join(b.text for b in reply.content if b.type == "text"),
        "stop_reason": reply.stop_reason,
        "stop_category": getattr(details, "category", None) if details else None,
        "usage": usage, "price": PRICE, "cost_usd": cost_of(usage),
        "latency_s": round(seconds, 3), "attempts": attempts,
        "request_id": getattr(reply, "_request_id", None), "model": reply.model,
        "requested_model": MODEL, "effort": EFFORT, "max_tokens": MAX_TOKENS,
        "shown": [unit.unit_id for unit in shown], **proof,
    }  # fmt: skip


@dataclass
class Response:
    checked: Checked
    line: dict | None  # None when the gate answered and the model was not called


def respond(
    question: dict,
    shown: list[Unit],
    facts: Facts,
    client,
    system: str,
    proof: dict | None = None,
    *,
    ask_anyway: bool = False,
    sleep: Callable = time.sleep,
) -> Response:
    """Answer one question. A question that names an ID the store does not hold gets a refusal and
    the model is never called (rule 1). ask_anyway is for the dev run, which still wants a raw
    reply to put beside the gate's."""
    text = question["question"]
    gated = any(not facts.holds_id(found) for found in dict.fromkeys(ids_in(text)))
    if gated and not ask_anyway:
        return Response(check(text, "", None, shown, facts), None)
    reply, attempts, seconds = ask(client, build_request(system, user_message(shown, text)), sleep)
    line = result_line(question, 1, reply, attempts, seconds, shown, proof or {})
    return Response(check(text, line["text"], line["stop_reason"], shown, facts), line)
