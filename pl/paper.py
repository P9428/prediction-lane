"""Paper trading loop. Pre-game, hold to settlement, taker side, one ticket per game.

  python -m pl paper tickets [DAY]   # today's slate: model probabilities, every venue's quote, tickets
  python -m pl paper settle          # CLV, then settle pending predictions and tickets from ESPN finals
  python -m pl paper status          # running scoreboard (docs/PAPER_STATUS.md)
  python -m pl paper snapshot        # hourly venue quotes for every pending game (lead-lag dataset)
  python -m pl paper clv             # closing-line value only

Every game on the slate gets a PREDICTION row (model, blend, each venue's price)
whether or not a ticket is written, so the forecast is scored on every game and
the bet rule cannot select its own evidence. Rule and sizes are frozen in
docs/PREREGISTRATION.md.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd

from pl import backtest, espn, http, models, stats
from pl.core import DATA, DOCS, JOURNAL, append_jsonl, configure_logging, finite, load_json, log, read_jsonl, utc_now, write_text

PRED = JOURNAL / "predictions.jsonl"
TICK = JOURNAL / "tickets.jsonl"
SETTLED = JOURNAL / "settled.jsonl"
SNAP = JOURNAL / "quotes.jsonl"
STATUS_MD = DOCS / "PAPER_STATUS.md"
BACKTEST_RESULTS = DATA / "backtest_results.json"

BANKROLL = 1000.0
RULE = stats.BetRule(edge_min=0.02, kelly_frac=0.25, stake_cap=0.02, bankroll=BANKROLL)
KALSHI_FEE = 0.07      # taker fee rate per contract: fee = 0.07 * p * (1-p)   (docs: trading fees)
POLY_FEE = 0.05        # measured live sports taker rate, polymarket/docs/FINDINGS.md section 3
VENUE_FEE = {"kalshi": KALSHI_FEE, "polymarket": POLY_FEE}
KALSHI_SERIES = {"mlb": "KXMLBGAME", "nhl": "KXNHLGAME", "nba": "KXNBAGAME", "nfl": "KXNFLGAME"}
POLY_TAG = {"mlb": "mlb", "nhl": "nhl", "nba": "nba", "nfl": "nfl"}
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_API = "https://gamma-api.polymarket.com"
SLATE_HORIZON = timedelta(hours=30)
LOG_LOSS_FLOOR = 1e-6
FORECAST_COLS = ("p_model", "p_blend", "p_elo", "p_gauss", "p_pois", "p_pois_pitch")


def _now_ts() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


# ---------------------------------------------------------------- slate
def slate(day: date) -> pd.DataFrame:
    """Scheduled regular/post-season games starting within the horizon, all leagues."""
    rows = []
    for lg in espn.LEAGUES:
        for d in (day, day + timedelta(days=1)):
            for e in espn.scoreboard(lg, d):
                r = espn.parse_event(lg, e)
                if r["status"] == "STATUS_SCHEDULED" and r["season_type"] in (2, 3):
                    rows.append(r)
    df = pd.DataFrame(rows).drop_duplicates("event_id")
    if df.empty:
        return df
    df["start"] = pd.to_datetime(df["start"], utc=True)
    now = datetime.now(UTC)
    df = df[(df.start > now) & (df.start < now + SLATE_HORIZON)]
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
        j = http.get_json(f"{KALSHI_API}/markets", dict(limit=200, status="open", series_ticker=ser, cursor=cur), fatal=())
        out += j.get("markets", [])
        cur = j.get("cursor") or ""
        if not cur:
            return out


def polymarket_quotes(league: str) -> list[dict]:
    tag = POLY_TAG.get(league)
    if not tag:
        return []
    events = http.get_json(f"{GAMMA_API}/events", dict(limit=200, closed="false", tag_slug=tag), timeout=60, fatal=())
    return [dict(event=e.get("title"), question=m.get("question"), start=m.get("gameStartTime"),
                 outcomes=json.loads(m.get("outcomes") or "[]"), prices=json.loads(m.get("outcomePrices") or "[]"),
                 best_bid=m.get("bestBid"), best_ask=m.get("bestAsk"), liquidity=m.get("liquidityNum"),
                 condition_id=m.get("conditionId"), tokens=json.loads(m.get("clobTokenIds") or "[]"))
            for e in events for m in e.get("markets", [])
            if m.get("sportsMarketType") == "moneyline" and m.get("gameStartTime")]


KALSHI_CODE = {"CHW": "CWS", "AZ": "ARI"}   # ESPN abbreviation -> Kalshi team code where they differ


def match_kalshi(game, markets: list[dict]) -> dict:
    """Both sides' bid/ask for one game. Kalshi tickers end in the team code;
    the event ticker carries the local date, so the date match falls back to the
    team pair alone (the quote feed only holds open markets, i.e. within ~36h)."""
    h, a = KALSHI_CODE.get(game.home_abbr, game.home_abbr), KALSHI_CODE.get(game.away_abbr, game.away_abbr)
    day = game.start.strftime("%y%b%d").upper()

    def pair(m: dict) -> bool:
        return m["event_ticker"].endswith(f"{a}{h}") or m["event_ticker"].endswith(f"{h}{a}")

    cands = [m for m in markets if pair(m) and m["event_ticker"].split("-")[1].startswith(day)] or [m for m in markets if pair(m)]
    out = {}
    for m in cands:
        side = m["ticker"].rsplit("-", 1)[1]
        key = "home" if side == h else ("away" if side == a else None)
        if key:
            out[key] = dict(ticker=m["ticker"], bid=float(m["yes_bid_dollars"] or "nan"), ask=float(m["yes_ask_dollars"] or "nan"),
                            last=float(m["last_price_dollars"] or "nan"), volume=float(m.get("volume_fp") or 0))
    return out


def _poly_start(raw: str) -> pd.Timestamp | None:
    try:
        ts = pd.Timestamp(raw)
        return pd.Timestamp(raw.replace(" ", "T")).tz_localize("UTC") if ts.tz is None else ts
    except (ValueError, TypeError):
        return None


def match_polymarket(game, markets: list[dict], team_names: dict) -> dict:
    """Both sides' bid/ask for one game from the Gamma moneyline list: same two
    display names, start within 3h. Gamma's best_bid/best_ask refer to outcome 0's
    token; outcome 1 is the complement."""
    hn, an = team_names.get(game.home_id, ""), team_names.get(game.away_id, "")
    if not (hn and an):
        return {}
    for m in markets:
        ts = _poly_start(m["start"])
        if ts is None or abs((ts - game.start).total_seconds()) > 3 * 3600 or len(m["outcomes"]) != 2:
            continue
        o = m["outcomes"]
        if not ({hn, an} <= {o[0], o[1]}):
            continue
        bb, ba = m["best_bid"], m["best_ask"]
        if bb is None or ba is None:
            continue
        i_home = o.index(hn)
        q0 = dict(bid=float(bb), ask=float(ba))
        q1 = dict(bid=1 - float(ba), ask=1 - float(bb))
        meta = dict(condition_id=m["condition_id"], liquidity=m["liquidity"])
        return {"home": dict(q0 if i_home == 0 else q1, token=m["tokens"][i_home], **meta),
                "away": dict(q1 if i_home == 0 else q0, token=m["tokens"][1 - i_home], **meta)}
    return {}


def team_display_names(league: str) -> dict:
    return espn.teams(league, "id", "displayName")


# ---------------------------------------------------------------- pricing and sizing
def price_edge(p: float, ask: float, fee_rate: float) -> tuple[float, float]:
    """Taker buys the side at `ask` on a $1 contract; fee = fee_rate*ask*(1-ask)
    per contract. Returns (net decimal odds, edge = p*dec - 1)."""
    cost = ask + fee_rate * ask * (1 - ask)
    dec = 1.0 / cost
    return dec, p * dec - 1


def best_price(p_home: float, quotes: dict[str, dict]) -> dict | None:
    """Highest-edge executable side across venues for the blend probability."""
    best = None
    for venue, q in quotes.items():
        for side in ("home", "away"):
            ask = (q.get(side) or {}).get("ask", np.nan)
            if not (np.isfinite(ask) and 0 < ask < 1):
                continue
            p = p_home if side == "home" else 1 - p_home
            dec, edge = price_edge(p, ask, VENUE_FEE[venue])
            if best is None or edge > best["edge"]:
                best = dict(venue=venue, side=side, ask=ask, dec=dec, edge=edge, p=p)
    return best


def kelly_stake(p: float, dec: float, rule: stats.BetRule = RULE) -> tuple[float, float]:
    """(full Kelly fraction, dollar stake under the pre-registered fraction and cap)."""
    b = dec - 1
    kelly = max((b * p - (1 - p)) / b, 0)
    return kelly, round(min(rule.kelly_frac * kelly, rule.stake_cap) * rule.bankroll, 2)


# ---------------------------------------------------------------- tickets
def tickets(day: date | None = None) -> None:
    day = day or date.today()
    meta_all = {r["league"]: r["meta"] for r in load_json(BACKTEST_RESULTS)}
    sl = slate(day)
    seen = {p["event_id"] for p in read_jsonl(PRED)}
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
        km, pm, names = kalshi_quotes(lg), polymarket_quotes(lg), team_display_names(lg)
        for _, r in fc.iterrows():
            kq, pq = match_kalshi(r, km), match_polymarket(r, pm, names)
            dk = dict(ml_home=r.get("ml_home"), ml_away=r.get("ml_away"), provider=r.get("live_provider"),
                      dec_home=r.get("dec_home"), dec_away=r.get("dec_away"), p_home_shin=r.get("p_close_shin"))
            p_model, p_blend = finite(r.p_model), finite(r.p_blend)
            append_jsonl(PRED, dict(
                ts=utc_now(), day=day.isoformat(), league=lg, event_id=r.event_id, start=r.start.isoformat(),
                home=r.home_abbr, away=r.away_abbr, home_id=r.home_id, away_id=r.away_id,
                home_prob=r.get("home_prob_name"), away_prob=r.get("away_prob_name"),
                p_elo=float(r.p_elo), p_gauss=finite(r.p_gauss), p_pois=finite(r.get("p_pois")), p_pois_pitch=finite(r.get("p_pois_pitch")),
                mu_gauss=finite(r.mu_gauss), rest_diff=float(r.rest_diff),
                p_model=p_model, p_blend=p_blend, sportsbook=dk, kalshi=kq, polymarket=pq, status="pending"))
            if p_blend is None:
                continue
            # ticket: best executable price per side across prediction venues, blend probability, pre-registered rule
            best = best_price(p_blend, {"kalshi": kq, "polymarket": pq})
            if best and best["edge"] > RULE.edge_min:
                kelly, stake = kelly_stake(best["p"], best["dec"])
                append_jsonl(TICK, dict(ts=utc_now(), day=day.isoformat(), league=lg, event_id=r.event_id, start=r.start.isoformat(),
                                        home=r.home_abbr, away=r.away_abbr, **best, stake=stake, kelly_full=kelly,
                                        p_model=p_model, p_blend=p_blend, p_sportsbook=dk["p_home_shin"], status="pending"))
                n_t += 1
                print(f"TICKET {lg} {r.away_abbr}@{r.home_abbr} {best['side']} @ {best['venue']} ask {best['ask']:.3f} "
                      f"edge {best['edge']:+.3%} p_blend {best['p']:.3f} stake ${stake}")
            else:
                e = f"{best['edge']:+.3%} ({best['venue']} {best['side']})" if best else "no venue quote"
                book = dk["p_home_shin"] if dk["p_home_shin"] is not None else float("nan")
                print(f"PASS   {lg} {r.away_abbr}@{r.home_abbr} p_model {p_model:.3f} p_blend {p_blend:.3f} book {book:.3f} best edge {e}")
    print(f"{len(sl)} games on slate, {n_t} tickets")


# ---------------------------------------------------------------- settlement
def log_loss(p: float, y: float) -> float:
    return float(-np.log(np.clip(p if y == 1 else 1 - p, LOG_LOSS_FLOOR, 1)))


def finals(days: set[tuple[str, date]]) -> dict[str, dict]:
    """Completed games with scores for every (league, UTC date) needed. ESPN files a
    game under its US date, so the day before and after are read too."""
    out: dict[str, dict] = {}
    for lg, d in days:
        for dd in (d - timedelta(days=1), d, d + timedelta(days=1)):
            for e in espn.scoreboard(lg, dd):
                r = espn.parse_event(lg, e)
                if r["completed"] and r["home_score"] is not None:
                    out[r["event_id"]] = r
    return out


def _venue_ll(q: dict, y: float) -> float | None:
    """Log-loss of a venue's own two-sided ask, normalised to a probability."""
    h, a = (q.get("home") or {}).get("ask", np.nan), (q.get("away") or {}).get("ask", np.nan)
    if not (np.isfinite(h) and np.isfinite(a)):
        return None
    return log_loss(h / (h + a), y)


