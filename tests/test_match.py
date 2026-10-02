from __future__ import annotations

import pandas as pd

from pl import paper


def kalshi_market(event: str, side: str, bid: str, ask: str, last: str = "", vol: str = "10"):
    return dict(event_ticker=event, ticker=f"{event}-{side}", yes_bid_dollars=bid, yes_ask_dollars=ask, last_price_dollars=last, volume_fp=vol)


def game(home="CLE", away="PIT", home_id="5", away_id="23", start="2026-10-02T00:15:00Z"):
    return pd.Series(dict(home_abbr=home, away_abbr=away, home_id=home_id, away_id=away_id, start=pd.Timestamp(start)))


def test_match_kalshi_by_team_pair_when_local_date_differs():
    # 8:15pm ET on Oct 1 is Oct 2 UTC; Kalshi dates the event by local time
    ms = [kalshi_market("KXNFLGAME-26OCT01PITCLE", "PIT", "0.57", "0.58", "0.58"),
          kalshi_market("KXNFLGAME-26OCT01PITCLE", "CLE", "0.42", "0.43", "0.43"),
          kalshi_market("KXNFLGAME-26OCT05DALNYG", "DAL", "0.5", "0.51")]
    q = paper.match_kalshi(game(), ms)
    assert q["home"]["ticker"].endswith("-CLE") and q["home"]["ask"] == 0.43
    assert q["away"]["ticker"].endswith("-PIT") and q["away"]["bid"] == 0.57 and q["away"]["volume"] == 10.0


def test_match_kalshi_prefers_same_day_event_and_maps_team_codes():
    ms = [kalshi_market("KXMLBGAME-26OCT01CWSCLE", "CWS", "0.40", "0.41"),
          kalshi_market("KXMLBGAME-26OCT02CWSCLE", "CWS", "0.44", "0.45"),
          kalshi_market("KXMLBGAME-26OCT02CWSCLE", "CLE", "0.55", "0.56")]
    q = paper.match_kalshi(game(home="CLE", away="CHW"), ms)
    assert q["away"]["ask"] == 0.45 and q["home"]["ask"] == 0.56


def test_match_kalshi_empty_quotes_become_nan():
    q = paper.match_kalshi(game(), [kalshi_market("KXNFLGAME-26OCT01PITCLE", "CLE", "", "", "")])
    assert q["home"]["ask"] != q["home"]["ask"] and "away" not in q


def poly_market(start, outcomes, bid, ask, tokens=("t0", "t1")):
    return dict(start=start, outcomes=list(outcomes), best_bid=bid, best_ask=ask, tokens=list(tokens), condition_id="c1", liquidity=1000.0)


NAMES = {"5": "Cleveland Browns", "23": "Pittsburgh Steelers"}


def test_match_polymarket_home_is_outcome_zero():
    q = paper.match_polymarket(game(), [poly_market("2026-10-02 00:15:00+00", ("Cleveland Browns", "Pittsburgh Steelers"), 0.42, 0.43)], NAMES)
    assert q["home"] == dict(bid=0.42, ask=0.43, token="t0", condition_id="c1", liquidity=1000.0)
    assert q["away"]["bid"] == 1 - 0.43 and q["away"]["ask"] == 1 - 0.42 and q["away"]["token"] == "t1"


def test_match_polymarket_home_is_outcome_one_complements():
    q = paper.match_polymarket(game(), [poly_market("2026-10-02T00:15:00Z", ("Pittsburgh Steelers", "Cleveland Browns"), 0.57, 0.58)], NAMES)
    assert q["home"]["bid"] == 1 - 0.58 and q["home"]["token"] == "t1" and q["away"]["ask"] == 0.58


def test_match_polymarket_rejects_wrong_time_names_or_missing_book():
    far = poly_market("2026-10-03T00:15:00Z", ("Cleveland Browns", "Pittsburgh Steelers"), 0.4, 0.5)
    other = poly_market("2026-10-02T00:15:00Z", ("Cleveland Browns", "Baltimore Ravens"), 0.4, 0.5)
    nobook = poly_market("2026-10-02T00:15:00Z", ("Cleveland Browns", "Pittsburgh Steelers"), None, 0.5)
    bad_ts = poly_market("not a date", ("Cleveland Browns", "Pittsburgh Steelers"), 0.4, 0.5)
    assert paper.match_polymarket(game(), [far, other, nobook, bad_ts], NAMES) == {}
    assert paper.match_polymarket(game(), [far], {}) == {}
