from __future__ import annotations

import numpy as np
import pytest

from pl import espn, paper, stats


@pytest.mark.parametrize("american,dec", [(-110, 1 + 100 / 110), (150, 2.5), (100, 2.0), (-100, 2.0), (0, None), ("x", None), (None, None)])
def test_american_to_decimal_scalar(american, dec):
    out = espn.american_to_decimal(american)
    assert out == pytest.approx(dec) if dec is not None else out is None


def test_american_to_decimal_vector_matches_scalar():
    a = np.array([-148.0, 124.0, np.nan])
    v = stats.american_to_decimal(a)
    assert v[0] == pytest.approx(espn.american_to_decimal(-148)) and v[1] == pytest.approx(espn.american_to_decimal(124)) and np.isnan(v[2])


def test_shin_devig_removes_overround_and_keeps_order():
    dec_h, dec_a = stats.american_to_decimal(np.array([124.0])), stats.american_to_decimal(np.array([-148.0]))
    ih, ia = stats.implied(dec_h), stats.implied(dec_a)
    assert ih[0] + ia[0] > 1
    ph = stats.devig_shin(ih, ia)[0]
    assert 0 < ph < 0.5 and ph < ih[0]
    assert stats.devig_proportional(ih, ia)[0] == pytest.approx(ih[0] / (ih[0] + ia[0]))


def test_price_edge_no_fee_is_inverse_ask():
    dec, edge = paper.price_edge(0.5, 0.4, 0.0)
    assert dec == pytest.approx(2.5) and edge == pytest.approx(0.25)


def test_price_edge_fee_lowers_payout():
    dec0, _ = paper.price_edge(0.5, 0.4, 0.0)
    dec1, _ = paper.price_edge(0.5, 0.4, paper.KALSHI_FEE)
    assert dec1 < dec0 and dec1 == pytest.approx(1 / (0.4 + 0.07 * 0.4 * 0.6))


def test_best_price_picks_max_edge_across_venues_and_sides():
    kq = {"home": {"ask": 0.60}, "away": {"ask": 0.42}}
    pq = {"home": {"ask": 0.58}, "away": {"ask": 0.45}}
    best = paper.best_price(0.55, {"kalshi": kq, "polymarket": pq})
    # the away side at Kalshi's 0.42 ask is the only positive-edge price: p_away 0.45 against ~0.437 all-in cost
    assert best["venue"] == "kalshi" and best["side"] == "away" and best["p"] == pytest.approx(0.45)
    dec, edge = paper.price_edge(0.45, 0.42, paper.KALSHI_FEE)
    assert best["dec"] == pytest.approx(dec) and best["edge"] == pytest.approx(edge) and edge > 0
    assert all(paper.price_edge(0.55 if s == "home" else 0.45, q[s]["ask"], f)[1] < edge
               for q, f in ((kq, paper.KALSHI_FEE), (pq, paper.POLY_FEE)) for s in q if (q, s) != (kq, "away"))


def test_best_price_ignores_missing_or_degenerate_asks():
    assert paper.best_price(0.5, {"kalshi": {}, "polymarket": {"home": {"ask": float("nan")}, "away": {"ask": 1.0}}}) is None


def test_kelly_stake_caps_and_floors():
    kelly, stake = paper.kelly_stake(0.6, 2.0)            # b=1: kelly = 0.2 -> 0.25*0.2 = 0.05 > cap 0.02
    assert kelly == pytest.approx(0.2) and stake == pytest.approx(0.02 * paper.BANKROLL)
    kelly, stake = paper.kelly_stake(0.4, 1.5)            # negative edge -> 0
    assert kelly == 0 and stake == 0
    kelly, stake = paper.kelly_stake(0.52, 2.0)           # 0.04 kelly -> 0.01 of bankroll
    assert stake == pytest.approx(10.0)
