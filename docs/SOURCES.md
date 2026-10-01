# Free data sources, probed 2026-10-01 from the workstation (US IP), no keys

Measured, not assumed: ops/probe_sources.py wrote data/probe_sources.json. Raw pulls of the usable ones live under data/raw/<source>/ with sha256 in data/raw/manifest.jsonl (python -m pl.sources).

## Reachable (56)

| source | bytes | s | what it gives |
|---|---|---|---|
| mlb_statsapi_schedule | 4,622 | 0.2 | MLB Stats API: schedule, probable pitchers, lineups, weather, umpires, venue; history to 1901. No key. |
| mlb_statsapi_hist | 183,954 | 0.2 | MLB Stats API: date-range schedule with decisions/linescore (one call per season). |
| mlb_statsapi_pitcher_gamelog | 191 | 0.0 | MLB Stats API: per-player game logs. |
| mlb_statsapi_team_stats | 982 | 0.0 | MLB Stats API: team season stats. |
| nhl_api_schedule | 93,922 | 0.1 | NHL api-web: schedule with gameType (1 pre / 2 reg / 3 post), goalies. |
| nhl_api_score | 70,877 | 0.2 | NHL api-web: scores by date. |
| nhl_api_standings | 58,829 | 0.2 | NHL api-web: standings by date. |
| nhl_goalie_stats | 2,012 | 0.2 | NHL stats REST: goalie summary by season. |
| nhl_api_gamecenter | 13,529 | 0.3 | NHL api-web: boxscore per game. |
| nflverse_games | 327,680 | 0.5 | nflverse games.csv: every NFL game since 1999 with spread_line, total_line, moneylines, QBs, rest, roof, surface. The NFL benchmark file. |
| nflverse_pbp_2025 | 327,680 | 0.3 | nflverse play-by-play (EPA) per season. |
| 538_nba_elo | 327,680 | 1.6 | FiveThirtyEight NBA Elo history 1946-2015. |
| 538_nba_latest | 314,617 | 0.7 | 538 NBA model page: HTML only, archived. |
| football_data_epl_2526 | 203,438 | 1.5 | football-data.co.uk: results + closing odds incl. Pinnacle (PSCH/PSCD/PSCA), 20+ leagues since 1993. |
| football_data_mls | 327,680 | 0.5 | football-data.co.uk MLS file with Pinnacle closing odds. |
| open_meteo_hist | 1,155 | 0.6 | Open-Meteo archive: hourly historical weather by lat/lon, no key. |
| open_meteo_fcst | 1,935 | 0.5 | Open-Meteo forecast, no key. |
| kalshi_series_sports | 430,758 | 0.2 | Kalshi public API: all sports series. |
| kalshi_markets_mlb | 31,064 | 0.1 | Kalshi public: open MLB game markets with yes/no bid/ask in dollars, volume, OI. |
| kalshi_markets_nfl | 139,267 | 0.0 | Kalshi public: NFL game markets. |
| kalshi_trades | 1,576 | 0.0 | Kalshi public: exchange-wide trade tape (taker side, price, count). |
| polymarket_gamma_sports_tags | 150,325 | 0.1 | Polymarket Gamma: sport tags. |
| polymarket_gamma_events_mlb | 729,795 | 0.1 | Polymarket Gamma: MLB events with moneyline/spread/total markets, bestBid/bestAsk, token ids. |
| polymarket_gamma_events_nhl | 835,820 | 0.1 | Polymarket Gamma: NHL events. |
| retrosheet_gl2024 | 327,680 | 0.7 | Retrosheet game logs: every MLB game since 1871 with starters, umpires, attendance. |
| massey_mlb | 6,958 | 0.2 | Massey Ratings pages (HTML). |
| manifold | 2,572 | 0.7 | Manifold Markets API (play money). |
| espn_injuries_mlb | 327,680 | 0.2 | ESPN injuries by league. |
| espn_injuries_nfl | 327,680 | 0.2 | ESPN injuries. |
| espn_injuries_nba | 327,680 | 0.1 | ESPN injuries. |
| espn_injuries_nhl | 327,680 | 0.1 | ESPN injuries. |
| espn_team_stats_mlb | 327,680 | 0.2 | ESPN team statistics. |
| espn_summary_mlb | 327,680 | 0.1 | ESPN game summary: boxscore, starters, odds, weather, win probability. |
| nba_injury_report | 116,667 | 0.6 | Official NBA injury report page (PDF links). |
| ufcstats | 2,998 | 0.1 | ufcstats.com (HTML scrape possible). |
| hltv | 329,668 | 0.3 | HLTV results HTML. |
| understat | 18,698 | 0.7 | understat xG HTML with embedded JSON. |
| sportsbookreview | 241,907 | 0.4 | SBR odds HTML (Next.js payload). |
| covers | 307,326 | 0.2 | Covers matchups HTML (consensus). |
| oddsportal | 316,321 | 1.0 | OddsPortal HTML (heavy JS). |
| hockey_reference | 915,369 | 0.2 | Hockey-Reference answers 200 but its terms forbid automated scraping; not used. |
| moneypuck_goalies | 93,386 | 0.2 | MoneyPuck goalie CSV (xG, GSAx) per season. |
| moneypuck_teams | 99,689 | 0.1 | MoneyPuck team CSV (xG%, Corsi) per season. |
| baseball_savant_csv | 40,490 | 0.2 | Baseball Savant statcast leaderboard CSV, no key. |
| pinnacle_guest | 14,399 | 0.1 | Pinnacle guest API: sports list answers; matchups need the public web key header. |
| vsin_splits | 324,027 | 0.7 | VSiN betting splits HTML. |
| actionnetwork_scoreboard | 18,027 | 0.2 | Action Network scoreboard JSON: odds by book and public bet percentages where present. No key. |
| rotowire_lineups | 330,539 | 0.6 | RotoWire daily lineups HTML. |
| dratings_mlb | 42,734 | 0.7 | DRatings predictions HTML. |
| teamrankings | 316,325 | 0.3 | TeamRankings stats HTML. |
| bref_schedule | 651,519 | 0.2 | Baseball-Reference answers 200 but its terms forbid scraping; not used. |
| liquipedia | 283 | 0.4 | Liquipedia MediaWiki API (esports). |
| wnba_espn | 23,994 | 0.1 | ESPN WNBA scoreboard. |
| cfb_espn | 41,505 | 0.0 | ESPN college football scoreboard. |
| soccer_espn_mls | 15,269 | 0.0 | ESPN MLS scoreboard. |
| statmuse | 385,195 | 0.2 | StatMuse HTML. |

