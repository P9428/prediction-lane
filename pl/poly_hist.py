"""Polymarket closed moneyline markets + hourly price history -> data/poly_hist.sqlite.

Gamma lists closed events by sport tag; the CLOB prices-history endpoint returns the
outcome-0 token's hourly mid (fidelity=60) for the market's whole life. No bid/ask in
history, so the lag test uses mid plus the half-spread measured live today (0.005-0.01
on these markets).

usage: python -m pl.poly_hist [mlb nfl nhl nba]
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
DB = ROOT / "data" / "poly_hist.sqlite"
_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 prediction-lane/0.1"

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (condition_id TEXT PRIMARY KEY, league TEXT, event_title TEXT, question TEXT,
  outcomes TEXT, prices TEXT, token0 TEXT, token1 TEXT, game_start TEXT, end_date TEXT, volume REAL, liquidity REAL,
  resolved_outcome TEXT, raw TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS prices (token TEXT, ts INTEGER, p REAL, PRIMARY KEY (token, ts));
CREATE TABLE IF NOT EXISTS price_pulls (token TEXT PRIMARY KEY, n INTEGER, fetched_at TEXT);
"""


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
            last = RuntimeError(f"{r.status_code} {r.text[:100]}")
        except requests.RequestException as e:
            last = e
        time.sleep(0.7 * (i + 1))
    raise last


def pull_markets(c: sqlite3.Connection, league: str, year: str = "2026") -> int:
    """Weekly start-date windows: the events endpoint caps offset pagination at 1000,
    and ordering by event startDate mixes futures in, so the walk is by window."""
    from datetime import date, timedelta
    n = 0
    d0 = date(int(year), 3, 15)
    while d0 < date.today() + timedelta(days=2):
        d1 = d0 + timedelta(days=7)
        for off in range(0, 1000, 100):
            try:
                evs = get("https://gamma-api.polymarket.com/events", dict(limit=100, offset=off, closed="true", tag_slug=league,
                                                                           start_date_min=d0.isoformat(), start_date_max=d1.isoformat()))
            except RuntimeError as e:
                print(f"  {league} {d0} offset {off}: {e}", flush=True)
                break
            if not evs:
                break
            rows = []
            for e in evs:
                for m in e.get("markets", []):
                    gs = m.get("gameStartTime") or ""
                    if m.get("sportsMarketType") != "moneyline" or not gs.startswith(year):
                        continue
                    toks = json.loads(m.get("clobTokenIds") or "[]")
                    if len(toks) != 2:
                        continue
                    prices = json.loads(m.get("outcomePrices") or "[]")
                    rows.append((m.get("conditionId"), league, e.get("title"), m.get("question"), m.get("outcomes"), m.get("outcomePrices"),
                                 toks[0], toks[1], gs, m.get("endDate"), _f(m.get("volumeNum")), _f(m.get("liquidityNum")),
                                 (json.loads(m.get("outcomes"))[int(float(prices[1]) > float(prices[0]))] if len(prices) == 2 else None),
                                 json.dumps({k: m.get(k) for k in ("id", "slug", "closed", "umaResolutionStatus", "startDate", "endDate")}),
                                 datetime.now(timezone.utc).isoformat(timespec="seconds")))
            with c:
                c.executemany("INSERT OR REPLACE INTO markets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            n += len(rows)
            if len(evs) < 100:
                break
        print(f"  {league} week {d0}: total {n}", flush=True)
        d0 = d1
    return n


def history(token: str) -> list[tuple]:
    j = get("https://clob.polymarket.com/prices-history", dict(market=token, interval="max", fidelity=60))
    return [(token, int(x["t"]), float(x["p"])) for x in j.get("history", [])]


def pull_prices(c: sqlite3.Connection, league: str, workers: int = 4) -> int:
    todo = [t for (t,) in c.execute("""SELECT m.token0 FROM markets m LEFT JOIN price_pulls p ON m.token0 = p.token
                                        WHERE m.league = ? AND p.token IS NULL""", (league,))]
    print(f"{league}: {len(todo)} tokens need history", flush=True)
    done, t0 = 0, time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(history, t): t for t in todo}
        for f in as_completed(futs):
            t = futs[f]
            try:
                rows = f.result()
            except Exception as e:  # noqa: BLE001
                print(f"  {t[:12]} ERR {e}", file=sys.stderr, flush=True)
                continue
            with c:
                c.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?)", rows)
                c.execute("INSERT OR REPLACE INTO price_pulls VALUES (?,?,?)", (t, len(rows), datetime.now(timezone.utc).isoformat(timespec="seconds")))
            done += 1
            if done % 200 == 0:
                print(f"  {league} history {done}/{len(todo)} {time.time() - t0:.0f}s", flush=True)
    return done


def main(argv=None):
    leagues = (argv or sys.argv[1:]) or ["mlb", "nfl"]
    c = sqlite3.connect(DB, timeout=120)
    c.executescript(SCHEMA)
    for lg in leagues:
        print(f"{lg}: {pull_markets(c, lg)} moneyline markets", flush=True)
        pull_prices(c, lg)
    c.close()


if __name__ == "__main__":
    main()
