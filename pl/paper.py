"""Paper trading loop. Pre-game, hold to settlement, taker side, one ticket per game.

  python -m pl.paper tickets   # today's slate: model probabilities, every venue's quote, tickets
  python -m pl.paper settle    # settle pending predictions and tickets from ESPN finals
  python -m pl.paper status    # running scoreboard (docs/PAPER_STATUS.md)

Every game on the slate gets a PREDICTION row (model, blend, each venue's price)
whether or not a ticket is written, so the forecast is scored on every game and
the bet rule cannot select its own evidence. Rule and sizes are frozen in
docs/PREREGISTRATION.md.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from pl import backtest, espn, models, stats, store

ROOT = Path(__file__).resolve().parents[1]
J = ROOT / "journal"
PRED = J / "predictions.jsonl"
TICK = J / "tickets.jsonl"
SETTLED = J / "settled.jsonl"

BANKROLL = 1000.0
RULE = stats.BetRule(edge_min=0.02, kelly_frac=0.25, stake_cap=0.02, bankroll=BANKROLL)
KALSHI_FEE = 0.07      # taker fee rate per contract: fee = 0.07 * p * (1-p)   (docs: trading fees)
POLY_FEE = 0.05        # measured live sports taker rate, polymarket/docs/FINDINGS.md section 3
KALSHI_SERIES = {"mlb": "KXMLBGAME", "nhl": "KXNHLGAME", "nba": "KXNBAGAME", "nfl": "KXNFLGAME"}
POLY_TAG = {"mlb": "mlb", "nhl": "nhl", "nba": "nba", "nfl": "nfl"}

_s = requests.Session()
_s.headers["User-Agent"] = "Mozilla/5.0 prediction-lane/0.1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=float) + "\n")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------- slate
def slate(day: date) -> pd.DataFrame:
    rows = []
    for lg in espn.LEAGUES:
        for d in (day, day + timedelta(days=1)):
            for e in espn.scoreboard(lg, d):
                r = espn.parse_event(lg, e)
                if r["status"] != "STATUS_SCHEDULED" or r["season_type"] not in (2, 3):
                    continue
                rows.append(r)
    df = pd.DataFrame(rows).drop_duplicates("event_id")
    if df.empty:
        return df
    df["start"] = pd.to_datetime(df["start"], utc=True)
    now = datetime.now(timezone.utc)
    df = df[(df.start > now) & (df.start < now + timedelta(hours=30))]
    return df.sort_values("start").reset_index(drop=True)


# ---------------------------------------------------------------- model state
def forecast(league: str, upcoming: pd.DataFrame, meta: dict) -> pd.DataFrame:
    """Append the unplayed games to the league's history and run every model
    walk-forward; the last rows are tonight's forecasts. Stacking weights are
    fit on all settled games (ridge 2), market blend likewise."""
    hist = backtest.load(league)
    up = upcoming.copy()
    up["y"] = np.nan
    up["home_score"] = np.nan
    up["away_score"] = np.nan
    up["date"] = up.start.dt.floor("D").values.astype("datetime64[D]")
    for c in ("ml_home", "ml_away", "ml_home_open", "ml_away_open"):
        up[c] = up["live_ml_home"] if c == "ml_home" else (up["live_ml_away"] if c == "ml_away" else np.nan)
        up[f"dec_{c[3:]}"] = stats.american_to_decimal(up[c].values)
    ih, ia = stats.implied(up.dec_home.values), stats.implied(up.dec_away.values)
    up["p_close_prop"] = stats.devig_proportional(ih, ia)
    up["p_close_shin"] = stats.devig_shin(ih, ia)
    up["p_open_shin"] = np.nan
    up["overround_close"] = ih + ia - 1
    df = pd.concat([hist, up[hist.columns.intersection(up.columns)]], ignore_index=True)
    e = meta["elo"]
    df["p_elo"] = models.run_elo(df, e["k"], e["hfa"], e["carry"])
    p_g, mu, sig = models.gaussian_margin_walkforward(df, half_life_days=backtest.GAUSS_HL[league])
    df["p_gauss"], df["mu_gauss"], df["sigma_gauss"] = p_g, mu, sig
    if "poisson" in meta:
        q = meta["poisson"]
        p_p, lh, la = models.run_poisson(df, q["eta"], q["hfa"], q["carry"], q["mu0"])
        df["p_pois"], df["lam_h"], df["lam_a"] = p_p, lh, la
        if league == "mlb":
            ah, aa = models.pitcher_adjustment(df)
            df["pitch_adj_home"], df["pitch_adj_away"] = ah, aa
            lh2, la2 = models.apply_pitcher(lh, la, ah, aa)
            df["p_pois_pitch"] = models.probs_from_lambdas(lh2, la2)
    rh, ra = models.rest_days(df)
    df["rest_diff"] = rh - ra
    F, names = backtest.model_feature_matrix(df, league)
    y = df.y.values
    df["p_model"] = models.walkforward_stack(df, F, y, np.ones(len(df), bool))
    Fb = np.column_stack([stats.logit(df.p_close_shin.values), stats.logit(df.p_model.values)])
    df["p_blend"] = models.walkforward_stack(df, Fb, y, np.ones(len(df), bool))
    out = df.iloc[len(hist):].copy()
    out["feature_names"] = json.dumps(names)
    return out


# ---------------------------------------------------------------- venue quotes
def kalshi_quotes(league: str) -> list[dict]:
    ser = KALSHI_SERIES.get(league)
    if not ser:
        return []
    out, cur = [], ""
    while True:
        j = _s.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                   params=dict(limit=200, status="open", series_ticker=ser, cursor=cur), timeout=30).json()
        out += j.get("markets", [])
        cur = j.get("cursor") or ""
        if not cur:
            break
    return out


def polymarket_quotes(league: str) -> list[dict]:
    tag = POLY_TAG.get(league)
    if not tag:
        return []
    j = _s.get("https://gamma-api.polymarket.com/events", params=dict(limit=200, closed="false", tag_slug=tag), timeout=60).json()
    out = []
    for e in j:
        for m in e.get("markets", []):
            if m.get("sportsMarketType") == "moneyline" and m.get("gameStartTime"):
                out.append(dict(event=e.get("title"), question=m.get("question"), start=m.get("gameStartTime"),
                                outcomes=json.loads(m.get("outcomes") or "[]"), prices=json.loads(m.get("outcomePrices") or "[]"),
                                best_bid=m.get("bestBid"), best_ask=m.get("bestAsk"), liquidity=m.get("liquidityNum"),
                                condition_id=m.get("conditionId"), tokens=json.loads(m.get("clobTokenIds") or "[]")))
    return out


def _abbr_match(abbr: str, name: str, team_names: dict) -> bool:
    return abbr == name or team_names.get(abbr, "").lower() in (name or "").lower() or (name or "").lower() in team_names.get(abbr, "").lower()


KALSHI_ABBR = {"NYY": "New York Y", "NYM": "New York M", "CHW": "Chicago WS", "CWS": "Chicago WS", "CHC": "Chicago C", "LAD": "Los Angeles D",
               "LAA": "Los Angeles A", "SF": "San Francisco", "SD": "San Diego", "TB": "Tampa Bay", "KC": "Kansas City", "STL": "St. Louis",
               "WSH": "Washington", "ATH": "Athletics", "AZ": "Arizona", "ARI": "Arizona"}


def match_kalshi(game, markets: list[dict]) -> dict:
    """Both sides' bid/ask for one game. Kalshi tickers end in the team code;
    ESPN codes mostly match (CHW vs CWS, ATH handled)."""
    code = {"CHW": "CWS", "AZ": "ARI"}
    h, a = code.get(game.home_abbr, game.home_abbr), code.get(game.away_abbr, game.away_abbr)
    day = game.start.strftime("%y%b%d").upper()
    cands = [m for m in markets if m["event_ticker"].split("-")[1].startswith(day) and
             (m["event_ticker"].endswith(f"{a}{h}") or m["event_ticker"].endswith(f"{h}{a}"))]
    if not cands:
        # same event may be dated by local time; fall back to team pair only within 36h
        cands = [m for m in markets if (m["event_ticker"].endswith(f"{a}{h}") or m["event_ticker"].endswith(f"{h}{a}"))]
    out = {}
    for m in cands:
        side = m["ticker"].rsplit("-", 1)[1]
        key = "home" if side == h else ("away" if side == a else None)
        if key:
            out[key] = dict(ticker=m["ticker"], bid=float(m["yes_bid_dollars"] or "nan"), ask=float(m["yes_ask_dollars"] or "nan"),
                            last=float(m["last_price_dollars"] or "nan"), volume=float(m.get("volume_fp") or 0))
    return out


POLY_NAMES = {}


def match_polymarket(game, markets: list[dict], team_names: dict) -> dict:
    t0 = game.start
    out = {}
    for m in markets:
        try:
            ts = pd.Timestamp(m["start"].replace(" ", "T")).tz_localize("UTC") if pd.Timestamp(m["start"]).tz is None else pd.Timestamp(m["start"])
        except Exception:  # noqa: BLE001
            continue
        if abs((ts - t0).total_seconds()) > 3 * 3600 or len(m["outcomes"]) != 2:
            continue
        hn, an = team_names.get(game.home_id, ""), team_names.get(game.away_id, "")
        o = m["outcomes"]
        if not ({hn, an} <= {o[0], o[1]} if hn and an else False):
            continue
        i_home = o.index(hn)
        bb, ba = m["best_bid"], m["best_ask"]
        if bb is None or ba is None:
            continue
        # gamma best_bid/best_ask refer to outcome 0's token; outcome 1 is the complement
        q0 = dict(bid=float(bb), ask=float(ba))
        q1 = dict(bid=1 - float(ba), ask=1 - float(bb))
        out["home"] = dict(q0 if i_home == 0 else q1, token=m["tokens"][i_home], condition_id=m["condition_id"], liquidity=m["liquidity"])
        out["away"] = dict(q1 if i_home == 0 else q0, token=m["tokens"][1 - i_home], condition_id=m["condition_id"], liquidity=m["liquidity"])
        break
    return out


def team_display_names(league: str) -> dict:
    sport, lg = espn.LEAGUES[league]
    j = espn.get(f"{espn.SITE}/{sport}/{lg}/teams?limit=100")
    out = {}
    for t in j["sports"][0]["leagues"][0]["teams"]:
        out[str(t["team"]["id"])] = t["team"]["displayName"]
    return out


# ---------------------------------------------------------------- tickets
def price_edge(p: float, ask: float, fee_rate: float) -> tuple[float, float]:
    """Taker buys the side at `ask` on a $1 contract; fee = fee_rate*ask*(1-ask)
    per contract. Returns (net decimal odds, edge = p*dec - 1)."""
    cost = ask + fee_rate * ask * (1 - ask)
    dec = 1.0 / cost
    return dec, p * dec - 1


def tickets(day: date | None = None) -> None:
    day = day or date.today()
    meta_all = {r["league"]: r["meta"] for r in json.load(open(ROOT / "data" / "backtest_results.json"))}
    sl = slate(day)
    seen = {p["event_id"] for p in _read(PRED)}
    if not sl.empty:
        sl = sl[~sl.event_id.isin(seen)].reset_index(drop=True)   # one forecast per game: the first one written
    if sl.empty:
        print("no new scheduled regular/post-season games in the next 30h")
        return
    n_t = 0
    for lg, g in sl.groupby("league"):
        if lg not in meta_all:
            print(f"{lg}: no frozen hyper-parameters (backtest not run); skipped")
            continue
        fc = forecast(lg, g, meta_all[lg])
        km = kalshi_quotes(lg)
        pm = polymarket_quotes(lg)
        names = team_display_names(lg)
        for _, r in fc.iterrows():
            kq, pq = match_kalshi(r, km), match_polymarket(r, pm, names)
            dk = dict(ml_home=r.get("ml_home"), ml_away=r.get("ml_away"), provider=r.get("live_provider"),
                      dec_home=r.get("dec_home"), dec_away=r.get("dec_away"), p_home_shin=r.get("p_close_shin"))
            p_model, p_blend = float(r.p_model) if np.isfinite(r.p_model) else None, float(r.p_blend) if np.isfinite(r.p_blend) else None
            pred = dict(ts=_now(), day=day.isoformat(), league=lg, event_id=r.event_id, start=r.start.isoformat(),
                        home=r.home_abbr, away=r.away_abbr, home_id=r.home_id, away_id=r.away_id,
                        home_prob=r.get("home_prob_name"), away_prob=r.get("away_prob_name"),
                        p_elo=float(r.p_elo), p_gauss=float(r.p_gauss) if np.isfinite(r.p_gauss) else None,
                        p_pois=float(r.p_pois) if "p_pois" in r and np.isfinite(r.p_pois) else None,
                        p_pois_pitch=float(r.p_pois_pitch) if "p_pois_pitch" in r and np.isfinite(r.p_pois_pitch) else None,
                        mu_gauss=float(r.mu_gauss) if np.isfinite(r.mu_gauss) else None, rest_diff=float(r.rest_diff),
                        p_model=p_model, p_blend=p_blend, sportsbook=dk, kalshi=kq, polymarket=pq, status="pending")
            _append(PRED, pred)
            # ticket: best executable price per side across prediction venues, blend probability, pre-registered rule
            if p_blend is None:
                continue
            best = None
            for venue, q, fee in (("kalshi", kq, KALSHI_FEE), ("polymarket", pq, POLY_FEE)):
                for side in ("home", "away"):
                    if side in q and np.isfinite(q[side].get("ask", np.nan)) and 0 < q[side]["ask"] < 1:
                        p = p_blend if side == "home" else 1 - p_blend
                        dec, edge = price_edge(p, q[side]["ask"], fee)
                        if best is None or edge > best["edge"]:
                            best = dict(venue=venue, side=side, ask=q[side]["ask"], dec=dec, edge=edge, p=p)
            if best and best["edge"] > RULE.edge_min:
                b = best["dec"] - 1
                kelly = max((b * best["p"] - (1 - best["p"])) / b, 0)
                stake = round(min(RULE.kelly_frac * kelly, RULE.stake_cap) * RULE.bankroll, 2)
                t = dict(ts=_now(), day=day.isoformat(), league=lg, event_id=r.event_id, start=r.start.isoformat(),
                         home=r.home_abbr, away=r.away_abbr, **best, stake=stake, kelly_full=kelly,
                         p_model=p_model, p_blend=p_blend, p_sportsbook=dk["p_home_shin"], status="pending")
                _append(TICK, t)
                n_t += 1
                print(f"TICKET {lg} {r.away_abbr}@{r.home_abbr} {best['side']} @ {best['venue']} ask {best['ask']:.3f} "
                      f"edge {best['edge']:+.3%} p_blend {best['p']:.3f} stake ${stake}")
            else:
                e = f"{best['edge']:+.3%} ({best['venue']} {best['side']})" if best else "no venue quote"
                print(f"PASS   {lg} {r.away_abbr}@{r.home_abbr} p_model {p_model:.3f} p_blend {p_blend:.3f} "
                      f"book {dk['p_home_shin'] if dk['p_home_shin'] is not None else float('nan'):.3f} best edge {e}")
    print(f"{len(sl)} games on slate, {n_t} tickets")


# ---------------------------------------------------------------- settlement
def settle() -> None:
    preds = _read(PRED)
    ticks = _read(TICK)
    done = {(r["kind"], r["event_id"]) for r in _read(SETTLED)}
    finals: dict[str, dict] = {}
    pending = [p for p in preds if ("pred", p["event_id"]) not in done] + [t for t in ticks if ("ticket", t["event_id"]) not in done]
    days = {(p["league"], pd.Timestamp(p["start"]).date()) for p in pending}
    for lg, d in days:
        for dd in (d, d + timedelta(days=1)):
            for e in espn.scoreboard(lg, dd):
                r = espn.parse_event(lg, e)
                if r["completed"] and r["home_score"] is not None:
                    finals[r["event_id"]] = r
    n = 0
    for p in preds:
        if ("pred", p["event_id"]) in done or p["event_id"] not in finals:
            continue
        f = finals[p["event_id"]]
        if f["home_score"] == f["away_score"]:
            continue
        y = 1.0 if f["home_score"] > f["away_score"] else 0.0
        row = dict(kind="pred", ts=_now(), event_id=p["event_id"], league=p["league"], day=p["day"], y=y,
                   home_score=f["home_score"], away_score=f["away_score"])
        for k in ("p_model", "p_blend", "p_elo", "p_gauss", "p_pois", "p_pois_pitch"):
            if p.get(k) is not None:
                row[f"ll_{k}"] = -np.log(np.clip(p[k] if y == 1 else 1 - p[k], 1e-6, 1))
        pb = (p.get("sportsbook") or {}).get("p_home_shin")
        if pb is not None and np.isfinite(pb):
            row["ll_book"] = -np.log(np.clip(pb if y == 1 else 1 - pb, 1e-6, 1))
        for venue in ("kalshi", "polymarket"):
            q = p.get(venue) or {}
            if "home" in q and "away" in q and np.isfinite(q["home"].get("ask", np.nan)) and np.isfinite(q["away"].get("ask", np.nan)):
                ph = q["home"]["ask"] / (q["home"]["ask"] + q["away"]["ask"])
                row[f"ll_{venue}"] = -np.log(np.clip(ph if y == 1 else 1 - ph, 1e-6, 1))
        _append(SETTLED, row)
        n += 1
    for t in ticks:
        if ("ticket", t["event_id"]) in done or t["event_id"] not in finals:
            continue
        f = finals[t["event_id"]]
        if f["home_score"] == f["away_score"]:
            continue
        home_won = f["home_score"] > f["away_score"]
        won = home_won if t["side"] == "home" else not home_won
        pnl = t["stake"] * (t["dec"] - 1) if won else -t["stake"]
        _append(SETTLED, dict(kind="ticket", ts=_now(), event_id=t["event_id"], league=t["league"], day=t["day"],
                              venue=t["venue"], side=t["side"], stake=t["stake"], dec=t["dec"], won=bool(won), pnl=round(pnl, 2)))
        n += 1
    print(f"settled {n} rows")
    status()


def status() -> None:
    rows = _read(SETTLED)
    preds = [r for r in rows if r["kind"] == "pred"]
    ticks = [r for r in rows if r["kind"] == "ticket"]
    L = [f"# paper status — {_now()}", "", f"predictions settled: {len(preds)}   tickets settled: {len(ticks)}   "
         f"pending tickets: {len(_read(TICK)) - len(ticks)}", ""]
    if preds:
        d = pd.DataFrame(preds)
        L += ["| forecast | n | mean log-loss |", "|---|---|---|"]
        for c in [c for c in d.columns if c.startswith("ll_")]:
            L.append(f"| {c[3:]} | {d[c].notna().sum()} | {d[c].mean():.4f} |")
        L.append("")
        L.append("Paired (book − model) log-loss, positive = model better: "
                 + (f"{(d.ll_book - d.ll_model).mean():+.4f} on {int((d.ll_book.notna() & d.ll_model.notna()).sum())} games"
                    if "ll_book" in d and "ll_model" in d else "n/a"))
    cl = [r for r in rows if r["kind"] == "clv"]
    if cl:
        c = pd.DataFrame(cl)
        L.append(f"CLV vs Kalshi pre-start mid: forecast side mean {c.forecast_clv.mean():+.4f} on {len(c)} games "
                 f"(share > 0: {(c.forecast_clv > 0).mean():.3f})"
                 + (f"; tickets mean {c.ticket_clv.mean():+.4f} on {c.ticket_clv.notna().sum()}" if "ticket_clv" in c and c.ticket_clv.notna().any() else ""))
    if ticks:
        t = pd.DataFrame(ticks)
        cum = t.pnl.cumsum()
        dd = (cum - cum.cummax()).min()
        L += ["", f"tickets: {len(t)}  staked ${t.stake.sum():.2f}  pnl ${t.pnl.sum():+.2f}  ROI {t.pnl.sum() / t.stake.sum():+.3%}  "
              f"hit {t.won.mean():.3f}  max drawdown ${dd:.2f}  avg win ${t[t.pnl > 0].pnl.mean() if (t.pnl > 0).any() else 0:.2f}  "
              f"avg loss ${t[t.pnl < 0].pnl.mean() if (t.pnl < 0).any() else 0:.2f}"]
        by = t.groupby("day").pnl.sum()
        L.append(f"days positive: {(by > 0).sum()}/{len(by)}")
    (ROOT / "docs" / "PAPER_STATUS.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- quote snapshots (lead-lag dataset) and CLV
SNAP = J / "quotes.jsonl"


def snapshot() -> None:
    """Hourly: every pending prediction's Kalshi/Polymarket quotes and the DraftKings
    line right now. Builds the forward lead-lag dataset the backtest cannot supply."""
    pend = [p for p in _read(PRED) if pd.Timestamp(p["start"]) > pd.Timestamp.now(tz="UTC")]
    if not pend:
        print("no pending games")
        return
    by_lg: dict[str, list[dict]] = {}
    for p in pend:
        by_lg.setdefault(p["league"], []).append(p)
    n = 0
    for lg, ps in by_lg.items():
        km, pm, names = kalshi_quotes(lg), polymarket_quotes(lg), team_display_names(lg)
        live = {}
        for d in {pd.Timestamp(p["start"]).date() for p in ps}:
            for e in espn.scoreboard(lg, d):
                r = espn.parse_event(lg, e)
                live[r["event_id"]] = r
        for p in ps:
            g = pd.Series(dict(home_abbr=p["home"], away_abbr=p["away"], home_id=p["home_id"], away_id=p["away_id"],
                               start=pd.Timestamp(p["start"])))
            r = live.get(p["event_id"], {})
            _append(SNAP, dict(ts=_now(), event_id=p["event_id"], league=lg, start=p["start"],
                               hours_to_start=round((pd.Timestamp(p["start"]) - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600, 2),
                               kalshi=match_kalshi(g, km), polymarket=match_polymarket(g, pm, names),
                               sportsbook=dict(ml_home=r.get("live_ml_home"), ml_away=r.get("live_ml_away"), provider=r.get("live_provider"))))
            n += 1
    print(f"snapshot: {n} games")


def clv() -> None:
    """Closing-line value for every settled ticket and every forecast: the Kalshi
    pre-start mid minus the price we paid (ticket) or the price that was available
    when the forecast was written (forecast side = the blend's favoured side)."""
    from pl.kalshi_hist import candles as kcandles
    rows = _read(SETTLED)
    done = {r["event_id"] for r in rows if r["kind"] == "clv"}
    preds = {p["event_id"]: p for p in _read(PRED)}
    ticks = {t["event_id"]: t for t in _read(TICK)}
    n = 0
    for ev, p in preds.items():
        if ev in done or pd.Timestamp(p["start"]) > pd.Timestamp.now(tz="UTC"):
            continue
        kq = p.get("kalshi") or {}
        if "home" not in kq:
            continue
        tk = kq["home"]["ticker"]
        ser = tk.split("-")[0]
        try:
            cs = kcandles(ser, tk, (pd.Timestamp(p["start"]) - pd.Timedelta(days=14)).isoformat(), pd.Timestamp(p["start"]).isoformat())
        except Exception as e:  # noqa: BLE001
            print(f"  clv {tk} ERR {e}")
            continue
        st = int(pd.Timestamp(p["start"]).timestamp())
        pre = [c for c in cs if c[1] <= st and c[2] is not None and c[3] is not None and (c[3] - c[2]) <= 0.10]
        if not pre:
            continue
        close_home = (pre[-1][2] + pre[-1][3]) / 2
        side = "home" if (p.get("p_blend") or 0.5) >= 0.5 else "away"
        paid = kq[side]["ask"]
        close_side = close_home if side == "home" else 1 - close_home
        row = dict(kind="clv", ts=_now(), event_id=ev, league=p["league"], day=p["day"], forecast_side=side,
                   forecast_ask=paid, kalshi_close_side=close_side, forecast_clv=round(close_side - paid, 4))
        t = ticks.get(ev)
        if t and t.get("venue") == "kalshi":
            tc = close_home if t["side"] == "home" else 1 - close_home
            row.update(ticket_side=t["side"], ticket_ask=t["ask"], ticket_clv=round(tc - t["ask"], 4))
        _append(SETTLED, row)
        n += 1
    print(f"clv rows: {n}")


def main(argv=None):
    a = argv or sys.argv[1:]
    cmd = a[0] if a else "tickets"
    if cmd == "tickets":
        tickets(date.fromisoformat(a[1]) if len(a) > 1 else None)
    elif cmd == "settle":
        clv()
        settle()
    elif cmd == "status":
        status()
    elif cmd == "snapshot":
        snapshot()
    elif cmd == "clv":
        clv()
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
