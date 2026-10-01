"""Render docs/SOURCES.md from data/probe_sources.json (the measured probe)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = json.load(open(ROOT / "data" / "probe_sources.json"))
N = {
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
ok = [r for r in rows if r["status"] == 200]
bad = [r for r in rows if r["status"] != 200]
L = ["# Free data sources, probed 2026-10-01 from the workstation (US IP), no keys", "",
     "Measured, not assumed: ops/probe_sources.py wrote data/probe_sources.json. Raw pulls of the usable ones live under "
     "data/raw/<source>/ with sha256 in data/raw/manifest.jsonl (python -m pl.sources).", "",
     f"## Reachable ({len(ok)})", "", "| source | bytes | s | what it gives |", "|---|---|---|---|"]
L += [f"| {r['source']} | {r['bytes']:,} | {r['secs']} | {N.get(r['source'], '')} |" for r in ok]
L += ["", f"## Blocked or keyed ({len(bad)})", "", "| source | status | why |", "|---|---|---|"]
L += [f"| {r['source']} | {r['status']} | {N.get(r['source'], '')} |" for r in bad]
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
(ROOT / "docs" / "SOURCES.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("SOURCES.md", len(ok), "reachable", len(bad), "blocked/keyed")