def settle() -> None:
    preds, ticks = read_jsonl(PRED), read_jsonl(TICK)
    done = {(r["kind"], r["event_id"]) for r in read_jsonl(SETTLED)}
    pending = [p for p in preds if ("pred", p["event_id"]) not in done] + [t for t in ticks if ("ticket", t["event_id"]) not in done]
    fin = finals({(p["league"], pd.Timestamp(p["start"]).date()) for p in pending})

    def result(kind: str, row: dict) -> dict | None:
        if (kind, row["event_id"]) in done or row["event_id"] not in fin:
            return None
        f = fin[row["event_id"]]
        return None if f["home_score"] == f["away_score"] else f   # ties (NFL) are void, never settled

    n = 0
    for p in preds:
        if (f := result("pred", p)) is None:
            continue
        y = 1.0 if f["home_score"] > f["away_score"] else 0.0
        row = dict(kind="pred", ts=utc_now(), event_id=p["event_id"], league=p["league"], day=p["day"], y=y,
                   home_score=f["home_score"], away_score=f["away_score"])
        row.update({f"ll_{k}": log_loss(p[k], y) for k in FORECAST_COLS if p.get(k) is not None})
        pb = (p.get("sportsbook") or {}).get("p_home_shin")
        if pb is not None and np.isfinite(pb):
            row["ll_book"] = log_loss(pb, y)
        for venue in VENUE_FEE:
            if (ll := _venue_ll(p.get(venue) or {}, y)) is not None:
                row[f"ll_{venue}"] = ll
        append_jsonl(SETTLED, row)
        n += 1
    for t in ticks:
        if (f := result("ticket", t)) is None:
            continue
        home_won = f["home_score"] > f["away_score"]
        won = home_won if t["side"] == "home" else not home_won
        pnl = t["stake"] * (t["dec"] - 1) if won else -t["stake"]
        append_jsonl(SETTLED, dict(kind="ticket", ts=utc_now(), event_id=t["event_id"], league=t["league"], day=t["day"],
                                   venue=t["venue"], side=t["side"], stake=t["stake"], dec=t["dec"], won=bool(won), pnl=round(pnl, 2)))
        n += 1
    print(f"settled {n} rows")
    status()


