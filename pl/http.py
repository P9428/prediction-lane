"""One HTTP session, one retry policy. Callers say which statuses are fatal
(no retry) and how long to back off; nothing else about transport lives
outside this module."""
from __future__ import annotations

import time
from typing import Any

import requests

from pl.core import log

UA = "Mozilla/5.0 prediction-lane/0.1"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"

_session = requests.Session()
_session.headers["User-Agent"] = UA


class HttpError(RuntimeError):
    """Non-200 answer. `status` lets callers branch without parsing the message."""

    def __init__(self, status: int, url: str, body: str = "") -> None:
        self.status, self.url, self.body = status, url, body
        super().__init__(f"{status} {url}" + (f" {body}" if body else ""))


def session() -> requests.Session:
    return _session


def fetch(url: str, *, timeout: float = 120, browser: bool = False, stream: bool = False,
          headers: dict[str, str] | None = None) -> requests.Response:
    """Raw response, no retry, for byte captures and probes."""
    h = dict(headers or {})
    if browser:
        h.setdefault("User-Agent", BROWSER_UA)
    return _session.get(url, timeout=timeout, stream=stream, headers=h or None)


def get_json(url: str, params: dict | None = None, *, timeout: float = 30, tries: int = 4, backoff: float = 0.8,
             fatal: tuple[int, ...] = (400, 404), rate_limit_backoff: float = 3.0) -> Any:
    """GET with linear back-off. A status in `fatal` raises at once; 429 waits
    `rate_limit_backoff * attempt`; anything else (5xx, timeouts, bad JSON) is
    retried `tries` times and the last error is raised."""
    last: Exception | None = None
    for i in range(tries):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = HttpError(r.status_code, url, r.text[:120])
            if r.status_code in fatal:
                raise last
            if r.status_code == 429:
                log.debug("429 %s, attempt %d", url, i + 1)
                time.sleep(rate_limit_backoff * (i + 1))
                continue
        except (requests.RequestException, ValueError) as e:
            last = e
        time.sleep(backoff * (i + 1))
    assert last is not None
    raise last
