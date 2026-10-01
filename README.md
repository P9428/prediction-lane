# prediction-lane

Forecast game outcomes from past performance, test the forecast against the sportsbook
closing line out of sample, and paper-trade as a selective taker only where the
forecast carries information the line lacks. Built 2026-10-01 as the inverse of every
measured failure in `../polymarket` (maker spread capture, closing-line bias, in-play
rules), `../venue-gate` (Novig closing line KILL, maker UNDERPOWERED) and the Kalshi
liquidity gate (DEAD).

**Read in this order:** `docs/RESULTS.md` (the walk-forward verdicts), `docs/PREREGISTRATION.md`
(the frozen paper rule and kill rules), `docs/SOURCES.md` (every free source, measured),
`docs/PAPER_STATUS.md` (running paper scoreboard).

## Commands

```
python -m pl.pull mlb 2026-03-20 2026-10-01 --odds   # ESPN history -> data/pl.sqlite (idempotent)
python -m pl.pull nfl --weeks 2026 --odds
python -m pl.backtest [mlb nba nhl nfl]               # walk-forward evaluation -> docs/RESULTS.md
python -m pl.paper tickets                            # today's slate: forecasts, venue quotes, tickets
python -m pl.paper settle                             # settle from ESPN finals -> journal/settled.jsonl
python -m pl.paper status                             # docs/PAPER_STATUS.md
python -m pl.sources                                  # raw pulls of every other reachable source
python ops/probe_sources.py                           # re-probe reachability
```

Windows tasks (hidden window, via `C:\Users\newce\ops\run-hidden.vbs`): `prediction-lane-tickets`
daily 16:30 local, `prediction-lane-settle` daily 09:30 local. Logs in `data/paper_*.log`.

## Layout

```
pl/espn.py      ESPN scoreboard + core odds history (open/close per provider)
pl/store.py     SQLite: games, odds, pulls
pl/pull.py      idempotent history walk, parallel odds
pl/models.py    Elo (MOV, season carry), Gaussian margin ridge (time-decayed), online Poisson
                attack/defence, MLB starting-pitcher layer, rest days, walk-forward logistic stack
pl/stats.py     odds algebra (Shin devig), paired skill with date-clustered bootstrap, Cox
                calibration, incremental-information test (cluster-robust Wald + LR), exact
                binomial bins, Hosmer-Lemeshow, margin normality, Poisson overdispersion,
                beta-binomial skill, split-half persistence, loss-first betting backtest
pl/backtest.py  per-league walk-forward: tune on season 1, test on the rest, render RESULTS.md
pl/paper.py     slate -> forecast -> Kalshi/Polymarket/DraftKings quotes -> tickets -> settle
pl/sources.py   raw pulls with sha256 manifest
journal/        predictions.jsonl, tickets.jsonl, settled.jsonl (append-only)
```

Data (`data/`) stays out of git.
