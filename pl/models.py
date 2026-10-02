"""Walk-forward outcome models built only from past games.

Every predictor sees games strictly before the game it predicts. Sequential
models (Elo, Poisson attack/defence) update one game at a time; the Gaussian
margin model refits by ridge on each new date. Hyper-parameters are tuned on the
FIRST season of a league only (`tune`) and frozen for every later season, so
the held-out seasons are honest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats as sps

from pl.stats import expit

LEAGUE_DEFAULTS = {
    # k, home_adv (Elo points), mov_scale, carry (fraction of rating kept at new season), goal model
    "mlb": dict(k=4.0, hfa=24.0, carry=0.67, score="poisson"),
    "nhl": dict(k=6.0, hfa=33.0, carry=0.70, score="poisson"),
    "nba": dict(k=20.0, hfa=70.0, carry=0.75, score="gauss"),
    "nfl": dict(k=20.0, hfa=48.0, carry=0.67, score="gauss"),
}


def _season_key(row) -> int:
    return int(row.season)


# ---------------------------------------------------------------- Elo (binomial logistic)
@dataclass
class Elo:
    k: float = 20.0
    hfa: float = 50.0
    carry: float = 0.67
    mov: bool = True
    ratings: dict = field(default_factory=dict)
    season_seen: dict = field(default_factory=dict)

    def _r(self, team: str, season: int) -> float:
        r = self.ratings.get(team, 1500.0)
        if self.season_seen.get(team) not in (None, season):
            r = 1500.0 + self.carry * (r - 1500.0)
            self.ratings[team] = r
        self.season_seen[team] = season
        return r

    def predict(self, home: str, away: str, season: int, neutral: int) -> float:
        rh, ra = self._r(home, season), self._r(away, season)
        d = rh - ra + (0.0 if neutral else self.hfa)
        return 1.0 / (1.0 + 10 ** (-d / 400.0))

    def update(self, home: str, away: str, season: int, neutral: int, hs: float, as_: float) -> None:
        p = self.predict(home, away, season, neutral)
        y = 1.0 if hs > as_ else (0.0 if hs < as_ else 0.5)
        margin = abs(hs - as_)
        mult = 1.0
        if self.mov and margin > 0:
            dr = (self.ratings.get(home, 1500.0) - self.ratings.get(away, 1500.0)) * (1 if y == 1 else -1)
            mult = np.log(margin + 1.0) * (2.2 / (dr * 0.001 + 2.2))
        delta = self.k * mult * (y - p)
        self.ratings[home] = self.ratings.get(home, 1500.0) + delta
        self.ratings[away] = self.ratings.get(away, 1500.0) - delta


def run_elo(df: pd.DataFrame, k: float, hfa: float, carry: float) -> np.ndarray:
    m = Elo(k=k, hfa=hfa, carry=carry)
    out = np.empty(len(df))
    for i, r in enumerate(df.itertuples(index=False)):
        out[i] = m.predict(r.home_id, r.away_id, r.season, r.neutral)
        if np.isfinite(r.home_score) and np.isfinite(r.away_score):
            m.update(r.home_id, r.away_id, r.season, r.neutral, r.home_score, r.away_score)
    return out


def tune_elo(df: pd.DataFrame, league: str) -> dict:
    """Grid on the tuning slice only; minimise log-loss."""
    best = None
    d = LEAGUE_DEFAULTS[league]
    y = (df.home_score > df.away_score).values.astype(float)
    for k in [d["k"] * f for f in (0.5, 0.75, 1.0, 1.5, 2.0)]:
        for hfa in [d["hfa"] * f for f in (0.5, 1.0, 1.5)]:
            p = np.clip(run_elo(df, k, hfa, d["carry"]), 1e-6, 1 - 1e-6)
            ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
            if best is None or ll < best[0]:
                best = (ll, k, hfa)
    return dict(k=best[1], hfa=best[2], carry=d["carry"], ll_tune=best[0])


# ---------------------------------------------------------------- Gaussian margin (ridge, time-decayed)
def gaussian_margin_walkforward(df: pd.DataFrame, half_life_days: float = 120.0, ridge: float = 3.0,
                                min_games: int = 60) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each date, fit margin_i = r_home - r_away + h + e on all prior games
    with exponential time weights, return (p_home, mu, sigma). Ridge keeps new
    teams at zero. Refit once per date; O(dates x teams^2)."""
    teams = sorted(set(df.home_id) | set(df.away_id))
    idx = {t: i for i, t in enumerate(teams)}
    n_t = len(teams)
    X = np.zeros((len(df), n_t + 1))
    for i, r in enumerate(df.itertuples(index=False)):
        X[i, idx[r.home_id]] = 1.0
        X[i, idx[r.away_id]] = -1.0
        X[i, n_t] = 0.0 if r.neutral else 1.0
    margin = (df.home_score - df.away_score).values.astype(float)
    t = df.start.values.astype("datetime64[D]").astype(np.int64)
    days = df.start.dt.floor("D").values
    p = np.full(len(df), np.nan)
    mu = np.full(len(df), np.nan)
    sig = np.full(len(df), np.nan)
    lam = np.log(2) / half_life_days
    pen = np.eye(n_t + 1) * ridge
    pen[n_t, n_t] = 0.1
    beta = None
    sigma = np.nan
    last_day = None
    for i in range(len(df)):
        if days[i] != last_day:
            if i >= min_games:
                ok = np.isfinite(margin[:i])
                w = np.exp(-lam * (t[i] - t[:i])) * ok
                Xw = X[:i] * w[:, None]
                A = Xw.T @ X[:i] + pen
                beta = np.linalg.solve(A, Xw.T @ np.nan_to_num(margin[:i]))
                res = np.nan_to_num(margin[:i] - X[:i] @ beta)
                sigma = np.sqrt(np.sum(w * res ** 2) / np.sum(w))
            last_day = days[i]
        if beta is not None:
            m = X[i] @ beta
            mu[i], sig[i] = m, sigma
            p[i] = sps.norm.cdf(m / sigma)
    return p, mu, sig


