"""Retries: rate limits and server errors are retried, anything else fails at once."""

import io
import urllib.error

import pytest

from advisor.ingest import http


def http_error(code):
    return urllib.error.HTTPError("https://example.invalid", code, "error", {}, None)


def stand_in_urlopen(responses, calls):
    def urlopen(request, timeout):
        calls.append(request.full_url)
        outcome = responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return io.BytesIO(outcome)

    return urlopen


def test_a_rate_limit_is_retried_and_the_later_answer_returned(monkeypatch):
    calls, waits = [], []
    responses = [http_error(429), b'{"ok": true}']
    monkeypatch.setattr(http.urllib.request, "urlopen", stand_in_urlopen(responses, calls))

    result = http.get_json("https://example.invalid", sleep=waits.append)

    assert result == {"ok": True}
    assert len(calls) == 2
    assert waits == [5]


def test_a_not_found_fails_at_once_without_retrying(monkeypatch):
    calls, waits = [], []
    monkeypatch.setattr(http.urllib.request, "urlopen", stand_in_urlopen([http_error(404)], calls))

    with pytest.raises(urllib.error.HTTPError):
        http.get_json("https://example.invalid", sleep=waits.append)

    assert len(calls) == 1
    assert waits == []


def test_a_server_that_keeps_failing_raises_after_the_last_attempt(monkeypatch):
    calls, waits = [], []
    responses = [http_error(503)] * 3
    monkeypatch.setattr(http.urllib.request, "urlopen", stand_in_urlopen(responses, calls))

    with pytest.raises(urllib.error.HTTPError):
        http.get_json("https://example.invalid", attempts=3, sleep=waits.append)

    assert len(calls) == 3
    assert waits == [5, 10]
