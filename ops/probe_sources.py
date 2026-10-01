"""Probe every candidate free data source once; print status, bytes, latency, a snippet.
Output is the evidence for docs/SOURCES.md. Nothing here is assumed; every row is measured."""
import json
import sys
import time

import requests

s = requests.Session()
s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
s.headers["Accept"] = "*/*"

PROBES = {
    "mlb_statsapi_schedule": "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-10-01&hydrate=probablePitcher,lineups,weather,officials",
    "mlb_statsapi_hist": "https://statsapi.mlb.com/api/v1/schedule?sportId=1&startDate=2024-06-01&endDate=2024-06-03&hydrate=probablePitcher,decisions,linescore",
    "mlb_statsapi_pitcher_gamelog": "https://statsapi.mlb.com/api/v1/people/592789/stats?stats=gameLog&group=pitching&season=2026",
    "mlb_statsapi_team_stats": "https://statsapi.mlb.com/api/v1/teams/144/stats?stats=season&group=hitting&season=2026",
    "nhl_api_schedule": "https://api-web.nhle.com/v1/schedule/2026-10-01",
    "nhl_api_score": "https://api-web.nhle.com/v1/score/2026-01-15",
    "nhl_api_standings": "https://api-web.nhle.com/v1/standings/2026-01-15",
    "nhl_goalie_stats": "https://api.nhle.com/stats/rest/en/goalie/summary?limit=5&cayenneExp=seasonId=20252026",
    "nhl_api_gamecenter": "https://api-web.nhle.com/v1/gamecenter/2025020001/boxscore",
    "nba_cdn_schedule": "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json",
    "nba_cdn_today": "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json",
    "nba_stats_api": "https://stats.nba.com/stats/leaguegamelog?Counter=1000&DateFrom=&DateTo=&Direction=DESC&LeagueID=00&PlayerOrTeam=T&Season=2025-26&SeasonType=Regular%20Season&Sorter=DATE",
    "nflverse_games": "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
    "nflverse_pbp_2025": "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.csv.gz",
    "538_nfl_elo": "https://raw.githubusercontent.com/fivethirtyeight/data/master/nfl-elo/nfl_elo.csv",
    "538_mlb_elo": "https://raw.githubusercontent.com/fivethirtyeight/data/master/mlb-elo/mlb_elo.csv",
    "538_nba_elo": "https://raw.githubusercontent.com/fivethirtyeight/data/master/nba-elo/nbaallelo.csv",
    "538_nba_latest": "https://projects.fivethirtyeight.com/nba-model/nba_elo_latest.csv",
    "football_data_epl_2526": "https://www.football-data.co.uk/mmz4281/2526/E0.csv",
    "football_data_mls": "https://www.football-data.co.uk/new/USA.csv",
    "tennis_data_2026": "http://www.tennis-data.co.uk/2026/2026.xlsx",
    "tennis_data_2025": "http://www.tennis-data.co.uk/2025/2025.xlsx",
    "tennis_data_wta_2025": "http://www.tennis-data.co.uk/2025w/2025.xlsx",
    "sackmann_atp_2025": "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_2025.csv",
    "sackmann_atp_2026": "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_2026.csv",
    "clubelo": "http://api.clubelo.com/2026-10-01",
    "open_meteo_hist": "https://archive-api.open-meteo.com/v1/archive?latitude=33.89&longitude=-84.47&start_date=2026-09-15&end_date=2026-09-15&hourly=temperature_2m,wind_speed_10m,precipitation",
    "open_meteo_fcst": "https://api.open-meteo.com/v1/forecast?latitude=33.89&longitude=-84.47&hourly=temperature_2m,wind_speed_10m,precipitation&forecast_days=2",
    "kalshi_series_sports": "https://api.elections.kalshi.com/trade-api/v2/series?category=Sports&limit=200",
    "kalshi_markets_mlb": "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open&series_ticker=KXMLBGAME",
    "kalshi_markets_nfl": "https://api.elections.kalshi.com/trade-api/v2/markets?limit=200&status=open&series_ticker=KXNFLGAME",
    "kalshi_trades": "https://api.elections.kalshi.com/trade-api/v2/markets/trades?limit=5",
    "polymarket_gamma_sports_tags": "https://gamma-api.polymarket.com/sports",
    "polymarket_gamma_events_mlb": "https://gamma-api.polymarket.com/events?limit=20&closed=false&tag_slug=mlb",
    "polymarket_gamma_events_nhl": "https://gamma-api.polymarket.com/events?limit=20&closed=false&tag_slug=nhl",
    "retrosheet_gl2024": "https://www.retrosheet.org/gamelogs/gl2024.zip",
    "cfbd_no_key": "https://api.collegefootballdata.com/games?year=2026&week=5",
    "massey_mlb": "https://masseyratings.com/mlb/ratings",
    "manifold": "https://api.manifold.markets/v0/search-markets?term=NHL&limit=3",
    "espn_injuries_mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/injuries",
    "espn_injuries_nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
    "espn_injuries_nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
    "espn_injuries_nhl": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries",
    "espn_team_stats_mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/15/statistics",
    "espn_core_athlete_stats": "https://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/seasons/2026/types/2/athletes/592789/statistics",
    "espn_summary_mlb": "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary?event=401816943",
    "nba_injury_report": "https://official.nba.com/nba-injury-report-2025-26-season/",
    "ufcstats": "http://ufcstats.com/statistics/events/completed",
    "hltv": "https://www.hltv.org/results",
    "understat": "https://understat.com/league/EPL/2026",
    "balldontlie_nokey": "https://api.balldontlie.io/v1/games?seasons[]=2025&per_page=5",
    "sportsbookreview": "https://www.sportsbookreview.com/betting-odds/mlb-baseball/",
    "covers": "https://www.covers.com/sports/mlb/matchups",
    "oddsportal": "https://www.oddsportal.com/baseball/usa/mlb/",
    "hockey_reference": "https://www.hockey-reference.com/leagues/NHL_2026_games.html",
    "moneypuck_goalies": "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/goalies.csv",
    "moneypuck_teams": "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/teams.csv",
    "natural_stat_trick": "https://www.naturalstattrick.com/teamtable.php?fromseason=20252026&thruseason=20252026",
    "fangraphs_api": "https://www.fangraphs.com/api/leaders/major-league/data?age=&pos=all&stats=pit&lg=all&qual=0&season=2026&season1=2026&startdate=&enddate=&month=0&hand=&team=0&pageitems=5&pagenum=1&ind=0&rost=0&players=&type=8&postseason=&sortdir=default&sortstat=WAR",
    "baseball_savant_csv": "https://baseballsavant.mlb.com/leaderboard/statcast?type=pitcher&year=2026&position=&team=&min=q&csv=true",
    "the_odds_api_nokey": "https://api.the-odds-api.com/v4/sports/?apiKey=",
    "pinnacle_guest": "https://guest.api.arcadia.pinnacle.com/0.1/sports",
    "betfair_nokey": "https://api.betfair.com/exchange/betting/rest/v1.0/listEventTypes/",
    "vsin_splits": "https://data.vsin.com/mlb/betting-splits/",
    "actionnetwork_scoreboard": "https://api.actionnetwork.com/web/v1/scoreboard/mlb?period=game",
    "rotowire_lineups": "https://www.rotowire.com/baseball/daily-lineups.php",
    "draftkings_sb": "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/84240",
    "novig_cdn_index": "https://data.novig.com/index.json",
    "sportsdata_nokey": "https://api.sportsdata.io/v3/mlb/scores/json/GamesByDate/2026-OCT-01",
    "dratings_mlb": "https://www.dratings.com/predictor/mlb-baseball-predictions/",
    "teamrankings": "https://www.teamrankings.com/mlb/stat/runs-per-game",
    "pfr_games": "https://www.pro-football-reference.com/years/2026/games.htm",
    "bref_schedule": "https://www.baseball-reference.com/leagues/majors/2026-schedule.shtml",
    "nfl_nextgen": "https://appapi.ngs.nfl.com/league/schedule?season=2026&seasonType=REG",
    "soccer_api_football_nokey": "https://v3.football.api-sports.io/status",
    "liquipedia": "https://liquipedia.net/counterstrike/api.php?action=query&list=recentchanges&format=json&rclimit=1",
    "pandascore_nokey": "https://api.pandascore.co/matches/upcoming?per_page=1",
    "wnba_espn": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/scoreboard?dates=20261001",
    "cfb_espn": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard?dates=20261001&groups=80",
    "soccer_espn_mls": "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates=20261001",
    "xg_fbref": "https://fbref.com/en/comps/9/Premier-League-Stats",
    "statmuse": "https://www.statmuse.com/mlb",
}


def main():
    rows = []
    for k, u in PROBES.items():
        t = time.time()
        try:
            r = s.get(u, timeout=20, stream=True)
            ct = r.headers.get("content-type", "")[:28]
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > 300000:
                    break
            r.close()
            snippet = body[:100].decode("utf-8", "replace").replace("\n", " ").replace("\r", " ")
            rows.append((k, r.status_code, len(body), round(time.time() - t, 1), ct, snippet))
        except Exception as e:  # noqa: BLE001
            rows.append((k, "ERR", 0, round(time.time() - t, 1), "", str(e)[:90]))
        print(f"{rows[-1][0]:30s} {str(rows[-1][1]):4s} {rows[-1][2]:>7} {rows[-1][3]:>5}s {rows[-1][4]:28s} {rows[-1][5][:80]}", flush=True)
    json.dump([dict(zip(["source", "status", "bytes", "secs", "content_type", "snippet"], r)) for r in rows],
              open("data/probe_sources.json", "w"), indent=1)


if __name__ == "__main__":
    main()
