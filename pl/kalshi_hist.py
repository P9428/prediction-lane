"""Kalshi settled game markets + hourly candlesticks -> data/kalshi_hist.sqlite.

usage: python -m pl.kalshi_hist [KXMLBGAME KXNFLGAME ...]
Idempotent: markets already holding candles are skipped.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from pl import http, store
from pl.core import DATA, configure_logging, epoch, log, to_float, utc_now

DB = DATA / "kalshi_hist.sqlite"
B = "https://api.elections.kalshi.com/trade-api/v2"

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (ticker TEXT PRIMARY KEY, series TEXT, event_ticker TEXT, title TEXT, sub TEXT,
  open_time TEXT, close_time TEXT, expected_expiration_time TEXT, result TEXT, volume REAL, raw TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS candles (ticker TEXT, end_ts INTEGER, bid REAL, ask REAL, price_close REAL, price_mean REAL,
  volume REAL, oi REAL, PRIMARY KEY (ticker, end_ts));
CREATE TABLE IF NOT EXISTS candle_pulls (ticker TEXT PRIMARY KEY, n INTEGER, fetched_at TEXT);
"""


def get(url: str, params: dict) -> dict:
    """Kalshi GET: every non-200 is retried, 429 with the long back-off."""
    return http.get_json(url, params, timeout=60, tries=4, backoff=0.5, fatal=())


def pull_markets(c: sqlite3.Connection, series: str) -> int:
    n, cur = 0, ""
    while True:
        j = get(f"{B}/markets", dict(limit=1000, status="settled", series_ticker=series, cursor=cur))
        ms = j.get("markets", [])
        rows = [(m["ticker"], series, m.get("event_ticker"), m.get("title"), m.get("yes_sub_title"), m.get("open_time"),
                 m.get("close_time"), m.get("expected_expiration_time"), m.get("result"), to_float(m.get("volume_fp")),
                 json.dumps(m, separators=(",", ":")), utc_now()) for m in ms]
        with c:
            c.executemany("INSERT OR REPLACE INTO markets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        n += len(ms)
        cur = j.get("cursor") or ""
        if not cur:
            break
    return n


def candles(series: str, ticker: str, open_time: str, close_time: str) -> list[tuple]:
    j = get(f"{B}/series/{series}/markets/{ticker}/candlesticks",
            dict(start_ts=epoch(open_time) - 3600, end_ts=epoch(close_time) + 3600, period_interval=60))
    out = []
    for x in j.get("candlesticks", []):
        p = x.get("price") or {}
        out.append((ticker, int(x["end_period_ts"]), to_float((x.get("yes_bid") or {}).get("close_dollars")),
                    to_float((x.get("yes_ask") or {}).get("close_dollars")), to_float(p.get("close_dollars")), to_float(p.get("mean_dollars")),
                    to_float(x.get("volume_fp")), to_float(x.get("open_interest_fp"))))
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
                log.warning("%s: %s", tk, e)
                continue
            with c:
                c.executemany("INSERT OR REPLACE INTO candles VALUES (?,?,?,?,?,?,?,?)", rows)
                c.execute("INSERT OR REPLACE INTO candle_pulls VALUES (?,?,?)", (tk, len(rows), utc_now()))
            done += 1
            if done % 100 == 0:
                print(f"  {series} candles {done}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    return done


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    ap = argparse.ArgumentParser(prog="pl kalshi-hist", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("series", nargs="*", default=["KXMLBGAME", "KXNFLGAME"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    c = store.open_db(DB, SCHEMA, wal=False)
    try:
        for ser in a.series:
            print(f"{ser}: {pull_markets(c, ser)} settled markets", flush=True)
            pull_candles(c, ser, a.workers)
    finally:
        c.close()


if __name__ == "__main__":
    main()