## Blocked or keyed (26)

| source | status | why |
|---|---|---|
| nba_cdn_schedule | 403 | NBA CDN schedule: Akamai 403 from this IP. |
| nba_cdn_today | 403 | NBA CDN live scoreboard: 403. |
| nba_stats_api | ERR | stats.nba.com: hangs for scripts. |
| 538_nfl_elo | 404 | FiveThirtyEight NFL Elo: repo path gone (404). |
| 538_mlb_elo | 404 | FiveThirtyEight MLB Elo: 404. |
| tennis_data_2026 | 403 | tennis-data.co.uk: Cloudflare 403 to scripts (browser download works). |
| tennis_data_2025 | 403 | 403. |
| tennis_data_wta_2025 | 403 | 403. |
| sackmann_atp_2025 | 404 | Jeff Sackmann tennis_atp: 404 at that path; check current file names. |
| sackmann_atp_2026 | 404 | 404. |
| clubelo | 502 | clubelo.com API: 502 at probe time (transient). |
| cfbd_no_key | 401 | collegefootballdata.com: free key required (includes betting lines). |
| espn_core_athlete_stats | 404 | ESPN core athlete statistics: 404 for that id/season. |
| balldontlie_nokey | 401 | balldontlie: key required. |
| natural_stat_trick | 403 | Natural Stat Trick: Cloudflare 403. |
| fangraphs_api | 403 | FanGraphs leaders API: Cloudflare 403. |
| the_odds_api_nokey | 401 | the-odds-api: free key (500 credits/mo) required; multi-book current odds. |
| betfair_nokey | 403 | Betfair API: app key + login required. |
| draftkings_sb | 403 | DraftKings sportsbook API: 403. |
| novig_cdn_index | 403 | Novig public tape CDN: index 403 at root; venue-gate ingests the daily files fine. |
| sportsdata_nokey | 401 | sportsdata.io: key required. |
| pfr_games | 403 | Pro-Football-Reference: Cloudflare 403. |
| nfl_nextgen | ERR | NFL Next Gen Stats app API: connection refused. |
| soccer_api_football_nokey | 403 | API-Football: key required (free 100/day). |
| pandascore_nokey | 403 | PandaScore: key required. |
| xg_fbref | 403 | FBref: Cloudflare 403. |

## What the models use today

- ESPN scoreboard + core odds history (scores, probables, ESPN BET / DraftKings open and close): pl/espn.py, data/pl.sqlite.
- Kalshi and Polymarket public quotes at ticket time: pl/paper.py.

## Pulled raw, not yet wired into a model (next layers, in order of expected value)

1. nflverse games.csv: 27 seasons of closing spreads/totals/moneylines, extends the NFL benchmark 25x and carries rest, QB, roof, surface.
2. MLB Stats API season schedules: umpires, weather, venue, decisions for every game 2024-2026; Baseball Savant statcast; Retrosheet logs.
3. MoneyPuck team/goalie xG and NHL goalie summaries: the goalie-start layer for NHL (probables already captured from ESPN).
4. football-data.co.uk: Pinnacle CLOSING odds for soccer, the sharpest free benchmark anywhere; Novig and Polymarket list soccer.
5. Open-Meteo: wind and temperature at first pitch for MLB totals.
6. ESPN injuries, Action Network splits: availability and public-money features.

Keyed free tiers worth a signup if the lane survives: collegefootballdata.com (lines + stats), the-odds-api (multi-book odds, 500/mo).
