"""ESPN public endpoints: scoreboard (scores, probables, live odds) and the core
odds history (open / close / current per provider) for settled games.

Measured 2026-10-01: both answer unauthenticated at ~0.15 s. The site scoreboard
rejects date ranges (400) for MLB/NBA/NHL, so history is walked one date at a
time; NFL is walked by week. Historical odds live only on the core endpoint
`events/{id}/competitions/{id}/odds`; the scoreboard `odds` field is null once a
game is final.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta

import requests

SITE = "https://site.api.espn.com/apis/site/v2/sports"
CORE = "https://sports.core.api.espn.com/v2/sports"

LEAGUES = {
    "mlb": ("baseball", "mlb"),
    "nba": ("basketball", "nba"),
    "nhl": ("hockey", "nhl"),
    "nfl": ("football", "nfl"),
}

# provider priority for the benchmark line: lowest number wins
PROVIDER_RANK = {"58": 0, "40": 1, "100": 1, "31": 2, "47": 3, "2000": 4}

_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 prediction-lane/0.1"


def get(url: str, tries: int = 4, timeout: int = 30) -> dict:
    last: Exception | None = None
    for i in range(tries):
        try:
            r = _s.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (400, 404):
                raise RuntimeError(f"{r.status_code} {url}")
            last = RuntimeError(f"{r.status_code} {url}")
        except (requests.RequestException, ValueError) as e:
            last = e
        time.sleep(0.8 * (i + 1))
    assert last is not None
    raise last


def scoreboard(league: str, day: date | None = None, **params) -> list[dict]:
    sport, lg = LEAGUES[league]
    q: dict = dict(limit=200)
    if day is not None:
        q["dates"] = day.strftime("%Y%m%d")
    q.update(params)
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    return get(f"{SITE}/{sport}/{lg}/scoreboard?{qs}").get("events", [])


def american_to_decimal(a) -> float | None:
    try:
        a = float(a)
    except (TypeError, ValueError):
        return None
    if a == 0:
        return None
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_event(league: str, e: dict) -> dict:
    c = e["competitions"][0]
    st = c["status"]["type"]
    row = dict(league=league, event_id=str(e["id"]), start=e["date"],
               season=int((e.get("season") or {}).get("year") or 0),
               season_type=int((e.get("season") or {}).get("type") or 0),
               status=st.get("name"), completed=int(bool(st.get("completed"))),
               neutral=int(bool(c.get("neutralSite"))))
    for t in c["competitors"]:
        side = "home" if t["homeAway"] == "home" else "away"
        row[f"{side}_id"] = str(t["team"]["id"])
        row[f"{side}_abbr"] = t["team"].get("abbreviation")
        row[f"{side}_score"] = _num(t.get("score"))
        pr = (t.get("probables") or [{}])[0]
        ath = pr.get("athlete") or {}
        row[f"{side}_prob_id"] = str(ath["id"]) if ath.get("id") else None
        row[f"{side}_prob_name"] = ath.get("displayName")
    od = (c.get("odds") or [None])[0]
    if od:
        row["live_provider"] = (od.get("provider") or {}).get("name")
        row["live_spread_home"] = _num(od.get("spread"))
        row["live_total"] = _num(od.get("overUnder"))
        ml = od.get("moneyline") or {}
        h_close = ((ml.get("home") or {}).get("close") or {}).get("odds")
        a_close = ((ml.get("away") or {}).get("close") or {}).get("odds")
        row["live_ml_home"] = _num(h_close) if _num(h_close) is not None else _num((od.get("homeTeamOdds") or {}).get("moneyLine"))
        row["live_ml_away"] = _num(a_close) if _num(a_close) is not None else _num((od.get("awayTeamOdds") or {}).get("moneyLine"))
    return row


def odds_history(league: str, event_id: str) -> dict:
    """The benchmark line for a settled game, from the best-ranked provider that
    carries a moneyline. `close` when the provider publishes one, else `current`,
    which on a settled game is the last pre-game update."""
    sport, lg = LEAGUES[league]
    try:
        j = get(f"{CORE}/{sport}/leagues/{lg}/events/{event_id}/competitions/{event_id}/odds")
    except RuntimeError:
        return {}
    items = j.get("items") or []
    best, best_rank = None, 99

    def side(o: dict, phase: str):
        ph = o.get(phase) or {}
        ml = (ph.get("moneyLine") or {}).get("american")
        sp = (ph.get("pointSpread") or {}).get("american")
        return _num(ml), _num(sp)

    for it in items:
        prov = it.get("provider") or {}
        pid = str(prov.get("id"))
        if "Live" in str(prov.get("name", "")):
            continue
        h, a = it.get("homeTeamOdds") or {}, it.get("awayTeamOdds") or {}
        mlh_c, sph_c = side(h, "close")
        mla_c, spa_c = side(a, "close")
        mlh_o, sph_o = side(h, "open")
        mla_o, spa_o = side(a, "open")
        mlh_cur, mla_cur = _num(h.get("moneyLine")), _num(a.get("moneyLine"))
        mlh = mlh_c if mlh_c is not None else mlh_cur
        mla = mla_c if mla_c is not None else mla_cur
        if mlh is None or mla is None:
            continue
        rank = PROVIDER_RANK.get(pid, 50)
        if rank < best_rank:
            best_rank = rank
            tot_close = _num(((it.get("close") or {}).get("total") or {}).get("american"))
            if tot_close is None:
                tot_close = _num(it.get("overUnder"))
            tot_open = _num(((it.get("open") or {}).get("total") or {}).get("american"))
            best = dict(provider=prov.get("name"), provider_id=pid,
                        ml_home=mlh, ml_away=mla, ml_home_open=mlh_o, ml_away_open=mla_o,
                        spread_home=sph_c if sph_c is not None else _num(it.get("spread")),
                        spread_home_open=sph_o, total=tot_close, total_open=tot_open,
                        n_providers=len(items), raw=json.dumps(items, separators=(",", ":")))
    return best or {}


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)