# ---------------------------------------------------------------- Poisson attack / defence (sequential)
@dataclass
class PoissonAD:
    """Online Dixon-Coles-style ratings: log lambda_home = mu + h + att_home - def_away.
    Updated per game by a stochastic-gradient step on the Poisson log-likelihood,
    which is the Poisson analogue of Elo. `eta` is the learning rate."""
    eta: float = 0.02
    hfa: float = 0.05
    carry: float = 0.7
    mu: float = 1.3
    att: dict = field(default_factory=dict)
    dfn: dict = field(default_factory=dict)
    season_seen: dict = field(default_factory=dict)

    def _touch(self, team: str, season: int) -> None:
        if self.season_seen.get(team) not in (None, season):
            self.att[team] = self.carry * self.att.get(team, 0.0)
            self.dfn[team] = self.carry * self.dfn.get(team, 0.0)
        self.season_seen[team] = season
        self.att.setdefault(team, 0.0)
        self.dfn.setdefault(team, 0.0)

    def lambdas(self, home: str, away: str, season: int, neutral: int) -> tuple[float, float]:
        self._touch(home, season)
        self._touch(away, season)
        h = 0.0 if neutral else self.hfa
        lh = np.exp(self.mu + h + self.att[home] - self.dfn[away])
        la = np.exp(self.mu + self.att[away] - self.dfn[home])
        return lh, la

    def update(self, home: str, away: str, season: int, neutral: int, hs: float, as_: float) -> None:
        lh, la = self.lambdas(home, away, season, neutral)
        gh, ga = hs - lh, as_ - la          # d loglik / d log-lambda
        self.att[home] += self.eta * gh
        self.dfn[away] -= self.eta * gh
        self.att[away] += self.eta * ga
        self.dfn[home] -= self.eta * ga
        self.mu += self.eta * 0.1 * (gh + ga) / 2


def poisson_outcome_probs(lh: float, la: float, max_goals: int = 25, tie_home: float = 0.5) -> tuple[float, float]:
    """P(home wins), E[total]. Ties (possible in regulation for NHL/MLB extra
    innings are not ties but the Poisson may put mass there) are split by
    `tie_home`, the empirical home share of tie-broken games."""
    k = np.arange(max_goals + 1)
    ph = sps.poisson.pmf(k, lh)
    pa = sps.poisson.pmf(k, la)
    M = np.outer(ph, pa)
    p_home = np.tril(M, -1).sum()
    p_tie = np.trace(M)
    return p_home + tie_home * p_tie, lh + la


