"""One question in, one page's worth of data out, with every limit applied in order.

The handler takes plain values and the things it depends on, so a test can drive it with a fake
model and a fake clock. The order matters: the cheap refusals come first, and the model is only
reached by a question that has passed all of them and has reserved its worst-case cost.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from advisor.generation import answer
from advisor.generation.evidence import user_message
from advisor.generation.facts import Facts
from advisor.retrieval.units import Unit
from advisor.web.limits import (
    Limits,
    RateLimiter,
    SpendCap,
    client_address,
    on_topic,
    question_problem,
)
from advisor.web.view import view

log = logging.getLogger(__name__)

TOO_MANY = "That is a lot of questions in a short time. Wait a minute and ask again."
DAILY_FULL = "Otis has answered as many questions as it can today. Try again tomorrow."
OFF_TOPIC = (
    "Otis answers questions about advisories for 18 named packages. Name an advisory ID, a CVE "
    "or one of the packages, and ask again."
)
FAILED = "Otis could not answer that. Try again in a moment."
TOO_BIG = "That request is too large."
NOT_JSON = 'Send the question as JSON: {"question": "..."}.'


@dataclass
class Deps:
    facts: Facts
    retrieve: Callable[[str], list[Unit]]
    client: object
    system: str
    clock: Callable[[], float]
    limits: Limits = field(default_factory=Limits)
    limiter: RateLimiter | None = None
    spend: SpendCap | None = None
    trusted_hops: int = 0

    def __post_init__(self) -> None:
        self.limiter = self.limiter or RateLimiter(self.limits)
        self.spend = self.spend or SpendCap(self.limits)


def message(status: int, text: str) -> tuple[int, dict]:
    return status, {"state": "error", "explanation": text, "ids": [], "links": []}


def declined(text: str) -> tuple[int, dict]:
    return 200, {"state": "declined", "explanation": text, "ids": [], "links": []}


def handle(deps: Deps, peer: str, forwarded_for: str | None, body: bytes) -> tuple[int, dict]:
    """Returns the status and the data the page shows. Nothing in it comes from the model except
    through view(), and no error carries a trace or any text from the prompt."""
    if len(body) > deps.limits.body_bytes:
        return message(413, TOO_BIG)
    try:
        sent = json.loads(body)
    except (ValueError, RecursionError):  # bad text, or brackets nested past the parser's depth
        return message(400, NOT_JSON)
    text = sent.get("question") if isinstance(sent, dict) else None
    problem = question_problem(text, deps.limits)
    if problem:
        return message(400, problem)
    now = deps.clock()
    address = client_address(peer, forwarded_for, deps.trusted_hops)
    if not deps.limiter.allow(address, now):
        return message(429, TOO_MANY)
    if not on_topic(text):
        return declined(OFF_TOPIC)
    try:
        shown = deps.retrieve(text)
        worst = answer.worst_case_call(deps.system, user_message(shown, text))
        if not deps.spend.reserve(worst, now):
            return message(503, DAILY_FULL)
        # A failure after this point keeps the reservation. The model may already have been paid
        # for, and a reply that crashes the checker must not be a way to spend without limit.
        question = {"id": "web", "split": "web", "question": text}
        done = answer.respond(question, shown, deps.facts, deps.client, deps.system)
        actual = done.line["cost_usd"] if done.line else 0.0
        deps.spend.settle(worst, actual, now)
    except Exception:  # whatever went wrong, the visitor gets one fixed sentence
        log.exception("A question could not be answered")  # the trace stays in the server log
        return message(502, FAILED)
    return 200, view(done.checked.text)
