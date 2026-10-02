# prediction-lane

Forecast game outcomes from past performance, test the forecast against the sportsbook
closing line out of sample, and paper-trade as a selective taker only where the
forecast carries information the line lacks. Built 2026-10-01 as the inverse of every
measured failure in `../polymarket` (maker spread capture, closing-line bias, in-play
rules), `../venue-gate` (Novig closing line KILL, maker UNDERPOWERED) and the Kalshi
liquidity gate (DEAD).

**Read in this order:** `docs/RESULTS.md` (the walk-forward verdicts), `docs/PREREGISTRATION.md`
(the frozen paper rule and kill rules), `docs/VERDICT.md` (the RI belief state), `docs/SOURCES.md`
(every free source, measured), `docs/PAPER_STATUS.md` (running paper scoreboard).

## Commands

One entry point, `python -m pl <command>`; `python -m pl` lists them, `--help` on any.

```
python -m pl pull mlb 2026-03-20 2026-10-01 --odds   # ESPN history -> data/pl.sqlite (idempotent)
python -m pl pull nfl --weeks 2026 --odds
python -m pl backtest [mlb nba nhl nfl]               # walk-forward evaluation -> docs/RESULTS.md
python -m pl paper tickets                            # today's slate: forecasts, venue quotes, tickets
python -m pl paper settle                             # CLV + settle from ESPN finals -> journal/settled.jsonl
python -m pl paper status                             # docs/PAPER_STATUS.md
python -m pl paper snapshot                           # hourly venue quotes for pending games
python -m pl evidence run                             # RI verdict -> data/evidence/*.ri, docs/VERDICT.md
python -m pl evidence replay data/evidence/pl_x.ri    # re-verify a saved run's signatures and root
python -m pl lag [kalshi|polymarket]                  # venue lead-lag test -> docs/<VENUE>_LAG.md
python -m pl kalshi-hist / poly-hist                  # venue history stores
python -m pl sources [name ...] | --doc               # raw pulls with sha256 manifest | render SOURCES.md
python -m pl probe sources | kalshi                   # reachability probes
```

The older `python -m pl.<module>` spellings still work; the scheduled tasks use them.

Windows tasks (hidden window, via `C:\Users\newce\ops\run-hidden.vbs`): `prediction-lane-tickets`
daily 16:30 local, `prediction-lane-settle` daily 09:30 local, `prediction-lane-snapshot` hourly.
Logs in `data/paper_*.log`. `ops/daily.cmd` is the morning run.

## Development

```
python -m pytest        # tests/ (config in pyproject.toml)
ruff check pl tests     # lint
```

Behaviour the refactor must never change: journal row formats, the printed report lines the
ops scripts grep, and the RI evidence root for unchanged inputs (`python -m pl evidence run`
twice on the same data must print the same root).

## Layout

```
pl/core.py        paths, UTC time, numeric coercion, JSONL journal I/O, logging, report formatting
pl/http.py        the one HTTP session and retry policy (fatal statuses, back-off, 429)
pl/store.py       SQLite: open_db for every store, games/odds/pulls schema, parametrised reads
pl/espn.py        ESPN scoreboard + core odds history (open/close per provider), team lists
pl/pull.py        idempotent history walk, parallel odds
pl/models.py      Elo (MOV, season carry), Gaussian margin ridge (time-decayed), online Poisson
                  attack/defence, MLB starting-pitcher layer, rest days, walk-forward logistic stack
pl/stats.py       odds algebra (Shin devig), paired skill with date-clustered bootstrap, Cox
                  calibration, incremental-information test (cluster-robust Wald + LR), exact
                  binomial bins, Hosmer-Lemeshow, margin normality, Poisson overdispersion,
                  beta-binomial skill, split-half persistence, loss-first betting backtest
pl/backtest.py    per-league walk-forward: tune on season 1, test on the rest, render RESULTS.md
pl/paper.py       slate -> forecast -> Kalshi/Polymarket/DraftKings quotes -> tickets -> settle -> CLV
pl/evidence.py    Reality Infrastructure binding: rules, captures, assertions, verdict, replay
pl/lag_test.py    pre-registered venue lead-lag test (Kalshi, Polymarket)
pl/kalshi_hist.py, pl/poly_hist.py   settled/closed venue markets + price history stores
pl/sources.py     raw pulls with sha256 manifest; SOURCES.md renderer
pl/probe.py       reachability probes
pl/__main__.py    command dispatch
tests/            unit tests: HTTP retry policy, odds algebra, venue matching, settlement, store, CLI
journal/          predictions.jsonl, tickets.jsonl, settled.jsonl, quotes.jsonl (append-only)
ops/              scheduled-task wrappers (.cmd) and bulk pull scripts (.sh)
```

Data (`data/`) stays out of git.
