"""Kalshi settled game markets + hourly candlesticks -> data/kalshi_hist.sqlite.

usage: python -m pl.kalshi_hist [KXMLBGAME KXNFLGAME ...]
Idempotent: markets already holding candles are skipped.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "kalshi_hist.sqlite"
B = "https://api.elections.kalshi.com/trade-api/v2"
_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 prediction-lane/0.1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (ticker TEXT PRIMARY KEY, series TEXT, event_ticker TEXT, title TEXT, sub TEXT,
  open_time TEXT, close_time TEXT, expected_expiration_time TEXT, result TEXT, volume REAL, raw TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS candles (ticker TEXT, end_ts INTEGER, bid REAL, ask REAL, price_close REAL, price_mean REAL,
  volume REAL, oi REAL, PRIMARY KEY (ticker, end_ts));
CREATE TABLE IF NOT EXISTS candle_pulls (ticker TEXT PRIMARY KEY, n INTEGER, fetched_at TEXT);
"""


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def get(url, params, tries=4):
    last = None
    for i in range(tries):
        try:
            r = _s.get(url, params=params, timeout=60)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2.0 * (i + 1))
                continue
            last = RuntimeError(f"{r.status_code} {r.text[:120]}")
        except requests.RequestException as e:
            last = e
        time.sleep(0.5 * (i + 1))
    raise last


def pull_markets(c: sqlite3.Connection, series: str) -> int:
    n, cur = 0, ""
    while True:
        j = get(f"{B}/markets", dict(limit=1000, status="settled", series_ticker=series, cursor=cur))
        ms = j.get("markets", [])
        rows = [(m["ticker"], series, m.get("event_ticker"), m.get("title"), m.get("yes_sub_title"), m.get("open_time"),
                 m.get("close_time"), m.get("expected_expiration_time"), m.get("result"), _f(m.get("volume_fp")),
                 json.dumps(m, separators=(",", ":")), datetime.now(timezone.utc).isoformat(timespec="seconds")) for m in ms]
        with c:
            c.executemany("INSERT OR REPLACE INTO markets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        n += len(ms)
        cur = j.get("cursor") or ""
        if not cur:
            break
    return n


def candles(series: str, ticker: str, open_time: str, close_time: str) -> list[tuple]:
    j = get(f"{B}/series/{series}/markets/{ticker}/candlesticks",
            dict(start_ts=_ts(open_time) - 3600, end_ts=_ts(close_time) + 3600, period_interval=60))
    out = []
    for x in j.get("candlesticks", []):
        p = x.get("price") or {}
        out.append((ticker, int(x["end_period_ts"]), _f((x.get("yes_bid") or {}).get("close_dollars")),
                    _f((x.get("yes_ask") or {}).get("close_dollars")), _f(p.get("close_dollars")), _f(p.get("mean_dollars")),
                    _f(x.get("volume_fp")), _f(x.get("open_interest_fp"))))
    return out


def pull_candles(c: sqlite3.Connection, series: str, workers: int = 4) -> int:
    todo = c.execute("""SELECT m.ticker, m.open_time, m.close_time FROM markets m LEFT JOIN candle_pulls p ON m.ticker = p.ticker
                        WHERE m.series = ? AND p.ticker IS NULL""", (series,)).fetchall()
    print(f"{series}: {len(todo)} markets need candles", flush=True)
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(candles, series, tk, o, cl): tk for tk, o, cl in todo}
        for f in as_completed(futs):
            tk = futs[f]
            try:
                rows = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  {tk} ERR {e}", file=sys.stderr, flush=True)
                continue
            with c:
                c.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)", rows)
                c.execute("INSERT OR REPLACE INTO candle_pulls VALUES (?,?,?)", (tk, len(rows), datetime.now(timezone.utc).isoformat(timespec="seconds")))
            done += 1
            if done % 100 == 0:
                print(f"  {series} candles {done}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    return done


def main(argv=None):
    series = (argv or sys.argv[1:]) or ["KXMLBGAME", "KXNFLGAME"]
    c = sqlite3.connect(DB, timeout=120)
    c.executescript(SCHEMA)
    for s in series:
        n = pull_markets(c, s)
        print(f"{s}: {n} settled markets", flush=True)
        pull_candles(c, s)
    c.close()


if __name__ == "__main__":
    main()
