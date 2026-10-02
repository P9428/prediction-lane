"""Every other free source that answered the 2026-10-01 probe, pulled raw into
data/raw/<source>/ with a sha256 manifest. Nothing is parsed here; the manifest
is the evidence that the bytes exist and when they were taken.

  python -m pl sources [name ...]   (default: all)
  python -m pl sources --doc        render docs/SOURCES.md from data/probe_sources.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import date

from pl import http
from pl.core import DATA, DOCS, configure_logging, load_json, log, utc_now, write_text

RAW = DATA / "raw"
MANIFEST = RAW / "manifest.jsonl"
PROBE_JSON = DATA / "probe_sources.json"

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

# what each probed source gives; keys are the probe names in data/probe_sources.json
NOTES = {
    "mlb_statsapi_schedule": "MLB Stats API: schedule, probable pitchers, lineups, weather, umpires, venue; history to 1901. No key.",
    "mlb_statsapi_hist": "MLB Stats API: date-range schedule with decisions/linescore (one call per season).",
    "mlb_statsapi_pitcher_gamelog": "MLB Stats API: per-player game logs.",
    "mlb_statsapi_team_stats": "MLB Stats API: team season stats.",
    "nhl_api_schedule": "NHL api-web: schedule with gameType (1 pre / 2 reg / 3 post), goalies.",
    "nhl_api_score": "NHL api-web: scores by date.", "nhl_api_standings": "NHL api-web: standings by date.",
    "nhl_goalie_stats": "NHL stats REST: goalie summary by season.", "nhl_api_gamecenter": "NHL api-web: boxscore per game.",
    "nba_cdn_schedule": "NBA CDN schedule: Akamai 403 from this IP.", "nba_cdn_today": "NBA CDN live scoreboard: 403.",
    "nba_stats_api": "stats.nba.com: hangs for scripts.",
    "nflverse_games": "nflverse games.csv: every NFL game since 1999 with spread_line, total_line, moneylines, QBs, rest, roof, surface. The NFL benchmark file.",
    "nflverse_pbp_2025": "nflverse play-by-play (EPA) per season.",
    "538_nfl_elo": "FiveThirtyEight NFL Elo: repo path gone (404).", "538_mlb_elo": "FiveThirtyEight MLB Elo: 404.",
    "538_nba_elo": "FiveThirtyEight NBA Elo history 1946-2015.", "538_nba_latest": "538 NBA model page: HTML only, archived.",
    "football_data_epl_2526": "football-data.co.uk: results + closing odds incl. Pinnacle (PSCH/PSCD/PSCA), 20+ leagues since 1993.",
    "football_data_mls": "football-data.co.uk MLS file with Pinnacle closing odds.",
    "tennis_data_2026": "tennis-data.co.uk: Cloudflare 403 to scripts (browser download works).", "tennis_data_2025": "403.", "tennis_data_wta_2025": "403.",
    "sackmann_atp_2025": "Jeff Sackmann tennis_atp: 404 at that path; check current file names.", "sackmann_atp_2026": "404.",
    "clubelo": "clubelo.com API: 502 at probe time (transient).",
    "open_meteo_hist": "Open-Meteo archive: hourly historical weather by lat/lon, no key.", "open_meteo_fcst": "Open-Meteo forecast, no key.",
    "kalshi_series_sports": "Kalshi public API: all sports series.", "kalshi_markets_mlb": "Kalshi public: open MLB game markets with yes/no bid/ask in dollars, volume, OI.",
    "kalshi_markets_nfl": "Kalshi public: NFL game markets.", "kalshi_trades": "Kalshi public: exchange-wide trade tape (taker side, price, count).",
    "polymarket_gamma_sports_tags": "Polymarket Gamma: sport tags.", "polymarket_gamma_events_mlb": "Polymarket Gamma: MLB events with moneyline/spread/total markets, bestBid/bestAsk, token ids.",
    "polymarket_gamma_events_nhl": "Polymarket Gamma: NHL events.",
    "retrosheet_gl2024": "Retrosheet game logs: every MLB game since 1871 with starters, umpires, attendance.",
    "cfbd_no_key": "collegefootballdata.com: free key required (includes betting lines).",
    "massey_mlb": "Massey Ratings pages (HTML).", "manifold": "Manifold Markets API (play money).",
    "espn_injuries_mlb": "ESPN injuries by league.", "espn_injuries_nfl": "ESPN injuries.", "espn_injuries_nba": "ESPN injuries.", "espn_injuries_nhl": "ESPN injuries.",
    "espn_team_stats_mlb": "ESPN team statistics.", "espn_core_athlete_stats": "ESPN core athlete statistics: 404 for that id/season.",
    "espn_summary_mlb": "ESPN game summary: boxscore, starters, odds, weather, win probability.",
    "nba_injury_report": "Official NBA injury report page (PDF links).", "ufcstats": "ufcstats.com (HTML scrape possible).", "hltv": "HLTV results HTML.", "understat": "understat xG HTML with embedded JSON.",
    "balldontlie_nokey": "balldontlie: key required.", "sportsbookreview": "SBR odds HTML (Next.js payload).", "covers": "Covers matchups HTML (consensus).", "oddsportal": "OddsPortal HTML (heavy JS).",
    "hockey_reference": "Hockey-Reference answers 200 but its terms forbid automated scraping; not used.",
    "moneypuck_goalies": "MoneyPuck goalie CSV (xG, GSAx) per season.", "moneypuck_teams": "MoneyPuck team CSV (xG%, Corsi) per season.",
    "natural_stat_trick": "Natural Stat Trick: Cloudflare 403.", "fangraphs_api": "FanGraphs leaders API: Cloudflare 403.",
    "baseball_savant_csv": "Baseball Savant statcast leaderboard CSV, no key.",
    "the_odds_api_nokey": "the-odds-api: free key (500 credits/mo) required; multi-book current odds.",
    "pinnacle_guest": "Pinnacle guest API: sports list answers; matchups need the public web key header.",
    "betfair_nokey": "Betfair API: app key + login required.", "vsin_splits": "VSiN betting splits HTML.",
    "actionnetwork_scoreboard": "Action Network scoreboard JSON: odds by book and public bet percentages where present. No key.",
    "rotowire_lineups": "RotoWire daily lineups HTML.", "draftkings_sb": "DraftKings sportsbook API: 403.",
    "novig_cdn_index": "Novig public tape CDN: index 403 at root; venue-gate ingests the daily files fine.",
    "sportsdata_nokey": "sportsdata.io: key required.", "dratings_mlb": "DRatings predictions HTML.", "teamrankings": "TeamRankings stats HTML.",
    "pfr_games": "Pro-Football-Reference: Cloudflare 403.", "bref_schedule": "Baseball-Reference answers 200 but its terms forbid scraping; not used.",
    "nfl_nextgen": "NFL Next Gen Stats app API: connection refused.", "soccer_api_football_nokey": "API-Football: key required (free 100/day).",
    "liquipedia": "Liquipedia MediaWiki API (esports).", "pandascore_nokey": "PandaScore: key required.",
    "wnba_espn": "ESPN WNBA scoreboard.", "cfb_espn": "ESPN college football scoreboard.", "soccer_espn_mls": "ESPN MLS scoreboard.",
    "xg_fbref": "FBref: Cloudflare 403.", "statmuse": "StatMuse HTML.",
}


def fetch(name: str, fname: str, url: str) -> dict:
    d = RAW / name
    d.mkdir(parents=True, exist_ok=True)
    t = time.time()
    r = http.fetch(url, timeout=120, browser=True)
    body = r.content
    (d / fname).write_bytes(body)
    row = dict(source=name, file=fname, url=url, status=r.status_code, nbytes=len(body),
               sha256=hashlib.sha256(body).hexdigest(), secs=round(time.time() - t, 1), fetched_at=utc_now())
    with open(MANIFEST, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    print(f"  {name}/{fname} {r.status_code} {len(body):,}B {row['secs']}s", flush=True)
    return row


def pull(names: list[str]) -> None:
    for n in names:
        for fname, url in SOURCES[n]:
            try:
                fetch(n, fname, url)
            except Exception as e:  # noqa: BLE001 - one dead source must not stop the capture
                log.warning("%s/%s: %s", n, fname, e)


def render_doc() -> str:
    """docs/SOURCES.md from the measured probe (data/probe_sources.json)."""
    rows = load_json(PROBE_JSON)
    ok = [r for r in rows if r["status"] == 200]
    bad = [r for r in rows if r["status"] != 200]
    L = ["# Free data sources, probed 2026-10-01 from the workstation (US IP), no keys", "",
         "Measured, not assumed: `python -m pl probe sources` wrote data/probe_sources.json. Raw pulls of the usable ones live under "
         "data/raw/<source>/ with sha256 in data/raw/manifest.jsonl (python -m pl sources).", "",
         f"## Reachable ({len(ok)})", "", "| source | bytes | s | what it gives |", "|---|---|---|---|"]
    L += [f"| {r['source']} | {r['bytes']:,} | {r['secs']} | {NOTES.get(r['source'], '')} |" for r in ok]
    L += ["", f"## Blocked or keyed ({len(bad)})", "", "| source | status | why |", "|---|---|---|"]
    L += [f"| {r['source']} | {r['status']} | {NOTES.get(r['source'], '')} |" for r in bad]
    L += ["", "## What the models use today", "",
          "- ESPN scoreboard + core odds history (scores, probables, ESPN BET / DraftKings open and close): pl/espn.py, data/pl.sqlite.",
          "- Kalshi and Polymarket public quotes at ticket time: pl/paper.py.", "",
          "## Pulled raw, not yet wired into a model (next layers, in order of expected value)", "",
          "1. nflverse games.csv: 27 seasons of closing spreads/totals/moneylines, extends the NFL benchmark 25x and carries rest, QB, roof, surface.",
          "2. MLB Stats API season schedules: umpires, weather, venue, decisions for every game 2024-2026; Baseball Savant statcast; Retrosheet logs.",
          "3. MoneyPuck team/goalie xG and NHL goalie summaries: the goalie-start layer for NHL (probables already captured from ESPN).",
          "4. football-data.co.uk: Pinnacle CLOSING odds for soccer, the sharpest free benchmark anywhere; Novig and Polymarket list soccer.",
          "5. Open-Meteo: wind and temperature at first pitch for MLB totals.",
          "6. ESPN injuries, Action Network splits: availability and public-money features.", "",
          "Keyed free tiers worth a signup if the lane survives: collegefootballdata.com (lines + stats), the-odds-api (multi-book odds, 500/mo)."]
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    ap = argparse.ArgumentParser(prog="pl sources", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", metavar="NAME", help=f"one of {', '.join(SOURCES)}")
    ap.add_argument("--doc", action="store_true", help="render docs/SOURCES.md from the probe instead of pulling")
    a = ap.parse_args(argv)
    if a.doc:
        write_text(DOCS / "SOURCES.md", render_doc())
        print("wrote docs/SOURCES.md")
        return
    pull(a.names or list(SOURCES))


if __name__ == "__main__":
    main()