def status() -> str:
    rows = read_jsonl(SETTLED)
    preds = [r for r in rows if r["kind"] == "pred"]
    ticks = [r for r in rows if r["kind"] == "ticket"]
    L = [f"# paper status — {utc_now()}", "", f"predictions settled: {len(preds)}   tickets settled: {len(ticks)}   "
         f"pending tickets: {len(read_jsonl(TICK)) - len(ticks)}", ""]
    if preds:
        d = pd.DataFrame(preds)
        L += ["| forecast | n | mean log-loss |", "|---|---|---|"]
        L += [f"| {c[3:]} | {d[c].notna().sum()} | {d[c].mean():.4f} |" for c in d.columns if c.startswith("ll_")]
        L.append("")
        paired = (f"{(d.ll_book - d.ll_model).mean():+.4f} on {int((d.ll_book.notna() & d.ll_model.notna()).sum())} games"
                  if "ll_book" in d and "ll_model" in d else "n/a")
        L.append(f"Paired (book − model) log-loss, positive = model better: {paired}")
    cl = [r for r in rows if r["kind"] == "clv"]
    if cl:
        c = pd.DataFrame(cl)
        L.append(f"CLV vs Kalshi pre-start mid: forecast side mean {c.forecast_clv.mean():+.4f} on {len(c)} games "
                 f"(share > 0: {(c.forecast_clv > 0).mean():.3f})"
                 + (f"; tickets mean {c.ticket_clv.mean():+.4f} on {c.ticket_clv.notna().sum()}"
                    if "ticket_clv" in c and c.ticket_clv.notna().any() else ""))
    if ticks:
        t = pd.DataFrame(ticks)
        cum = t.pnl.cumsum()
        dd = (cum - cum.cummax()).min()
        L += ["", f"tickets: {len(t)}  staked ${t.stake.sum():.2f}  pnl ${t.pnl.sum():+.2f}  ROI {t.pnl.sum() / t.stake.sum():+.3%}  "
              f"hit {t.won.mean():.3f}  max drawdown ${dd:.2f}  avg win ${t[t.pnl > 0].pnl.mean() if (t.pnl > 0).any() else 0:.2f}  "
              f"avg loss ${t[t.pnl < 0].pnl.mean() if (t.pnl < 0).any() else 0:.2f}"]
        by = t.groupby("day").pnl.sum()
        L.append(f"days positive: {(by > 0).sum()}/{len(by)}")
    text = "\n".join(L) + "\n"
    write_text(STATUS_MD, text)
    print(text, end="")
    return text


