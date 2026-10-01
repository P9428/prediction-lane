"""Every other free source that answered the 2026-10-01 probe, pulled raw into
data/raw/<source>/ with a sha256 manifest. Nothing is parsed here; the manifest
is the evidence that the bytes exist and when they were taken.

usage: python -m pl.sources [name ...]   (default: all)
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.jsonl"

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"

TODAY = date.today().isoformat()

SOURCES: dict[str, list[tuple[str, str]]] = {
    # (published path under data/raw/<name>/, url)
    "nflverse": [("games.csv", "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv")],
    "football_data": [("E0_2526.csv", "https://www.football-data.co.uk/mmz4281/2526/E0.csv"),
                      ("E0_2425.csv", "https://www.football-data.co.uk/mmz4281/2425/E0.csv"),
                      ("E0_2324.csv", "https://www.football-data.co.uk/mmz4281/2324/E0.csv"),
                      ("D1_2526.csv", "https://www.football-data.co.uk/mmz4281/2526/D1.csv"),
                      ("SP1_2526.csv", "https://www.football-data.co.uk/mmz4281/2526/SP1.csv"),
                      ("I1_2526.csv", "https://www.football-data.co.uk/mmz4281/2526/I1.csv"),
                      ("USA.csv", "https://www.football-data.co.uk/new/USA.csv"),
                      ("fixtures.csv", "https://www.football-data.co.uk/fixtures.csv")],
    "fivethirtyeight": [("nbaallelo.csv", "https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv"),
                        ("nba_elo.csv", "https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-forecasts/nba_elo.csv"),
                        ("nfl_elo.csv", "https://raw.githubusercontent.com/fivethirtyeight/data/master/nfl-elo/nfl_elo.csv"),
                        ("mlb_elo.csv", "https://raw.githubusercontent.com/fivethirtyeight/data/master/mlb-elo/mlb_elo.csv")],
    "moneypuck": [("teams_2025.csv", "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/teams.csv"),
                  ("goalies_2025.csv", "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/goalies.csv"),
                  ("teams_2024.csv", "https://moneypuck.com/moneypuck/playerData/seasonSummary/2024/regular/teams.csv"),
                  ("goalies_2024.csv", "https://moneypuck.com/moneypuck/playerData/seasonSummary/2024/regular/goalies.csv")],
    "baseball_savant": [("pitchers_2026.csv", "https://baseballsavant.mlb.com/leaderboard/statcast?type=pitcher&year=2026&position=&team=&min=q&csv=true"),
                        ("batters_2026.csv", "https://baseballsavant.mlb.com/leaderboard/statcast?type=batter&year=2026&position=&team=&min=q&csv=true")],
    "retrosheet": [("gl2024.zip", "https://www.retrosheet.org/gamelogs/gl2024.zip"),
                   ("gl2025.zip", "https://www.retrosheet.org/gamelogs/gl2025.zip")],
    "mlb_statsapi": [(f"schedule_{y}.json", f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate={y}-03-15&endDate={y}-11-10&gameType=R,F,D,L,W&hydrate=probablePitcher,decisions,linescore,weather,officials,venue")
                     for y in (2024, 2025, 2026)] +
                    [(f"schedule_today_{TODAY}.json", f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={TODAY}&hydrate=probablePitcher,lineups,weather,officials,venue")],
    "nhl_api": [(f"schedule_{TODAY}.json", f"https://api-web.nhle.com/v1/schedule/{TODAY}"),
                ("standings_now.json", "https://api-web.nhle.com/v1/standings/now"),
                ("goalies_2025.json", "https://api.nhle.com/stats/rest/en/goalie/summary?limit=200&cayenneExp=seasonId=20252026"),
                ("teams_2025.json", "https://api.nhle.com/stats/rest/en/team/summary?limit=50&cayenneExp=seasonId=20252026")],
    "kalshi": [("series_sports.json", "https://api.elections.kalshi.com/trade-api/v2/series?category=Sports&limit=200"),
               ("markets_mlb.json", "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open&series_ticker=KXMLBGAME"),
               ("markets_nfl.json", "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open&series_ticker=KXNFLGAME"),
               ("markets_nhl.json", "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open&series_ticker=KXNHLGAME"),
               ("markets_nba.json", "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open&series_ticker=KXNBAGAME"),
               ("trades_recent.json", "https://api.elections.kalshi.com/trade-api/v2/markets/trades?limit=1000")],
    "polymarket": [("sports_tags.json", "https://gamma-api.polymarket.com/sports"),
                   ("events_mlb.json", "https://gamma-api.polymarket.com/events?limit=100&closed=false&tag_slug=mlb"),
                   ("events_nhl.json", "https://gamma-api.polymarket.com/events?limit=100&closed=false&tag_slug=nhl"),
                   ("events_nfl.json", "https://gamma-api.polymarket.com/events?limit=100&closed=false&tag_slug=nfl"),
                   ("events_nba.json", "https://gamma-api.polymarket.com/events?limit=100&closed=false&tag_slug=nba")],
    "espn_injuries": [(f"{lg}_{TODAY}.json", f"https://site.api.espn.com/apis/site/v2/sports/{sp}/{lg}/injuries")
                      for sp, lg in (("baseball", "mlb"), ("football", "nfl"), ("basketball", "nba"), ("hockey", "nhl"))],
    "pinnacle_guest": [("sports.json", "https://guest.api.arcadia.pinnacle.com/0.1/sports")],
    "actionnetwork": [(f"mlb_{TODAY}.json", "https://api.actionnetwork.com/web/v1/scoreboard/mlb?period=game"),
                      (f"nfl_{TODAY}.json", "https://api.actionnetwork.com/web/v1/scoreboard/nfl?period=game"),
                      (f"nhl_{TODAY}.json", "https://api.actionnetwork.com/web/v1/scoreboard/nhl?period=game")],
    "open_meteo": [(f"truist_park_{TODAY}.json", "https://api.open-meteo.com/v1/forecast?latitude=33.89&longitude=-84.47&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,precipitation_probability&forecast_days=2&timezone=America%2FNew_York")],
}


def fetch(name: str, fname: str, url: str) -> dict:
    d = RAW / name
    d.mkdir(parents=True, exist_ok=True)
    t = time.time()
    r = s.get(url, timeout=120)
    body = r.content
    (d / fname).write_bytes(body)
    row = dict(source=name, file=fname, url=url, status=r.status_code, nbytes=len(body),
               sha256=hashlib.sha256(body).hexdigest(), secs=round(time.time() - t, 1),
               fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with open(MANIFEST, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(f"  {name}/{fname} {r.status_code} {len(body):,}B {row['secs']}s", flush=True)
    return row


def main(argv=None):
    names = (argv or sys.argv[1:]) or list(SOURCES)
    for n in names:
        for fname, url in SOURCES[n]:
            try:
                fetch(n, fname, url)
            except Exception as e:  # noqa: BLE001
                print(f"  {n}/{fname} ERR {e}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
