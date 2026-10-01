"""Inference for binary game outcomes against a market benchmark.

Everything here is numpy/scipy. Bootstraps are clustered by game date because
games on one date share weather, news and line-maker behaviour; a game-level
bootstrap would overstate the independent count (the same lesson as the
Polymarket game-clustered bootstrap, see ../polymarket/docs/SESSION_LOG.md).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, special, stats as sps

EPS = 1e-6


# ---------------------------------------------------------------- odds algebra
def american_to_decimal(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, float)
    out = np.where(a > 0, 1 + a / 100.0, 1 + 100.0 / np.abs(a))
    return np.where(a == 0, np.nan, out)


def implied(dec: np.ndarray) -> np.ndarray:
    return 1.0 / np.asarray(dec, float)


def devig_proportional(p_home: np.ndarray, p_away: np.ndarray) -> np.ndarray:
    s = p_home + p_away
    return p_home / s


def devig_shin(p_home: np.ndarray, p_away: np.ndarray) -> np.ndarray:
    """Shin (1993) removes vig assuming a share z of insider money; for two
    outcomes z has a closed form. Favourites get less of the overround than the
    proportional rule gives them, which matches measured favourite-longshot shape."""
    p_home, p_away = np.asarray(p_home, float), np.asarray(p_away, float)
    s = p_home + p_away
    z = ((s - 1.0) * (p_home ** 2 + p_away ** 2 - s)) / (s * (p_home ** 2 + p_away ** 2) - s)
    z = np.clip(np.nan_to_num(z, nan=0.0), 0.0, 0.5)
    ph = (np.sqrt(z ** 2 + 4 * (1 - z) * p_home ** 2 / s) - z) / (2 * (1 - z))
    pa = (np.sqrt(z ** 2 + 4 * (1 - z) * p_away ** 2 / s) - z) / (2 * (1 - z))
    return ph / (ph + pa)


def logit(p):
    p = np.clip(np.asarray(p, float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def expit(x):
    return special.expit(x)


# ---------------------------------------------------------------- scoring
def log_loss(y, p):
    p = np.clip(p, EPS, 1 - EPS)
    return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))


def brier(y, p):
    return np.mean((p - y) ** 2)


def _cluster_ids(dates):
    _, ids = np.unique(np.asarray(dates), return_inverse=True)
    return ids


def cluster_bootstrap(stat, dates, B=2000, seed=0):
    """Resample whole dates with replacement; `stat(idx)` evaluates on an index array."""
    ids = _cluster_ids(dates)
    n_c = ids.max() + 1
    by = [np.flatnonzero(ids == k) for k in range(n_c)]
    rng = np.random.default_rng(seed)
    out = np.empty(B)
    for b in range(B):
        pick = rng.integers(0, n_c, n_c)
        idx = np.concatenate([by[k] for k in pick])
        out[b] = stat(idx)
    return out


def paired_skill(y, p_model, p_market, dates, B=2000, seed=0):
    """Log-loss and Brier differences (market - model; positive = model better),
    with date-clustered bootstrap CIs. The paired difference is the right
    statistic: both models are scored on the identical games."""
    y, pm, pk = np.asarray(y, float), np.asarray(p_model, float), np.asarray(p_market, float)
    d_ll = lambda idx: log_loss(y[idx], pk[idx]) - log_loss(y[idx], pm[idx])  # noqa: E731
    d_br = lambda idx: brier(y[idx], pk[idx]) - brier(y[idx], pm[idx])  # noqa: E731
    all_idx = np.arange(len(y))
    bl, bb = cluster_bootstrap(d_ll, dates, B, seed), cluster_bootstrap(d_br, dates, B, seed + 1)
    return dict(n=len(y), ll_model=log_loss(y, pm), ll_market=log_loss(y, pk),
                d_ll=d_ll(all_idx), d_ll_ci=(np.percentile(bl, 2.5), np.percentile(bl, 97.5)),
                brier_model=brier(y, pm), brier_market=brier(y, pk),
                d_brier=d_br(all_idx), d_brier_ci=(np.percentile(bb, 2.5), np.percentile(bb, 97.5)))


# ---------------------------------------------------------------- logistic MLE
def logistic_fit(X, y, ridge=0.0):
    X = np.asarray(X, float)
    y = np.asarray(y, float)

    def nll(b):
        z = X @ b
        return np.sum(np.logaddexp(0, z) - y * z) + 0.5 * ridge * np.sum(b[1:] ** 2)

    def grad(b):
        return X.T @ (expit(X @ b) - y) + ridge * np.r_[0, b[1:]]

    r = optimize.minimize(nll, np.zeros(X.shape[1]), jac=grad, method="L-BFGS-B")
    return r.x, r.fun


def logistic_cluster_se(X, y, b, clusters):
    """Sandwich covariance with clustering by date."""
    X = np.asarray(X, float)
    p = expit(X @ b)
    W = p * (1 - p)
    H = (X * W[:, None]).T @ X
    Hinv = np.linalg.pinv(H)
    ids = _cluster_ids(clusters)
    g = X * (y - p)[:, None]
    S = np.zeros_like(H)
    for k in range(ids.max() + 1):
        gk = g[ids == k].sum(0)
        S += np.outer(gk, gk)
    V = Hinv @ S @ Hinv
    return np.sqrt(np.diag(V))


def cox_calibration(y, p, dates):
    """logit(y) = a + b*logit(p). Perfect calibration: a=0, b=1. b<1: prices too
    extreme (overconfident); b>1: underconfident."""
    X = np.column_stack([np.ones(len(y)), logit(p)])
    b, _ = logistic_fit(X, y)
    se = logistic_cluster_se(X, y, b, dates)
    return dict(a=b[0], b=b[1], se_a=se[0], se_b=se[1], z_a=b[0] / se[0], z_b=(b[1] - 1) / se[1])


def incremental_information(y, p_market, p_model, dates):
    """The decisive test. logit(y) = a + b*logit(p_mkt) + c*logit(p_model).
    If c = 0 the model is redundant given the market. Reports the cluster-robust
    Wald z on c and the likelihood-ratio test against the market-only model,
    plus the optimal blend weight w = c / (b + c)."""
    y = np.asarray(y, float)
    X0 = np.column_stack([np.ones(len(y)), logit(p_market)])
    X1 = np.column_stack([X0, logit(p_model)])
    b0, nll0 = logistic_fit(X0, y)
    b1, nll1 = logistic_fit(X1, y)
    se = logistic_cluster_se(X1, y, b1, dates)
    lr = 2 * (nll0 - nll1)
    p_lr = sps.chi2.sf(lr, 1)
    z_c = b1[2] / se[2]
    p_wald = 2 * sps.norm.sf(abs(z_c))
    w = b1[2] / (b1[1] + b1[2]) if (b1[1] + b1[2]) != 0 else np.nan
    return dict(a=b1[0], b_market=b1[1], c_model=b1[2], se_c=se[2], z_c=z_c, p_wald=p_wald,
                lr=lr, p_lr=p_lr, blend_w=w, n=len(y))


def blend_fit(y, p_market, p_model):
    """Fit the stacking weights on PAST games only (the caller enforces that)."""
    X = np.column_stack([np.ones(len(y)), logit(p_market), logit(p_model)])
    b, _ = logistic_fit(X, y, ridge=1.0)
    return b


def blend_apply(b, p_market, p_model):
    return expit(b[0] + b[1] * logit(p_market) + b[2] * logit(p_model))


# ---------------------------------------------------------------- calibration bins
def calibration_table(y, p, edges=(0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0)):
    rows = []
    y, p = np.asarray(y, float), np.asarray(p, float)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p > lo) & (p <= hi)
        n = int(m.sum())
        if n == 0:
            continue
        k = int(y[m].sum())
        ci = sps.beta.ppf([0.025, 0.975], [k + 0.5, k + 1], [n - k + 1, n - k + 0.5]) if n else (np.nan, np.nan)
        lo_ci = 0.0 if k == 0 else sps.beta.ppf(0.025, k, n - k + 1)
        hi_ci = 1.0 if k == n else sps.beta.ppf(0.975, k + 1, n - k)
        rows.append(dict(bin=f"({lo:.1f}, {hi:.1f}]", n=n, mean_p=float(p[m].mean()), realized=k / n,
                         lo=lo_ci, hi=hi_ci, binom_p=float(sps.binomtest(k, n, float(p[m].mean())).pvalue)))
    return rows


def hosmer_lemeshow(y, p, g=10):
    q = np.quantile(p, np.linspace(0, 1, g + 1))
    q[0], q[-1] = -1, 2
    chi = 0.0
    for lo, hi in zip(q[:-1], q[1:]):
        m = (p > lo) & (p <= hi)
        n = m.sum()
        if n == 0:
            continue
        e = p[m].sum()
        o = y[m].sum()
        chi += (o - e) ** 2 / (e * (1 - e / n) + EPS)
    return dict(chi2=chi, df=g - 2, p=sps.chi2.sf(chi, g - 2))


# ---------------------------------------------------------------- distribution diagnostics
def margin_diagnostics(resid: np.ndarray) -> dict:
    """Is the margin residual Gaussian? Jarque-Bera, Anderson-Darling, Student-t df."""
    r = np.asarray(resid, float)
    r = r[np.isfinite(r)]
    jb = sps.jarque_bera(r)
    ad = sps.anderson(r, "norm")
    df, loc, scale = sps.t.fit(r)
    ll_t = np.sum(sps.t.logpdf(r, df, loc, scale))
    ll_n = np.sum(sps.norm.logpdf(r, r.mean(), r.std()))
    return dict(n=len(r), mean=r.mean(), sd=r.std(), skew=sps.skew(r), kurt=sps.kurtosis(r),
                jb_stat=jb.statistic, jb_p=jb.pvalue, ad_stat=ad.statistic, ad_crit5=ad.critical_values[2],
                t_df=df, aic_t=2 * 3 - 2 * ll_t, aic_norm=2 * 2 - 2 * ll_n)


def poisson_dispersion(counts: np.ndarray) -> dict:
    """Variance/mean of scores, NB size parameter by MLE, and the Cameron-Trivedi
    overdispersion score test (under Poisson, var = mean)."""
    x = np.asarray(counts, float)
    x = x[np.isfinite(x)]
    m, v = x.mean(), x.var(ddof=1)
    # NB2 MLE
    def nll(th):
        r = np.exp(th)
        return -np.sum(sps.nbinom.logpmf(x, r, r / (r + m)))
    th = optimize.minimize_scalar(nll, bounds=(-5, 8), method="bounded").x
    r = np.exp(th)
    ll_nb = -nll(th)
    ll_p = np.sum(sps.poisson.logpmf(x, m))
    # score test: t = sum((x-m)^2 - x) / sqrt(2 * sum(m^2))
    t = np.sum((x - m) ** 2 - x) / np.sqrt(2 * len(x) * m ** 2)
    return dict(n=len(x), mean=m, var=v, var_over_mean=v / m, nb_size=r, lr_nb_vs_poisson=2 * (ll_nb - ll_p),
                ct_z=t, ct_p=sps.norm.sf(t))


def skill_persistence(first: np.ndarray, second: np.ndarray) -> dict:
    """Split-half persistence of team ratings or win%: does the past predict the
    future at all? Spearman with its p-value, and the Beta-Binomial rho on counts
    would be the alternative."""
    r, p = sps.spearmanr(first, second)
    return dict(n=len(first), spearman=r, p=p)


def beta_binomial_rho(k: np.ndarray, n: np.ndarray) -> dict:
    """Overdispersion of team win counts beyond binomial: rho = 1/(a+b+1).
    Zero means all teams are coin flips (no skill to forecast)."""
    k, n = np.asarray(k, float), np.asarray(n, float)

    def nll(th):
        a, b = np.exp(th)
        return -np.sum(special.betaln(k + a, n - k + b) - special.betaln(a, b))

    r = optimize.minimize(nll, np.log([5.0, 5.0]), method="Nelder-Mead")
    a, b = np.exp(r.x)
    pbar = k.sum() / n.sum()
    ll_binom = np.sum(sps.binom.logpmf(k, n, pbar))
    return dict(a=a, b=b, rho=1 / (a + b + 1), lr_vs_binomial=2 * (-r.fun - ll_binom),
                p=sps.chi2.sf(2 * (-r.fun - ll_binom), 1))


# ---------------------------------------------------------------- betting
@dataclass
class BetRule:
    edge_min: float = 0.02      # p*dec - 1 must exceed this
    kelly_frac: float = 0.25
    stake_cap: float = 0.02     # of bankroll
    bankroll: float = 1000.0


def backtest(y, p, dec_home, dec_away, dates, rule: BetRule, B=2000, seed=0) -> dict:
    """Flat-bankroll (no compounding) paper backtest at the posted taker price.
    One ticket per game at most: the side with the larger positive edge.
    Returns loss-first metrics and a date-clustered bootstrap CI on ROI."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    dh, da = np.asarray(dec_home, float), np.asarray(dec_away, float)
    e_h, e_a = p * dh - 1, (1 - p) * da - 1
    side = np.where(e_h >= e_a, 1, 0)
    edge = np.where(side == 1, e_h, e_a)
    dec = np.where(side == 1, dh, da)
    win = np.where(side == 1, y, 1 - y)
    bet = (edge > rule.edge_min) & np.isfinite(dec)
    b = dec - 1
    q = np.where(side == 1, p, 1 - p)
    kelly = np.clip((b * q - (1 - q)) / b, 0, None)
    stake = np.minimum(rule.kelly_frac * kelly, rule.stake_cap) * rule.bankroll
    stake = np.where(bet, stake, 0.0)
    pnl = np.where(win == 1, stake * b, -stake)
    n_bets = int(bet.sum())
    out = dict(n_games=len(y), n_bets=n_bets, staked=float(stake.sum()), pnl=float(pnl.sum()))
    if n_bets == 0:
        return out
    roi = lambda idx: pnl[idx].sum() / max(stake[idx].sum(), EPS)  # noqa: E731
    bs = cluster_bootstrap(roi, dates, B, seed)
    cum = np.cumsum(pnl)
    dd = cum - np.maximum.accumulate(np.r_[0, cum])[1:]
    months = np.asarray(dates).astype("datetime64[M]")
    mp = {m: pnl[months == m].sum() for m in np.unique(months[bet])}
    wins = pnl[bet & (pnl > 0)]
    losses = pnl[bet & (pnl < 0)]
    out.update(roi=roi(np.arange(len(y))), roi_ci=(np.percentile(bs, 2.5), np.percentile(bs, 97.5)),
               p_roi_le_0=float(np.mean(bs <= 0)), hit=float(win[bet].mean()),
               avg_dec=float(dec[bet].mean()), avg_edge=float(edge[bet].mean()),
               max_drawdown=float(dd.min()), worst_bet=float(pnl.min()),
               losing_months=sum(v < 0 for v in mp.values()), months=len(mp),
               avg_win=float(wins.mean()) if len(wins) else 0.0, avg_loss=float(losses.mean()) if len(losses) else 0.0,
               payoff_ratio=float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else np.nan)
    return out
