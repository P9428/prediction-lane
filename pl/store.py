"""SQLite store: one row per game, benchmark odds joined by event_id."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "pl.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
  league TEXT NOT NULL, event_id TEXT NOT NULL, start TEXT, season INTEGER, season_type INTEGER,
  status TEXT, completed INTEGER, neutral INTEGER,
  home_id TEXT, home_abbr TEXT, home_score REAL, home_prob_id TEXT, home_prob_name TEXT,
  away_id TEXT, away_abbr TEXT, away_score REAL, away_prob_id TEXT, away_prob_name TEXT,
  live_provider TEXT, live_spread_home REAL, live_total REAL, live_ml_home REAL, live_ml_away REAL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (league, event_id));
CREATE TABLE IF NOT EXISTS odds (
  league TEXT NOT NULL, event_id TEXT NOT NULL, provider TEXT, provider_id TEXT,
  ml_home REAL, ml_away REAL, ml_home_open REAL, ml_away_open REAL,
  spread_home REAL, spread_home_open REAL, total REAL, total_open REAL, n_providers INTEGER,
  raw TEXT, fetched_at TEXT NOT NULL,
  PRIMARY KEY (league, event_id));
CREATE TABLE IF NOT EXISTS pulls (league TEXT NOT NULL, day TEXT NOT NULL, n INTEGER, fetched_at TEXT NOT NULL,
  PRIMARY KEY (league, day));
"""

GAME_COLS = ["league", "event_id", "start", "season", "season_type", "status", "completed", "neutral",
             "home_id", "home_abbr", "home_score", "home_prob_id", "home_prob_name",
             "away_id", "away_abbr", "away_score", "away_prob_id", "away_prob_name",
             "live_provider", "live_spread_home", "live_total", "live_ml_home", "live_ml_away", "fetched_at"]
ODDS_COLS = ["league", "event_id", "provider", "provider_id", "ml_home", "ml_away", "ml_home_open", "ml_away_open",
             "spread_home", "spread_home_open", "total", "total_open", "n_providers", "raw", "fetched_at"]


def connect(path: Path = DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(path, timeout=120)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(SCHEMA)
    return c


def upsert(c: sqlite3.Connection, table: str, cols: list[str], rows: list[dict]) -> None:
    if not rows:
        return
    marks = ",".join(["?"] * len(cols))
    q = f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({marks})"
    c.executemany(q, [tuple(r.get(k) for k in cols) for r in rows])


def games(league: str | None = None, completed_only: bool = True, path: Path = DB) -> pd.DataFrame:
    c = connect(path)
    q = """SELECT g.*, o.provider, o.ml_home, o.ml_away, o.ml_home_open, o.ml_away_open,
                  o.spread_home, o.spread_home_open, o.total, o.total_open
           FROM games g LEFT JOIN odds o ON g.league = o.league AND g.event_id = o.event_id"""
    w = []
    if league:
        w.append(f"g.league = '{league}'")
    if completed_only:
        w.append("g.completed = 1 AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL")
    if w:
        q += " WHERE " + " AND ".join(w)
    df = pd.read_sql(q, c)
    c.close()
    df["start"] = pd.to_datetime(df["start"], utc=True)
    return df.sort_values(["start", "event_id"]).reset_index(drop=True)
