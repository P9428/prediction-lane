from __future__ import annotations

import sqlite3

from pl import store


def game(league, event_id, start, completed=1, hs=3.0, as_=1.0):
    return dict(league=league, event_id=event_id, start=start, season=2026, season_type=2, status="STATUS_FINAL",
                completed=completed, neutral=0, home_id="1", home_abbr="H", home_score=hs if completed else None,
                away_id="2", away_abbr="A", away_score=as_ if completed else None, fetched_at="2026-10-01T00:00:00+00:00")


def test_games_filters_by_league_with_bound_parameters(tmp_path):
    db = tmp_path / "pl.sqlite"
    c = store.connect(db)
    with c:
        store.upsert(c, "games", store.GAME_COLS, [game("mlb", "1", "2026-05-01T00:00:00Z"), game("mlb", "2", "2026-04-01T00:00:00Z"),
                                                   game("nfl", "3", "2026-09-01T00:00:00Z"), game("mlb", "4", "2026-06-01T00:00:00Z", completed=0)])
        store.upsert(c, "odds", store.ODDS_COLS, [dict(league="mlb", event_id="1", provider="DK", ml_home=-120.0, ml_away=100.0, fetched_at="t")])
    c.close()
    df = store.games("mlb", path=db)
    assert list(df.event_id) == ["2", "1"]                     # sorted by start, incomplete excluded
    assert df.loc[df.event_id == "1", "ml_home"].item() == -120.0 and df.loc[df.event_id == "2", "ml_home"].isna().item()
    assert str(df.start.dt.tz) == "UTC"
    assert len(store.games(path=db)) == 3 and len(store.games(completed_only=False, path=db)) == 4
    assert store.games("mlb' OR '1'='1", path=db).empty     # a value, never SQL


def test_open_db_applies_schema_and_wal_choice(tmp_path):
    c = store.open_db(tmp_path / "a" / "x.sqlite", "CREATE TABLE IF NOT EXISTS t (k TEXT PRIMARY KEY);")
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c.close()
    c = store.open_db(tmp_path / "y.sqlite", wal=False)
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    c.close()


def test_upsert_replaces_on_primary_key_and_scalar_reads(tmp_path):
    db = tmp_path / "pl.sqlite"
    c = store.connect(db)
    with c:
        store.upsert(c, "games", store.GAME_COLS, [game("mlb", "1", "2026-05-01T00:00:00Z", hs=1.0)])
        store.upsert(c, "games", store.GAME_COLS, [game("mlb", "1", "2026-05-01T00:00:00Z", hs=9.0)])
        store.upsert(c, "games", store.GAME_COLS, [])
    c.close()
    assert store.scalar(db, "SELECT count(*) FROM games") == 1
    assert store.scalar(db, "SELECT home_score FROM games WHERE event_id=?", "1") == 9.0
    with sqlite3.connect(db) as c2:
        assert c2.execute("SELECT count(*) FROM pulls").fetchone()[0] == 0