# ---------------------------------------------------------------- quote snapshots (lead-lag dataset) and CLV
def snapshot() -> None:
    """Hourly: every pending prediction's Kalshi/Polymarket quotes and the DraftKings
    line right now. Builds the forward lead-lag dataset the backtest cannot supply."""
    now = _now_ts()
    pend = [p for p in read_jsonl(PRED) if pd.Timestamp(p["start"]) > now]
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
            start = pd.Timestamp(p["start"])
            g = pd.Series(dict(home_abbr=p["home"], away_abbr=p["away"], home_id=p["home_id"], away_id=p["away_id"], start=start))
            r = live.get(p["event_id"], {})
            append_jsonl(SNAP, dict(ts=utc_now(), event_id=p["event_id"], league=lg, start=p["start"],
                                    hours_to_start=round((start - now).total_seconds() / 3600, 2),
                                    kalshi=match_kalshi(g, km), polymarket=match_polymarket(g, pm, names),
                                    sportsbook=dict(ml_home=r.get("live_ml_home"), ml_away=r.get("live_ml_away"), provider=r.get("live_provider"))))
            n += 1
    print(f"snapshot: {n} games")


def clv() -> None:
    """Closing-line value for every settled ticket and every forecast: the Kalshi
    pre-start mid minus the price we paid (ticket) or the price that was available
    when the forecast was written (forecast side = the blend's favoured side)."""
    from pl.kalshi_hist import candles as kcandles
    rows = read_jsonl(SETTLED)
    done = {r["event_id"] for r in rows if r["kind"] == "clv"}
    ticks = {t["event_id"]: t for t in read_jsonl(TICK)}
    now = _now_ts()
    n = 0
    for p in read_jsonl(PRED):
        ev, start = p["event_id"], pd.Timestamp(p["start"])
        kq = p.get("kalshi") or {}
        if ev in done or start > now or "home" not in kq:
            continue
        tk = kq["home"]["ticker"]
        try:
            cs = kcandles(tk.split("-")[0], tk, (start - pd.Timedelta(days=14)).isoformat(), start.isoformat())
        except Exception as e:  # noqa: BLE001 - one market's history must not block the rest
            log.warning("clv %s: %s", tk, e)
            continue
        st = int(start.timestamp())
        pre = [c for c in cs if c[1] <= st and c[2] is not None and c[3] is not None and (c[3] - c[2]) <= 0.10]
        if not pre:
            continue
        close_home = (pre[-1][2] + pre[-1][3]) / 2
        side = "home" if (p.get("p_blend") or 0.5) >= 0.5 else "away"
        paid = kq[side]["ask"]
        close_side = close_home if side == "home" else 1 - close_home
        row = dict(kind="clv", ts=utc_now(), event_id=ev, league=p["league"], day=p["day"], forecast_side=side,
                   forecast_ask=paid, kalshi_close_side=close_side, forecast_clv=round(close_side - paid, 4))
        t = ticks.get(ev)
        if t and t.get("venue") == "kalshi":
            tc = close_home if t["side"] == "home" else 1 - close_home
            row.update(ticket_side=t["side"], ticket_ask=t["ask"], ticket_clv=round(tc - t["ask"], 4))
        append_jsonl(SETTLED, row)
        n += 1
    print(f"clv rows: {n}")


def main(argv: list[str] | None = None) -> None:
    configure_logging()
    ap = argparse.ArgumentParser(prog="pl paper", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="tickets", choices=("tickets", "settle", "status", "snapshot", "clv"))
    ap.add_argument("day", nargs="?", type=date.fromisoformat, help="slate date for `tickets` (default today)")
    a = ap.parse_args(argv)
    if a.cmd == "tickets":
        tickets(a.day)
    elif a.cmd == "settle":
        clv()
        settle()
    else:
        {"status": status, "snapshot": snapshot, "clv": clv}[a.cmd]()


if __name__ == "__main__":
    main()
