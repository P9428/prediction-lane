from __future__ import annotations

import pytest
import requests

from pl import http


class FakeResponse:
    def __init__(self, status: int, payload=None, text: str = ""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def script(monkeypatch, *responses):
    """session.get returns the scripted responses in order; raising entries are raised."""
    calls = []
    it = iter(responses)

    def get(url, params=None, timeout=None, **kw):
        calls.append((url, params))
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(http._session, "get", get)
    return calls


def test_200_returns_json_without_sleeping(monkeypatch, no_sleep):
    script(monkeypatch, FakeResponse(200, {"ok": 1}))
    assert http.get_json("u") == {"ok": 1}
    assert no_sleep == []


def test_5xx_then_200_retries_with_linear_backoff(monkeypatch, no_sleep):
    calls = script(monkeypatch, FakeResponse(503), FakeResponse(503), FakeResponse(200, [1]))
    assert http.get_json("u", backoff=0.5) == [1]
    assert len(calls) == 3 and no_sleep == [0.5, 1.0]


def test_fatal_status_raises_immediately(monkeypatch, no_sleep):
    calls = script(monkeypatch, FakeResponse(404, text="nope"))
    with pytest.raises(http.HttpError) as ei:
        http.get_json("u")
    assert ei.value.status == 404 and "nope" in str(ei.value) and len(calls) == 1 and no_sleep == []


def test_429_uses_rate_limit_backoff(monkeypatch, no_sleep):
    script(monkeypatch, FakeResponse(429), FakeResponse(200, {}))
    assert http.get_json("u", fatal=(), rate_limit_backoff=3.0) == {}
    assert no_sleep == [3.0]


def test_exhausted_retries_raise_last_error(monkeypatch, no_sleep):
    script(monkeypatch, requests.ConnectionError("down"), FakeResponse(500), FakeResponse(200, ValueError("bad json")))
    with pytest.raises(ValueError, match="bad json"):
        http.get_json("u", tries=3)
    assert len(no_sleep) == 3


def test_http_error_is_a_runtime_error():
    assert issubclass(http.HttpError, RuntimeError)
