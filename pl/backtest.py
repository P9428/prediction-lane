"""Walk-forward evaluation of past-performance models against the sportsbook line.

usage: python -m pl.backtest [league ...]   (default: all four)

Per league: tuning season = the first season in the store (hyper-parameters are
chosen there and frozen), test = every later regular-season + postseason game
with a closing moneyline. The PRIMARY pre-registered test is the cluster-robust
Wald z on the model's coefficient in logit(y) = a + b*logit(p_close) + c*logit(p_model),
one per league, Bonferroni over four leagues (alpha 0.0125). Everything else is
diagnostic. Outputs docs/RESULTS.md and data/backtest_<league>.csv (per game).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from pl import models, stats, store

ROOT = Path(__file__).resolve().parents[1]
GAUSS_HL = {"mlb": 150.0, "nba": 120.0, "nhl": 150.0, "nfl": 400.0}
RULE = stats.BetRule(edge_min=0.02, kelly_frac=0.25, stake_cap=0.02, bankroll=1000.0)


def load(league: str) -> pd.DataFrame:
    df = store.games(league)
    df = df[df.season_type.isin([2, 3])].copy()
    df = df[(df.home_score != df.away_score)]                    # NFL ties: 1-2 per season, no binary outcome
    df["y"] = (df.home_score > df.away_score).astype(float)
    df["date"] = df.start.dt.floor("D").values.astype("datetime64[D]")
    for c in ("ml_home", "ml_away", "ml_home_open", "ml_away_open"):
        df[f"dec_{c[3:]}"] = stats.american_to_decimal(df[c].values)
    ih, ia = stats.implied(df.dec_home.values), stats.implied(df.dec_away.values)
    df["p_close_prop"] = stats.devig_proportional(ih, ia)
    df["p_close_shin"] = stats.devig_shin(ih, ia)
    ioh, ioa = stats.implied(df.dec_home_open.values), stats.implied(df.dec_away_open.values)
    df["p_open_shin"] = stats.devig_shin(ioh, ioa)
    df["overround_close"] = ih + ia - 1
    return df.reset_index(drop=True)


def fit_models(df: pd.DataFrame, league: str, tune_season: int) -> tuple[pd.DataFrame, dict]:
    tune = df[df.season == tune_season]
    meta = {}
    e = models.tune_elo(tune, league)
    meta["elo"] = e
    df["p_elo"] = models.run_elo(df, e["k"], e["hfa"], e["carry"])
    p_g, mu, sig = models.gaussian_margin_walkforward(df, half_life_days=GAUSS_HL[league])
    df["p_gauss"], df["mu_gauss"], df["sigma_gauss"] = p_g, mu, sig
    if models.LEAGUE_DEFAULTS[league]["score"] == "poisson":
        q = models.tune_poisson(tune)
        meta["poisson"] = q
        p_p, lh, la = models.run_poisson(df, q["eta"], q["hfa"], q["carry"], q["mu0"])
        df["p_pois"], df["lam_h"], df["lam_a"] = p_p, lh, la
        if league == "mlb":
            ah, aa = models.pitcher_adjustment(df)
            df["pitch_adj_home"], df["pitch_adj_away"] = ah, aa
            lh2, la2 = models.apply_pitcher(lh, la, ah, aa)
            df["p_pois_pitch"] = models.probs_from_lambdas(lh2, la2)
    rh, ra = models.rest_days(df)
    df["rest_diff"] = rh - ra
    return df, meta


def model_feature_matrix(df: pd.DataFrame, league: str) -> tuple[np.ndarray, list[str]]:
    cols = ["p_elo", "p_gauss"]
    if "p_pois" in df:
        cols.append("p_pois")
    if "p_pois_pitch" in df:
        cols.append("p_pois_pitch")
    F = [stats.logit(df[c].values) for c in cols]
    names = [f"logit_{c}" for c in cols]
    if "pitch_adj_home" in df:
        F.append(df.pitch_adj_away.values - df.pitch_adj_home.values)   # >0 means home faces the worse pitcher
        names.append("pitch_adj_diff")
    F.append(df.rest_diff.values / 3.0)
    names.append("rest_diff")
    return np.column_stack(F), names


def evaluate(league: str) -> dict:
    df = load(league)
    seasons = sorted(df.season.unique())
    tune_season = seasons[0]
    df, meta = fit_models(df, league, tune_season)
    y = df.y.values
    test = (df.season > tune_season).values & np.isfinite(df.p_close_shin.values) & np.isfinite(df.p_gauss.values)
    F, names = model_feature_matrix(df, league)
    df["p_model"] = models.walkforward_stack(df, F, y, np.ones(len(df), bool))
    Fb = np.column_stack([stats.logit(df.p_close_shin.values), stats.logit(df.p_model.values)])
    df["p_blend"] = models.walkforward_stack(df, Fb, y, np.ones(len(df), bool))
    Fo = np.column_stack([stats.logit(df.p_open_shin.values), stats.logit(df.p_model.values)])
    df["p_blend_open"] = models.walkforward_stack(df, Fo, y, np.ones(len(df), bool))
    t = test & np.isfinite(df.p_model.values) & np.isfinite(df.p_blend.values)
    d = df[t]
    dates = d.date.values
    out = dict(league=league, tune_season=int(tune_season), test_seasons=[int(s) for s in seasons[1:]],
               n_test=int(t.sum()), meta=meta, feature_names=names)
    # --- market calibration and overround
    out["market_cox"] = stats.cox_calibration(d.y.values, d.p_close_shin.values, dates)
    out["market_calib"] = stats.calibration_table(d.y.values, d.p_close_shin.values)
    out["market_hl"] = stats.hosmer_lemeshow(d.y.values, d.p_close_shin.values)
    out["overround_median"] = float(np.nanmedian(d.overround_close))
    # --- each model alone vs market (paired log-loss) and its calibration
    out["models"] = {}
    for c in [n for n in ("p_elo", "p_gauss", "p_pois", "p_pois_pitch", "p_model") if n in d]:
        out["models"][c] = dict(skill=stats.paired_skill(d.y.values, d[c].values, d.p_close_shin.values, dates, B=1000),
                                cox=stats.cox_calibration(d.y.values, d[c].values, dates))
    # --- PRIMARY: incremental information over the closing line
    out["primary_close"] = stats.incremental_information(d.y.values, d.p_close_shin.values, d.p_model.values, dates)
    # secondary: over the opening line (where information edges would live)
    mo = np.isfinite(d.p_open_shin.values)
    out["secondary_open"] = stats.incremental_information(d.y.values[mo], d.p_open_shin.values[mo], d.p_model.values[mo], dates[mo])
    # does the market itself add information over the model? (sanity: it must)
    out["market_over_model"] = stats.incremental_information(d.y.values, d.p_model.values, d.p_close_shin.values, dates)
    # --- betting at the posted close price, blended walk-forward
    out["bets_close"] = stats.backtest(d.y.values, d.p_blend.values, d.dec_home.values, d.dec_away.values, dates, RULE, B=1000)
    out["bets_model_only_close"] = stats.backtest(d.y.values, d.p_model.values, d.dec_home.values, d.dec_away.values, dates, RULE, B=1000)
    bo = mo & np.isfinite(d.p_blend_open.values)
    out["bets_open"] = stats.backtest(d.y.values[bo], d.p_blend_open.values[bo], d.dec_home_open.values[bo], d.dec_away_open.values[bo], dates[bo], RULE, B=1000)
    # --- distribution diagnostics
    margin = (d.home_score - d.away_score).values
    out["margin_norm"] = stats.margin_diagnostics(margin - d.mu_gauss.values)
    out["score_dispersion_home"] = stats.poisson_dispersion(d.home_score.values)
    out["score_dispersion_away"] = stats.poisson_dispersion(d.away_score.values)
    # --- is there skill to forecast at all? team win counts per season vs binomial, and split-half persistence
    rows = []
    for s, g in df[df.season_type == 2].groupby("season"):
        g = g.sort_values("start")
        half = g.start.quantile(0.5)
        for team in set(g.home_id) | set(g.away_id):
            gh = g[(g.home_id == team) | (g.away_id == team)]
            w = ((gh.home_id == team) & (gh.y == 1)) | ((gh.away_id == team) & (gh.y == 0))
            first = gh.start <= half
            rows.append(dict(season=s, team=team, k=int(w.sum()), n=len(gh),
                             w1=float(w[first].mean()) if first.sum() else np.nan,
                             w2=float(w[~first].mean()) if (~first).sum() else np.nan))
    tw = pd.DataFrame(rows).dropna()
    out["beta_binomial"] = stats.beta_binomial_rho(tw.k.values, tw.n.values)
    out["split_half"] = stats.skill_persistence(tw.w1.values, tw.w2.values)
    # per-season breakdown of the primary and of ROI
    out["by_season"] = {}
    for s in seasons[1:]:
        m = (d.season == s).values
        if m.sum() < 100:
            continue
        out["by_season"][int(s)] = dict(
            n=int(m.sum()),
            info=stats.incremental_information(d.y.values[m], d.p_close_shin.values[m], d.p_model.values[m], dates[m]),
            skill=stats.paired_skill(d.y.values[m], d.p_model.values[m], d.p_close_shin.values[m], dates[m], B=500),
            bets=stats.backtest(d.y.values[m], d.p_blend.values[m], d.dec_home.values[m], d.dec_away.values[m], dates[m], RULE, B=500))
    keep = ["league", "event_id", "start", "season", "season_type", "home_abbr", "away_abbr", "home_score", "away_score", "y",
            "ml_home", "ml_away", "ml_home_open", "ml_away_open", "p_close_shin", "p_open_shin", "p_elo", "p_gauss",
            "mu_gauss", "sigma_gauss", "p_model", "p_blend", "p_blend_open", "rest_diff"]
    keep += [c for c in ("p_pois", "p_pois_pitch", "pitch_adj_home", "pitch_adj_away", "lam_h", "lam_a") if c in df]
    df.loc[t, keep].to_csv(ROOT / "data" / f"backtest_{league}.csv", index=False)
    return out


def _f(x, nd=4):
    return "nan" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def render(results: list[dict]) -> str:
    L = [f"# prediction-lane results — walk-forward, generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}", ""]
    L.append("Primary test per league: cluster-robust Wald z on the model coefficient in "
             "`logit(y) = a + b·logit(p_close) + c·logit(p_model)` on the test seasons. "
             "Bonferroni over 4 leagues: p < 0.0125 to pass. The market is Shin-devigged ESPN BET / DraftKings close.")
    L.append("")
    L.append("| league | tune | test seasons | n | c_model | z (cluster) | p | LR p | blend w | VERDICT |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        pc = r["primary_close"]
        verdict = "INFORMATIVE" if (pc["p_wald"] < 0.0125 and pc["c_model"] > 0) else "REDUNDANT"
        L.append(f"| {r['league']} | {r['tune_season']} | {r['test_seasons']} | {r['n_test']} | {_f(pc['c_model'],3)} | "
                 f"{_f(pc['z_c'],2)} | {_f(pc['p_wald'])} | {_f(pc['p_lr'])} | {_f(pc['blend_w'],3)} | **{verdict}** |")
    for r in results:
        L += ["", f"## {r['league'].upper()}", ""]
        L.append(f"- hyper-parameters frozen on {r['tune_season']}: `{json.dumps({k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in r['meta'].items()})}`")
        mc = r["market_cox"]
        L.append(f"- market (close, Shin) Cox calibration: a={_f(mc['a'],3)} (z {_f(mc['z_a'],2)}), b={_f(mc['b'],3)} (z vs 1: {_f(mc['z_b'],2)}); "
                 f"Hosmer-Lemeshow p={_f(r['market_hl']['p'])}; median overround {_f(r['overround_median'],4)}")
        L.append(f"- skill exists to forecast? team-season win counts vs binomial: beta-binomial rho={_f(r['beta_binomial']['rho'],3)} "
                 f"(LR p={_f(r['beta_binomial']['p'])}); split-half persistence of team win%: spearman={_f(r['split_half']['spearman'],3)} (p={_f(r['split_half']['p'])})")
        mn = r["margin_norm"]
        L.append(f"- margin residual (vs Gaussian model): sd={_f(mn['sd'],2)}, skew={_f(mn['skew'],2)}, excess kurt={_f(mn['kurt'],2)}, "
                 f"JB p={_f(mn['jb_p'])}, AD stat={_f(mn['ad_stat'],2)} (5% crit {_f(mn['ad_crit5'],2)}), Student-t df={_f(mn['t_df'],1)}, AIC t-normal={_f(mn['aic_t']-mn['aic_norm'],1)}")
        sh, sa = r["score_dispersion_home"], r["score_dispersion_away"]
        L.append(f"- score dispersion: home var/mean={_f(sh['var_over_mean'],2)} (CT z={_f(sh['ct_z'],1)}, NB size={_f(sh['nb_size'],1)}); "
                 f"away var/mean={_f(sa['var_over_mean'],2)} (CT z={_f(sa['ct_z'],1)})")
        L += ["", "| model | log-loss | market log-loss | Δ (mkt−model) | 95% CI | Brier Δ | Cox b | Cox a |", "|---|---|---|---|---|---|---|---|"]
        for name, m in r["models"].items():
            s, c = m["skill"], m["cox"]
            L.append(f"| {name} | {_f(s['ll_model'])} | {_f(s['ll_market'])} | {_f(s['d_ll'])} | [{_f(s['d_ll_ci'][0])}, {_f(s['d_ll_ci'][1])}] | "
                     f"{_f(s['d_brier'])} | {_f(c['b'],3)} | {_f(c['a'],3)} |")
        so, mm = r["secondary_open"], r["market_over_model"]
        L.append("")
        L.append(f"- vs OPENING line: c_model={_f(so['c_model'],3)}, z={_f(so['z_c'],2)}, p={_f(so['p_wald'])}, blend w={_f(so['blend_w'],3)} (n={so['n']})")
        L.append(f"- sanity, market over model: c_market={_f(mm['c_model'],3)}, z={_f(mm['z_c'],2)} (must be large and positive)")
        L += ["", "| bet set | games | bets | staked $ | pnl $ | ROI | ROI 95% CI | P(ROI≤0) | hit | avg dec | max DD $ | losing months | payoff |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for name in ("bets_close", "bets_model_only_close", "bets_open"):
            b = r[name]
            if b.get("n_bets", 0) == 0:
                L.append(f"| {name} | {b['n_games']} | 0 | 0 | 0 | — | — | — | — | — | — | — | — |")
                continue
            L.append(f"| {name} | {b['n_games']} | {b['n_bets']} | {b['staked']:.0f} | {b['pnl']:.0f} | {_f(b['roi'])} | "
                     f"[{_f(b['roi_ci'][0])}, {_f(b['roi_ci'][1])}] | {_f(b['p_roi_le_0'],3)} | {_f(b['hit'],3)} | {_f(b['avg_dec'],3)} | "
                     f"{b['max_drawdown']:.0f} | {b['losing_months']}/{b['months']} | {_f(b['payoff_ratio'],2)} |")
        L += ["", "| season | n | c_model | z | p | Δ log-loss | ROI | ROI CI | bets |", "|---|---|---|---|---|---|---|---|---|"]
        for s, v in r["by_season"].items():
            i, k, b = v["info"], v["skill"], v["bets"]
            roi = _f(b.get("roi")) if b.get("n_bets") else "—"
            ci = f"[{_f(b['roi_ci'][0])}, {_f(b['roi_ci'][1])}]" if b.get("n_bets") else "—"
            L.append(f"| {s} | {v['n']} | {_f(i['c_model'],3)} | {_f(i['z_c'],2)} | {_f(i['p_wald'])} | {_f(k['d_ll'])} | {roi} | {ci} | {b.get('n_bets',0)} |")
        L += ["", "market calibration (close, Shin), test seasons:", "", "| bin | n | mean p | realized | exact 95% CI | binom p |", "|---|---|---|---|---|---|"]
        for c in r["market_calib"]:
            L.append(f"| {c['bin']} | {c['n']} | {_f(c['mean_p'],3)} | {_f(c['realized'],3)} | [{_f(c['lo'],3)}, {_f(c['hi'],3)}] | {_f(c['binom_p'],3)} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    leagues = (argv or sys.argv[1:]) or ["mlb", "nba", "nhl", "nfl"]
    results = []
    for lg in leagues:
        print(f"== {lg}", flush=True)
        r = evaluate(lg)
        results.append(r)
        pc = r["primary_close"]
        print(f"   n={r['n_test']}  c_model={pc['c_model']:.3f}  z={pc['z_c']:.2f}  p={pc['p_wald']:.4f}  "
              f"d_ll={r['models']['p_model']['skill']['d_ll']:.4f}  bets={r['bets_close'].get('n_bets')}  roi={r['bets_close'].get('roi')}", flush=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "RESULTS.md").write_text(render(results), encoding="utf-8")
    json.dump(results, open(ROOT / "data" / "backtest_results.json", "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("wrote docs/RESULTS.md")


if __name__ == "__main__":
    main()
