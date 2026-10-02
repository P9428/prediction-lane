from __future__ import annotations

import math
from datetime import date

import pytest

from pl import core, espn, paper
from tests.conftest import espn_event

PIT_CLE = "2026-10-02T00:15:00Z"   # Thursday night, Oct 1 US date


def prediction(event_id="401872964", league="nfl", start=PIT_CLE, **over):
    row = dict(ts="2026-10-01T20:48:13+00:00", day="2026-10-01", league=league, event_id=event_id, start=start,
               home="CLE", away="PIT", home_id="5", away_id="23", p_elo=0.46, p_gauss=0.43, p_pois=None, p_pois_pitch=None,
               mu_gauss=-2.1, rest_diff=0.0, p_model=0.46, p_blend=0.42,
               sportsbook=dict(ml_home=124.0, ml_away=-148.0, provider="DraftKings", p_home_shin=0.4247),
               kalshi=dict(away=dict(ticker="KXNFLGAME-26OCT01PITCLE-PIT", bid=0.57, ask=0.58),
                           home=dict(ticker="KXNFLGAME-26OCT01PITCLE-CLE", bid=0.42, ask=0.43)),
               polymarket={}, status="pending")
    row.update(over)
    return row


def ticket(event_id, start, dec, stake=7.67):
    return dict(ts="x", day="2026-10-01", league="nfl", event_id=event_id, start=start, home="CLE", away="PIT",
                venue="kalshi", side="away", ask=0.58, dec=dec, edge=0.03, p=0.58, stake=stake, kelly_full=0.03, status="pending")


def scoreboard_with(monkeypatch, by_date: dict[date, list[dict]]):
    calls = []

    def scoreboard(league, day=None, **params):
        calls.append((league, day))
        return by_date.get(day, [])

    monkeypatch.setattr(espn, "scoreboard", scoreboard)
    return calls


def test_settle_finds_game_filed_under_prior_us_date(journal, monkeypatch, capsys):
    """Regression: a 00:15Z kickoff is Oct 2 UTC but ESPN lists it under Oct 1."""
    core.append_jsonl(paper.PRED, prediction())
    calls = scoreboard_with(monkeypatch, {date(2026, 10, 1): [espn_event("401872964", PIT_CLE, ("5", "CLE"), ("23", "PIT"), (27, 24))]})
    paper.settle()
    assert {d for _, d in calls} == {date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)}
    rows = core.read_jsonl(paper.SETTLED)
    assert len(rows) == 1 and rows[0]["kind"] == "pred" and rows[0]["y"] == 1.0
    r = rows[0]
    assert r["ll_p_model"] == pytest.approx(-math.log(0.46)) and r["ll_book"] == pytest.approx(-math.log(0.4247))
    assert r["ll_kalshi"] == pytest.approx(-math.log(0.43 / (0.43 + 0.58)))
    assert "ll_p_pois" not in r and "ll_polymarket" not in r
    assert "settled 1 rows" in capsys.readouterr().out


def test_settle_is_idempotent_and_skips_ties_and_unfinished(journal, monkeypatch):
    core.append_jsonl(paper.PRED, prediction())
    core.append_jsonl(paper.PRED, prediction(event_id="tie", start="2026-10-01T17:00:00Z"))
    core.append_jsonl(paper.PRED, prediction(event_id="live", start="2026-10-01T17:00:00Z"))
    board = {date(2026, 10, 1): [espn_event("401872964", PIT_CLE, ("5", "CLE"), ("23", "PIT"), (27, 24)),
                                 espn_event("tie", "2026-10-01T17:00:00Z", ("5", "CLE"), ("23", "PIT"), (20, 20)),
                                 espn_event("live", "2026-10-01T17:00:00Z", ("5", "CLE"), ("23", "PIT"), status="STATUS_IN_PROGRESS")]}
    scoreboard_with(monkeypatch, board)
    paper.settle()
    paper.settle()
    rows = core.read_jsonl(paper.SETTLED)
    assert [r["event_id"] for r in rows] == ["401872964"]


def test_settle_ticket_pnl_and_status_page(journal, monkeypatch, capsys):
    core.append_jsonl(paper.PRED, prediction())
    core.append_jsonl(paper.TICK, ticket("401872964", PIT_CLE, dec=1.68))
    core.append_jsonl(paper.TICK, ticket("pending-1", "2026-10-02T23:00:00Z", dec=2.34))
    scoreboard_with(monkeypatch, {date(2026, 10, 1): [espn_event("401872964", PIT_CLE, ("5", "CLE"), ("23", "PIT"), (27, 24))]})
    paper.settle()
    rows = core.read_jsonl(paper.SETTLED)
    t = [r for r in rows if r["kind"] == "ticket"][0]
    assert t["won"] is False and t["pnl"] == -7.67
    page = paper.STATUS_MD.read_text(encoding="utf-8")
    assert "predictions settled: 1   tickets settled: 1   pending tickets: 1" in page
    assert "| p_model | 1 |" in page and "tickets: 1  staked $7.67  pnl $-7.67" in page
    out = capsys.readouterr().out.splitlines()
    assert out[out.index("settled 2 rows") + 1:] == page.splitlines()


def test_log_loss_floor():
    assert paper.log_loss(0.0, 1.0) == pytest.approx(-math.log(1e-6))
    assert paper.log_loss(1.0, 0.0) == pytest.approx(-math.log(1e-6))
    assert paper.log_loss(0.25, 0.0) == pytest.approx(-math.log(0.75))


def test_parse_event_scores_and_probables():
    e = espn_event("1", PIT_CLE, ("5", "CLE"), ("23", "PIT"), (27, 24))
    r = espn.parse_event("nfl", e)
    assert r["completed"] == 1 and r["home_score"] == 27.0 and r["away_score"] == 24.0 and r["home_prob_id"] is None
    r = espn.parse_event("nfl", espn_event("2", PIT_CLE, ("5", "CLE"), ("23", "PIT")))
    assert r["completed"] == 0 and r["home_score"] is None and r["status"] == "STATUS_SCHEDULED"
