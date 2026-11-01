"""One small JSON-over-HTTPS client, so every fetcher retries and times out the same way."""

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

USER_AGENT = "otis-ai-security-advisor/0.1 (+https://github.com/Jatzo/Otis-AI-Security-Advisor)"
# Rate limits and brief outages answer with these; anything else is a real error.
RETRY_STATUSES = {403, 429, 500, 502, 503, 504}

GetJson = Callable[..., Any]


def get_json(
    url: str,
    *,
    body: dict | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 5,
    timeout: float = 60,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """GET, or POST when a body is given, and return the decoded JSON.

    Retries with a growing wait on rate limits and server errors, then raises.
    """
    data = json.dumps(body).encode() if body is not None else None
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=data, headers=request_headers)  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in RETRY_STATUSES or attempt == attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts:
                raise
        sleep(min(60, 5 * 2 ** (attempt - 1)))
    raise AssertionError("unreachable")