def run_poisson(df: pd.DataFrame, eta: float, hfa: float, carry: float, mu0: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    m = PoissonAD(eta=eta, hfa=hfa, carry=carry, mu=mu0)
    p = np.empty(len(df))
    lam_h = np.empty(len(df))
    lam_a = np.empty(len(df))
    for i, r in enumerate(df.itertuples(index=False)):
        lh, la = m.lambdas(r.home_id, r.away_id, r.season, r.neutral)
        lam_h[i], lam_a[i] = lh, la
        p[i], _ = poisson_outcome_probs(lh, la)
        if np.isfinite(r.home_score) and np.isfinite(r.away_score):
            m.update(r.home_id, r.away_id, r.season, r.neutral, r.home_score, r.away_score)
    return p, lam_h, lam_a


def tune_poisson(df: pd.DataFrame) -> dict:
    y = (df.home_score > df.away_score).values.astype(float)
    mu0 = float(np.log(np.mean(np.r_[df.home_score.values, df.away_score.values])))
    best = None
    for eta in (0.01, 0.02, 0.04, 0.08):
        for hfa in (0.02, 0.05, 0.10):
            p = np.clip(run_poisson(df, eta, hfa, 0.7, mu0)[0], 1e-6, 1 - 1e-6)
            ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
            if best is None or ll < best[0]:
                best = (ll, eta, hfa)
    return dict(eta=best[1], hfa=best[2], carry=0.7, mu0=mu0, ll_tune=best[0])


# ---------------------------------------------------------------- MLB starting pitcher layer
def pitcher_adjustment(df: pd.DataFrame, prior_n: float = 12.0, half_life_games: float = 40.0) -> np.ndarray:
    """Runs-allowed-per-game factor for each probable starter, computed from the
    team's runs allowed in his previous starts (the game log we have), shrunk to
    1.0 with `prior_n` pseudo-games and exponentially decayed. Returns the
    log-ratio adjustment to apply to the OPPONENT's lambda: negative = good pitcher."""
    hist: dict[str, list[tuple[float, float]]] = {}   # pitcher -> [(runs_allowed, decay_weight_index)]
    adj_home = np.zeros(len(df))
    adj_away = np.zeros(len(df))
    lam = np.log(2) / half_life_games
    run_mean = []
    for i, r in enumerate(df.itertuples(index=False)):
        base = np.mean(run_mean[-800:]) if run_mean else 4.5
        for side, pid, _ra in (("home", r.home_prob_id, r.away_score), ("away", r.away_prob_id, r.home_score)):
            if pid:
                h = hist.get(pid, [])
                if h:
                    w = np.exp(-lam * (len(h) - 1 - np.arange(len(h))))
                    obs = np.array([x for x in h])
                    est = (np.sum(w * obs) + prior_n * base) / (np.sum(w) + prior_n)
                    val = np.log(est / base)
                else:
                    val = 0.0
                (adj_home if side == "home" else adj_away)[i] = val
        # update after the game
        if not (np.isfinite(r.home_score) and np.isfinite(r.away_score)):
            continue
        if r.home_prob_id:
            hist.setdefault(r.home_prob_id, []).append(float(r.away_score))
        if r.away_prob_id:
            hist.setdefault(r.away_prob_id, []).append(float(r.home_score))
        run_mean.append(float(r.home_score))
        run_mean.append(float(r.away_score))
    return adj_home, adj_away


def apply_pitcher(lam_h: np.ndarray, lam_a: np.ndarray, adj_home: np.ndarray, adj_away: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """home pitcher quality scales AWAY runs, and vice versa."""
    return lam_h * np.exp(adj_away), lam_a * np.exp(adj_home)


def probs_from_lambdas(lam_h: np.ndarray, lam_a: np.ndarray) -> np.ndarray:
    return np.array([poisson_outcome_probs(a, b)[0] for a, b in zip(lam_h, lam_a)])


# ---------------------------------------------------------------- rest / schedule features
def rest_days(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    last: dict[str, np.datetime64] = {}
    rh = np.full(len(df), 7.0)
    ra = np.full(len(df), 7.0)
    d = df.start.dt.floor("D").values
    for i, r in enumerate(df.itertuples(index=False)):
        for team, arr in ((r.home_id, rh), (r.away_id, ra)):
            if team in last:
                arr[i] = min(7.0, (d[i] - last[team]) / np.timedelta64(1, "D"))
        last[r.home_id] = d[i]
        last[r.away_id] = d[i]
    return rh, ra


# ---------------------------------------------------------------- stacking of models and features (walk-forward)
def walkforward_stack(df: pd.DataFrame, feats: np.ndarray, y: np.ndarray, test_mask: np.ndarray,
                      refit_every: int = 50, ridge: float = 2.0) -> np.ndarray:
    """Logistic stacking refit every `refit_every` games on all prior games.
    Returns the stacked probability for every row in test_mask; NaN elsewhere."""
    from pl.stats import logistic_fit
    X = np.column_stack([np.ones(len(df)), feats])
    out = np.full(len(df), np.nan)
    beta = None
    n_fit = 0
    ok = np.all(np.isfinite(X), axis=1) & np.isfinite(y)
    for i in range(len(df)):
        if beta is None or (i - n_fit) >= refit_every:
            m = ok[:i]
            if m.sum() >= 200:
                beta, _ = logistic_fit(X[:i][m], y[:i][m], ridge=ridge)
                n_fit = i
        if beta is not None and test_mask[i] and np.all(np.isfinite(X[i])):
            out[i] = expit(X[i] @ beta)
    return out
