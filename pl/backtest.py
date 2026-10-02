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

import argparse
import json

import numpy as np
import pandas as pd

from pl import models, stats, store
from pl.core import DATA, DOCS, LEAGUES, fmt, utc_now, write_text

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
    df.loc[t, keep].to_csv(DATA / f"backtest_{league}.csv", index=False)
    return out


def render(results: list[dict]) -> str:
    L = [f"# prediction-lane results — walk-forward, generated {utc_now()}", ""]
    L.append("Primary test per league: cluster-robust Wald z on the model coefficient in "
             "`logit(y) = a + b·logit(p_close) + c·logit(p_model)` on the test seasons. "
             "Bonferroni over 4 leagues: p < 0.0125 to pass. The market is Shin-devigged ESPN BET / DraftKings close.")
    L.append("")
    L.append("| league | tune | test seasons | n | c_model | z (cluster) | p | LR p | blend w | VERDICT |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        pc = r["primary_close"]
        verdict = "INFORMATIVE" if (pc["p_wald"] < 0.0125 and pc["c_model"] > 0) else "REDUNDANT"
        L.append(f"| {r['league']} | {r['tune_season']} | {r['test_seasons']} | {r['n_test']} | {fmt(pc['c_model'],3)} | "
                 f"{fmt(pc['z_c'],2)} | {fmt(pc['p_wald'])} | {fmt(pc['p_lr'])} | {fmt(pc['blend_w'],3)} | **{verdict}** |")
    for r in results:
        L += ["", f"## {r['league'].upper()}", ""]
        L.append(f"- hyper-parameters frozen on {r['tune_season']}: `{json.dumps({k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in r['meta'].items()})}`")
        mc = r["market_cox"]
        L.append(f"- market (close, Shin) Cox calibration: a={fmt(mc['a'],3)} (z {fmt(mc['z_a'],2)}), b={fmt(mc['b'],3)} (z vs 1: {fmt(mc['z_b'],2)}); "
                 f"Hosmer-Lemeshow p={fmt(r['market_hl']['p'])}; median overround {fmt(r['overround_median'],4)}")
        L.append(f"- skill exists to forecast? team-season win counts vs binomial: beta-binomial rho={fmt(r['beta_binomial']['rho'],3)} "
                 f"(LR p={fmt(r['beta_binomial']['p'])}); split-half persistence of team win%: spearman={fmt(r['split_half']['spearman'],3)} (p={fmt(r['split_half']['p'])})")
        mn = r["margin_norm"]
        L.append(f"- margin residual (vs Gaussian model): sd={fmt(mn['sd'],2)}, skew={fmt(mn['skew'],2)}, excess kurt={fmt(mn['kurt'],2)}, "
                 f"JB p={fmt(mn['jb_p'])}, AD stat={fmt(mn['ad_stat'],2)} (5% crit {fmt(mn['ad_crit5'],2)}), Student-t df={fmt(mn['t_df'],1)}, AIC t-normal={fmt(mn['aic_t']-mn['aic_norm'],1)}")
        sh, sa = r["score_dispersion_home"], r["score_dispersion_away"]
        L.append(f"- score dispersion: home var/mean={fmt(sh['var_over_mean'],2)} (CT z={fmt(sh['ct_z'],1)}, NB size={fmt(sh['nb_size'],1)}); "
                 f"away var/mean={fmt(sa['var_over_mean'],2)} (CT z={fmt(sa['ct_z'],1)})")
        L += ["", "| model | log-loss | market log-loss | Δ (mkt−model) | 95% CI | Brier Δ | Cox b | Cox a |", "|---|---|---|---|---|---|---|---|"]
        for name, m in r["models"].items():
            s, c = m["skill"], m["cox"]
            L.append(f"| {name} | {fmt(s['ll_model'])} | {fmt(s['ll_market'])} | {fmt(s['d_ll'])} | [{fmt(s['d_ll_ci'][0])}, {fmt(s['d_ll_ci'][1])}] | "
                     f"{fmt(s['d_brier'])} | {fmt(c['b'],3)} | {fmt(c['a'],3)} |")
        so, mm = r["secondary_open"], r["market_over_model"]
        L.append("")
        L.append(f"- vs OPENING line: c_model={fmt(so['c_model'],3)}, z={fmt(so['z_c'],2)}, p={fmt(so['p_wald'])}, blend w={fmt(so['blend_w'],3)} (n={so['n']})")
        L.append(f"- sanity, market over model: c_market={fmt(mm['c_model'],3)}, z={fmt(mm['z_c'],2)} (must be large and positive)")
        L += ["", "| bet set | games | bets | staked $ | pnl $ | ROI | ROI 95% CI | P(ROI≤0) | hit | avg dec | max DD $ | losing months | payoff |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for name in ("bets_close", "bets_model_only_close", "bets_open"):
            b = r[name]
            if b.get("n_bets", 0) == 0:
                L.append(f"| {name} | {b['n_games']} | 0 | 0 | 0 | — | — | — | — | — | — | — | — |")
                continue
            L.append(f"| {name} | {b['n_games']} | {b['n_bets']} | {b['staked']:.0f} | {b['pnl']:.0f} | {fmt(b['roi'])} | "
                     f"[{fmt(b['roi_ci'][0])}, {fmt(b['roi_ci'][1])}] | {fmt(b['p_roi_le_0'],3)} | {fmt(b['hit'],3)} | {fmt(b['avg_dec'],3)} | "
                     f"{b['max_drawdown']:.0f} | {b['losing_months']}/{b['months']} | {fmt(b['payoff_ratio'],2)} |")
        L += ["", "| season | n | c_model | z | p | Δ log-loss | ROI | ROI CI | bets |", "|---|---|---|---|---|---|---|---|---|"]
        for s, v in r["by_season"].items():
            i, k, b = v["info"], v["skill"], v["bets"]
            roi = fmt(b.get("roi")) if b.get("n_bets") else "—"
            ci = f"[{fmt(b['roi_ci'][0])}, {fmt(b['roi_ci'][1])}]" if b.get("n_bets") else "—"
            L.append(f"| {s} | {v['n']} | {fmt(i['c_model'],3)} | {fmt(i['z_c'],2)} | {fmt(i['p_wald'])} | {fmt(k['d_ll'])} | {roi} | {ci} | {b.get('n_bets',0)} |")
        L += ["", "market calibration (close, Shin), test seasons:", "", "| bin | n | mean p | realized | exact 95% CI | binom p |", "|---|---|---|---|---|---|"]
        for c in r["market_calib"]:
            L.append(f"| {c['bin']} | {c['n']} | {fmt(c['mean_p'],3)} | {fmt(c['realized'],3)} | [{fmt(c['lo'],3)}, {fmt(c['hi'],3)}] | {fmt(c['binom_p'],3)} |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="pl backtest", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("leagues", nargs="*", default=list(LEAGUES))
    a = ap.parse_args(argv)
    results = []
    for lg in a.leagues:
        print(f"== {lg}", flush=True)
        r = evaluate(lg)
        results.append(r)
        pc = r["primary_close"]
        print(f"   n={r['n_test']}  c_model={pc['c_model']:.3f}  z={pc['z_c']:.2f}  p={pc['p_wald']:.4f}  "
              f"d_ll={r['models']['p_model']['skill']['d_ll']:.4f}  bets={r['bets_close'].get('n_bets')}  roi={r['bets_close'].get('roi')}", flush=True)
    write_text(DOCS / "RESULTS.md", render(results))
    with open(DATA / "backtest_results.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("wrote docs/RESULTS.md")


if __name__ == "__main__":
    main()
