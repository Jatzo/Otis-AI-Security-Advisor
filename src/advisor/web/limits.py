"""What a visitor may send, and how much of the day's money one visitor or all of them may use.

The numbers are the plan's proposals (docs/red-team-plan.md) and are in one place so they can be
changed. The rate limiter keeps its state in memory, so it is per process: the demo runs as one
process, and the daily spend cap is the backstop if that ever changes.
"""

import re
import threading
from collections import deque
from dataclasses import dataclass

from advisor.generation.facts import FOLDED_NAMES, PLAIN_NAMES
from advisor.generation.reading import ANY_ID


@dataclass(frozen=True)
class Limits:
    per_minute: int = 5
    per_day: int = 60
    question_chars: int = 500
    body_bytes: int = 8 * 1024
    timeout_s: int = 60
    daily_spend_usd: float = 3.0
    addresses_kept: int = 10_000


DEFAULT = Limits()
MINUTE = 60
DAY = 24 * 60 * 60


class RateLimiter:
    """A sliding window per address. An address with no recent questions is forgotten, and the
    table is capped, so a flood of new addresses cannot grow it without end."""

    def __init__(self, limits: Limits = DEFAULT) -> None:
        self.limits = limits
        self.seen: dict[str, deque[float]] = {}
        self.lock = threading.Lock()  # a threaded server must not let two requests both pass

    def allow(self, address: str, now: float) -> bool:
        with self.lock:
            return self.check(address, now)

    def check(self, address: str, now: float) -> bool:
        times = self.seen.get(address)
        if times is None:
            if len(self.seen) >= self.limits.addresses_kept:
                self.forget_old(now)
            if len(self.seen) >= self.limits.addresses_kept:
                return False  # a table full of live addresses: refuse the new one, never grow
            times = self.seen[address] = deque()
        while times and now - times[0] >= DAY:
            times.popleft()
        in_minute = sum(1 for t in times if now - t < MINUTE)
        if in_minute >= self.limits.per_minute or len(times) >= self.limits.per_day:
            return False
        times.append(now)
        return True

    def forget_old(self, now: float) -> None:
        for address in [a for a, t in self.seen.items() if not t or now - t[-1] >= DAY]:
            del self.seen[address]


class SpendCap:
    """The day's model spend. A call reserves its worst case before it starts and settles to the
    real cost afterwards, so the cap holds even when a call runs long."""

    def __init__(self, limits: Limits = DEFAULT) -> None:
        self.cap = limits.daily_spend_usd
        self.day = None
        self.spent = 0.0
        self.lock = threading.Lock()

    def roll(self, now: float) -> None:
        today = int(now // DAY)
        if today != self.day:
            self.day, self.spent = today, 0.0

    def reserve(self, worst_case: float, now: float) -> bool:
        with self.lock:
            self.roll(now)
            if self.spent + worst_case > self.cap:
                return False
            self.spent += worst_case
            return True

    def settle(self, worst_case: float, actual: float, now: float) -> None:
        with self.lock:
            self.roll(now)
            self.spent += actual - worst_case


def question_problem(text: object, limits: Limits = DEFAULT) -> str | None:
    """Says what is wrong with a question, or None. The text is the visitor's own, so it is
    judged by length and by control characters only."""
    if not isinstance(text, str) or not text.strip():
        return "Type a question about an advisory or a package."
    if len(text) > limits.question_chars:
        return f"Keep the question under {limits.question_chars} characters."
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        return "The question has characters that cannot be read."
    return None


def names_package(text: str) -> bool:
    lowered = text.lower()
    return any(
        re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w-])", lowered)
        for name in (*PLAIN_NAMES, *FOLDED_NAMES)
    )


def on_topic(text: str) -> bool:
    """Whether a question names an advisory, a CVE or one of the 18 packages. It stops a visitor
    using Otis as a free chat model before any money is spent. It is a cost control and not a
    security one: a question that mentions a package and asks for something else gets through,
    and the checker and the page are what keep such a reply harmless."""
    return bool(ANY_ID.search(text)) or names_package(text)


def client_address(peer: str, forwarded_for: str | None, trusted_hops: int = 0) -> str:
    """The address to rate-limit. With no trusted proxy it is the connection's own address and the
    header is ignored, so a visitor cannot pick their own. Behind a proxy we run, trusted_hops is
    how many proxies add to the header, and the address is the entry the nearest one added,
    counted from the right, because the entries on the left are whatever the visitor sent."""
    if trusted_hops <= 0 or not forwarded_for:
        return peer
    entries = [part.strip() for part in forwarded_for.split(",") if part.strip()]
    if len(entries) < trusted_hops:
        return peer
    return entries[-trusted_hops]
