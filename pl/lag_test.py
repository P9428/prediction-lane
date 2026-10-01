"""PREREG_KALSHI_LAG.md, executed. Joins Kalshi settled game markets to ESPN games and
the walk-forward backtest probabilities, then runs P1/P2 at h=3 and the diagnostics.

usage: python -m pl.lag_test   -> docs/KALSHI_LAG.md, data/kalshi_lag_rows.csv
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pl import stats
from pl.kalshi_hist import DB as KDB

ROOT = Path(__file__).resolve().parents[1]
FEE = 0.07
EDGE_MIN = 0.02
H_PRIMARY = 3
H_ALL = (24, 12, 6, 3, 1)
MAX_SPREAD = 0.10
# Kalshi team codes -> ESPN abbreviations where they differ
CODE = {"CWS": "CHW", "AZ": "ARI", "WAS": "WSH", "KCR": "KC", "SFG": "SF", "SDP": "SD", "TBR": "TB", "LVR": "LV", "JAC": "JAX"}
_TK = re.compile(r"^KX(?P<series>[A-Z]+)-(?P<date>\d{2}[A-Z]{3}\d{2})(?P<time>\d{4})?(?P<teams>[A-Z]+)-(?P<side>[A-Z]+)$")


def load_kalshi() -> pd.DataFrame:
    c = sqlite3.connect(KDB)
    m = pd.read_sql("SELECT ticker, series, event_ticker, result, volume, open_time, close_time FROM markets", c)
    cd = pd.read_sql("SELECT * FROM candles", c)
    c.close()
    rows = []
    for r in m.itertuples(index=False):
        g = _TK.match(r.ticker)
        if not g:
            continue
        d = datetime.strptime(g["date"], "%y%b%d").date()
        hhmm = g["time"] or "1200"
        kdt = pd.Timestamp(datetime.strptime(g["date"] + hhmm, "%y%b%d%H%M")).tz_localize("US/Eastern").tz_convert("UTC")
        teams, side = g["teams"], g["side"]
        if not teams.endswith(side) and not teams.startswith(side):
            continue
        other = teams[: -len(side)] if teams.endswith(side) else teams[len(side):]
        rows.append(dict(ticker=r.ticker, league=r.series[2:].replace("GAME", "").lower(), event_ticker=r.event_ticker,
                         kdate=d, kdt=kdt, has_time=bool(g["time"]), side=CODE.get(side, side), other=CODE.get(other, other),
                         side_is_home=teams.endswith(side), result=r.result, volume=r.volume))
    km = pd.DataFrame(rows)
    return km, cd


def load_games(league: str) -> pd.DataFrame:
    g = pd.read_csv(ROOT / "data" / f"backtest_{league}.csv", parse_dates=["start"])
    g["start"] = pd.to_datetime(g["start"], utc=True)
    g["edate_et"] = (g.start - pd.Timedelta(hours=4)).dt.date      # Kalshi tickers are dated in US Eastern
    return g


def join(km: pd.DataFrame, cd: pd.DataFrame) -> pd.DataFrame:
    out = []
    for lg in sorted(km.league.unique()):
        try:
            g = load_games(lg)
        except FileNotFoundError:
            continue
        k = km[km.league == lg]
        for r in k.itertuples(index=False):
            home, away = (r.side, r.other) if r.side_is_home else (r.other, r.side)
            cand = g[(g.home_abbr == home) & (g.away_abbr == away)]
            if r.has_time:
                dt = (cand.start - r.kdt).abs()
                cand = cand[dt <= pd.Timedelta(hours=6)]
                if cand.empty:
                    continue
                x = cand.loc[dt[cand.index].idxmin()]
            else:
                cand = cand[(cand.edate_et - r.kdate).abs() <= pd.Timedelta(days=1)]
                if len(cand) != 1:
                    continue
                x = cand.iloc[0]
            out.append(dict(ticker=r.ticker, league=lg, event_id=x.event_id, start=x.start, home=home, away=away,
                            side_is_home=r.side_is_home, result=r.result, volume=r.volume, y_home=x.y,
                            p_open_shin=x.p_open_shin, p_close_shin=x.p_close_shin, p_model=x.p_model,
                            p_blend_open=x.p_blend_open, p_blend=x.p_blend))
    j = pd.DataFrame(out)
    # per-side probabilities and outcome
    s = np.where(j.side_is_home, 1.0, -1.0)
    for c in ("p_open_shin", "p_close_shin", "p_model", "p_blend_open", "p_blend"):
        j[f"{c}_side"] = np.where(j.side_is_home, j[c], 1 - j[c])
    j["y_side"] = np.where(j.side_is_home, j.y_home, 1 - j.y_home)
    j["y_kalshi"] = (j.result == "yes").astype(float)
    j["date"] = j.start.dt.floor("D").values.astype("datetime64[D]")
    # candles -> price at each horizon and the pre-start close
    cd = cd.sort_values(["ticker", "end_ts"])
    by = {t: d for t, d in cd.groupby("ticker")}
    start_ts = (j.start.astype("int64") // 10 ** 9).values
    for h in H_ALL:
        asks, bids = np.full(len(j), np.nan), np.full(len(j), np.nan)
        for i, (t, st) in enumerate(zip(j.ticker, start_ts)):
            d = by.get(t)
            if d is None:
                continue
            d = d[(d.end_ts <= st - h * 3600) & d.bid.notna() & d.ask.notna()]
            d = d[(d.ask - d.bid) <= MAX_SPREAD]
            if len(d):
                asks[i], bids[i] = d.ask.iloc[-1], d.bid.iloc[-1]
        j[f"ask_{h}"], j[f"bid_{h}"] = asks, bids
    kc = np.full(len(j), np.nan)
    for i, (t, st) in enumerate(zip(j.ticker, start_ts)):
        d = by.get(t)
        if d is None:
            continue
        d = d[(d.end_ts <= st) & d.bid.notna() & d.ask.notna() & ((d.ask - d.bid) <= MAX_SPREAD)]
        if len(d):
            kc[i] = (d.ask.iloc[-1] + d.bid.iloc[-1]) / 2
    j["kalshi_close"] = kc
    return j


POLY_FEE = 0.05
POLY_HALF_SPREAD = 0.01
VENUE_FEE = {"kalshi": FEE, "polymarket": POLY_FEE}


def load_poly_join() -> pd.DataFrame:
    """Polymarket closed moneyline markets -> the same joined frame as join(),
    two side rows per market, prices from the outcome-0 hourly mid."""
    from pl.poly_hist import DB as PDB
    from pl.paper import team_display_names
    c = sqlite3.connect(PDB)
    m = pd.read_sql("SELECT * FROM markets", c)
    pr = pd.read_sql("SELECT * FROM prices", c)
    c.close()
    by = {t: d.sort_values("ts") for t, d in pr.groupby("token")}
    out = []
    for lg in sorted(m.league.unique()):
        g = load_games(lg)
        from pl import espn
        sport, lgx = espn.LEAGUES[lg]
        tj = espn.get(f"{espn.SITE}/{sport}/{lgx}/teams?limit=100")
        abbr_by_name = {t["team"]["displayName"]: t["team"]["abbreviation"] for t in tj["sports"][0]["leagues"][0]["teams"]}
        id_by_name = abbr_by_name
        abbr_by_id = abbr_by_name
        gs = g.copy()
        gs["start_ts"] = gs.start.astype("int64") // 10 ** 9
        for r in m[m.league == lg].itertuples(index=False):
            o = json.loads(r.outcomes)
            if len(o) != 2 or o[0] not in id_by_name or o[1] not in id_by_name:
                continue
            a0, a1 = abbr_by_name[o[0]], abbr_by_name[o[1]]
            t0 = pd.Timestamp(r.game_start.replace(" ", "T")).tz_localize("UTC") if pd.Timestamp(r.game_start.replace(" ", "T")).tz is None else pd.Timestamp(r.game_start.replace(" ", "T"))
            cand = gs[(((gs.home_abbr == a0) & (gs.away_abbr == a1)) | ((gs.home_abbr == a1) & (gs.away_abbr == a0))) &
                      ((gs.start - t0).abs() <= pd.Timedelta(hours=3))]
            if len(cand) != 1:
                continue
            x = cand.iloc[0]
            d = by.get(r.token0)
            if d is None or d.empty:
                continue
            st = int(x.start_ts)
            for side_abbr, is0 in ((a0, True), (a1, False)):
                side_is_home = (x.home_abbr == side_abbr)
                row = dict(ticker=f"{r.condition_id[:10]}:{side_abbr}", league=lg, event_id=x.event_id, start=x.start, home=x.home_abbr,
                           away=x.away_abbr, side_is_home=side_is_home, result=None, volume=r.volume, y_home=x.y,
                           p_open_shin=x.p_open_shin, p_close_shin=x.p_close_shin, p_model=x.p_model,
                           p_blend_open=x.p_blend_open, p_blend=x.p_blend)
                for h in H_ALL:
                    dd = d[d.ts <= st - h * 3600]
                    mid = (dd.p.iloc[-1] if is0 else 1 - dd.p.iloc[-1]) if len(dd) else np.nan
                    row[f"ask_{h}"], row[f"bid_{h}"] = mid + POLY_HALF_SPREAD, mid - POLY_HALF_SPREAD
                dd = d[d.ts <= st]
                row["kalshi_close"] = (dd.p.iloc[-1] if is0 else 1 - dd.p.iloc[-1]) if len(dd) else np.nan
                out.append(row)
    j = pd.DataFrame(out)
    for cname in ("p_open_shin", "p_close_shin", "p_model", "p_blend_open", "p_blend"):
        j[f"{cname}_side"] = np.where(j.side_is_home, j[cname], 1 - j[cname])
    j["y_side"] = np.where(j.side_is_home, j.y_home, 1 - j.y_home)
    j["y_kalshi"] = j.y_side
    j["date"] = j.start.dt.floor("D").values.astype("datetime64[D]")
    return j


def net_dec(ask: np.ndarray, fee: float = FEE) -> np.ndarray:
    return 1.0 / (ask + fee * ask * (1 - ask))


def rule(j: pd.DataFrame, p_col: str, h: int, B: int = 2000, seed: int = 0, fee: float = FEE) -> dict:
    """Buy one $1 contract of a side at its ask when p_side * net_dec - 1 > EDGE_MIN."""
    a = j[f"ask_{h}"].values
    p = j[f"{p_col}_side"].values
    ok = np.isfinite(a) & np.isfinite(p) & (a > 0) & (a < 1)
    dec = net_dec(np.where(ok, a, 0.5), fee)
    edge = p * dec - 1
    bet = ok & (edge > EDGE_MIN)
    y = j.y_side.values
    pnl = np.where(bet, np.where(y == 1, dec - 1, -1.0), 0.0)
    stake = bet.astype(float)
    clv = np.where(bet, j.kalshi_close.values - a, np.nan)
    n = int(bet.sum())
    out = dict(p=p_col, h=h, n_quoted=int(ok.sum()), n_bets=n, games=int(j.event_id.nunique()))
    if n == 0:
        return out
    dates = j.date.values
    roi = lambda idx: pnl[idx].sum() / max(stake[idx].sum(), 1e-9)  # noqa: E731
    bs = stats.cluster_bootstrap(roi, dates, B, seed)
    cl = lambda idx: np.nanmean(np.where(bet[idx], clv[idx], np.nan)) if bet[idx].any() else 0.0  # noqa: E731
    bc = stats.cluster_bootstrap(cl, dates, B, seed + 1)
    out.update(roi=roi(np.arange(len(j))), roi_ci=(np.percentile(bs, 2.5), np.percentile(bs, 97.5)),
               roi_lo975=np.percentile(bs, 1.25), hit=float(y[bet].mean()), avg_ask=float(a[bet].mean()),
               avg_edge=float(edge[bet].mean()), clv=float(np.nanmean(clv)), clv_ci=(np.percentile(bc, 2.5), np.percentile(bc, 97.5)),
               clv_lo975=np.percentile(bc, 1.25), clv_pos=float(np.mean(clv[bet] > 0)))
    return out


def _f(x, nd=4):
    return "nan" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def render(j: pd.DataFrame, res: list[dict], prim: list[dict]) -> str:
    L = [f"# Kalshi lag test — {datetime.now(timezone.utc).isoformat(timespec='seconds')}", "",
         f"Pre-registration: docs/PREREG_KALSHI_LAG.md. Joined {len(j)} Kalshi side-markets = {j.event_id.nunique()} games "
         f"({', '.join(f'{lg} {n}' for lg, n in j.groupby('league').event_id.nunique().items())}); "
         f"Kalshi result agrees with ESPN outcome on {float((j.y_kalshi == j.y_side).mean()):.4f} of sides.", "",
         "## Primaries (h = 3 h, edge > 0.02 after the 0.07·p(1−p) taker fee, one $1 contract per bet)", "",
         "| test | p used | quoted | bets | ROI | 95% CI | ROI lo(97.5%) | CLV | CLV 95% CI | CLV lo(97.5%) | hit | avg ask | PASS |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in zip(("P1 sportsbook OPEN", "P2 model blend (open)"), prim):
        if r.get("n_bets", 0) == 0:
            L.append(f"| {name} | {r['p']} | {r['n_quoted']} | 0 | — | — | — | — | — | — | — | — | FAIL (no bets) |")
            continue
        ok = r["roi_lo975"] > 0 and r["clv_lo975"] > 0
        L.append(f"| {name} | {r['p']} | {r['n_quoted']} | {r['n_bets']} | {_f(r['roi'])} | [{_f(r['roi_ci'][0])}, {_f(r['roi_ci'][1])}] | "
                 f"{_f(r['roi_lo975'])} | {_f(r['clv'])} | [{_f(r['clv_ci'][0])}, {_f(r['clv_ci'][1])}] | {_f(r['clv_lo975'])} | "
                 f"{_f(r['hit'],3)} | {_f(r['avg_ask'],3)} | **{'PASS' if ok else 'FAIL'}** |")
    L += ["", "## Diagnostics (not scored): every horizon, every reference probability, incl. the CLOSE which is not knowable at h", "",
          "| p used | h | quoted | bets | ROI | 95% CI | CLV | CLV 95% CI | CLV>0 share | hit | avg ask |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        if r.get("n_bets", 0) == 0:
            L.append(f"| {r['p']} | {r['h']} | {r['n_quoted']} | 0 | — | — | — | — | — | — | — |")
            continue
        L.append(f"| {r['p']} | {r['h']} | {r['n_quoted']} | {r['n_bets']} | {_f(r['roi'])} | [{_f(r['roi_ci'][0])}, {_f(r['roi_ci'][1])}] | "
                 f"{_f(r['clv'])} | [{_f(r['clv_ci'][0])}, {_f(r['clv_ci'][1])}] | {_f(r['clv_pos'],3)} | {_f(r['hit'],3)} | {_f(r['avg_ask'],3)} |")
    # how stale is Kalshi? mean |ask_h - close| and correlation of Kalshi mid with the sportsbook at each horizon
    L += ["", "## How far Kalshi's price sits from where it ends (all quoted sides)", "", "| h | quoted | mean(mid_h − kalshi_close) | mean abs | corr(mid_h, book close) | corr(mid_h, book open) | mean spread |", "|---|---|---|---|---|---|---|"]
    for h in H_ALL:
        a, b = j[f"ask_{h}"].values, j[f"bid_{h}"].values
        ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(j.kalshi_close.values)
        mid = (a + b) / 2
        if ok.sum() < 10:
            continue
        L.append(f"| {h} | {int(ok.sum())} | {_f(np.mean(mid[ok] - j.kalshi_close.values[ok]))} | {_f(np.mean(np.abs(mid[ok] - j.kalshi_close.values[ok])))} | "
                 f"{_f(np.corrcoef(mid[ok], j.p_close_shin_side.values[ok])[0,1],3)} | {_f(np.corrcoef(mid[ok], j.p_open_shin_side.values[ok])[0,1],3)} | {_f(np.mean(a[ok]-b[ok]),3)} |")
    # calibration of Kalshi's own pre-start mid
    L += ["", "## Kalshi pre-start mid, calibration (exact binomial)", "", "| bin | n | mean p | realized | 95% CI | binom p |", "|---|---|---|---|---|---|"]
    ok = np.isfinite(j.kalshi_close.values)
    for c in stats.calibration_table(j.y_side.values[ok], j.kalshi_close.values[ok]):
        L.append(f"| {c['bin']} | {c['n']} | {_f(c['mean_p'],3)} | {_f(c['realized'],3)} | [{_f(c['lo'],3)}, {_f(c['hi'],3)}] | {_f(c['binom_p'],3)} |")
    cox = stats.cox_calibration(j.y_side.values[ok], j.kalshi_close.values[ok], j.date.values[ok])
    L.append(f"\nCox: a={_f(cox['a'],3)} (z {_f(cox['z_a'],2)}), b={_f(cox['b'],3)} (z vs 1 {_f(cox['z_b'],2)})")
    return "\n".join(L) + "\n"


def main(venue: str = "kalshi"):
    if venue == "kalshi":
        km, cd = load_kalshi()
        j = join(km, cd)
    else:
        j = load_poly_join()
    fee = VENUE_FEE[venue]
    tag = "kalshi" if venue == "kalshi" else "poly"
    j.to_csv(ROOT / "data" / f"{tag}_lag_rows.csv", index=False)
    prim = [rule(j, "p_open_shin", H_PRIMARY, fee=fee), rule(j, "p_blend_open", H_PRIMARY, fee=fee)]
    res = [rule(j, p, h, B=1000, fee=fee) for p in ("p_open_shin", "p_blend_open", "p_model", "p_close_shin", "p_blend") for h in H_ALL]
    md = render(j, res, prim).replace("# Kalshi lag test", f"# {venue} lag test")
    (ROOT / "docs" / f"{tag.upper()}_LAG.md").write_text(md, encoding="utf-8")
    json.dump(dict(venue=venue, primaries=prim, diagnostics=res), open(ROOT / "data" / f"{tag}_lag_results.json", "w"), indent=1, default=float)
    print(md[:3500])


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "kalshi")
