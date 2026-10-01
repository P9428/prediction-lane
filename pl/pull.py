"""Walk ESPN history into the store. Idempotent per (league, day); odds fetched
once per settled game, in parallel.

usage: python -m pl.pull <league> <YYYY-MM-DD> <YYYY-MM-DD> [--odds] [--workers N]
       python -m pl.pull nfl --weeks 2023 2024 2025 2026 [--odds]
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

from pl import espn, store


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pull_days(league: str, a: date, b: date, force: bool = False) -> int:
    c = store.connect()
    have = {d for (d,) in c.execute("SELECT day FROM pulls WHERE league=?", (league,))}
    n_tot = 0
    for d in espn.daterange(a, b):
        key = d.isoformat()
        if key in have and not force:
            continue
        try:
            rows = [espn.parse_event(league, e) for e in espn.scoreboard(league, d)]
        except Exception as e:  # noqa: BLE001 - a 5xx day is retried on the next run, never recorded as pulled
            print(f"  {league} {key} FAILED {e}", file=sys.stderr, flush=True)
            continue
        for r in rows:
            r["fetched_at"] = _now()
        with c:
            store.upsert(c, "games", store.GAME_COLS, rows)
            c.execute("INSERT OR REPLACE INTO pulls VALUES (?,?,?,?)", (league, key, len(rows), _now()))
        n_tot += len(rows)
        print(f"  {league} {key} {len(rows)}", flush=True)
    c.close()
    return n_tot


def pull_nfl_weeks(seasons: list[int], force: bool = False) -> int:
    c = store.connect()
    have = {d for (d,) in c.execute("SELECT day FROM pulls WHERE league='nfl'")}
    n_tot = 0
    for season in seasons:
        for stype, weeks in ((2, range(1, 19)), (3, range(1, 6))):
            for wk in weeks:
                key = f"{season}-t{stype}-w{wk:02d}"
                if key in have and not force:
                    continue
                try:
                    evs = espn.scoreboard("nfl", None, dates=season, seasontype=stype, week=wk)
                except RuntimeError:
                    evs = []
                rows = [espn.parse_event("nfl", e) for e in evs]
                for r in rows:
                    r["fetched_at"] = _now()
                with c:
                    store.upsert(c, "games", store.GAME_COLS, rows)
                    c.execute("INSERT OR REPLACE INTO pulls VALUES (?,?,?,?)", ("nfl", key, len(rows), _now()))
                n_tot += len(rows)
                print(f"  nfl {key} {len(rows)}", flush=True)
    c.close()
    return n_tot


def pull_odds(league: str, workers: int = 6) -> int:
    c = store.connect()
    todo = [eid for (eid,) in c.execute(
        """SELECT g.event_id FROM games g LEFT JOIN odds o ON g.league=o.league AND g.event_id=o.event_id
           WHERE g.league=? AND g.completed=1 AND o.event_id IS NULL""", (league,))]
    print(f"{league}: {len(todo)} games need odds", flush=True)
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(espn.odds_history, league, eid): eid for eid in todo}
        batch: list[dict] = []
        for f in as_completed(futs):
            eid = futs[f]
            try:
                o = f.result()
            except Exception as e:  # noqa: BLE001 - one bad game must not stop the walk
                print(f"  odds error {eid}: {e}", file=sys.stderr, flush=True)
                o = {}
            batch.append(dict(o, league=league, event_id=eid, fetched_at=_now()))
            done += 1
            if len(batch) >= 50:
                with c:
                    store.upsert(c, "odds", store.ODDS_COLS, batch)
                batch.clear()
                print(f"  {league} odds {done}/{len(todo)}  {time.time() - t0:.0f}s", flush=True)
        if batch:
            with c:
                store.upsert(c, "odds", store.ODDS_COLS, batch)
    c.close()
    return done


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("league")
    ap.add_argument("start", nargs="?")
    ap.add_argument("end", nargs="?")
    ap.add_argument("--weeks", nargs="*", type=int)
    ap.add_argument("--odds", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.weeks:
        pull_nfl_weeks(a.weeks, a.force)
    elif a.start:
        pull_days(a.league, date.fromisoformat(a.start), date.fromisoformat(a.end), a.force)
    if a.odds:
        pull_odds(a.league, a.workers)


if __name__ == "__main__":
    main()
