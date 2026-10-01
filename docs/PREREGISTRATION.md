# PREREGISTRATION — prediction lane (frozen 2026-10-01, before the first paper ticket)

## Hypothesis

A forecast built only from past performance (team ratings, scoring rates, starting
pitchers, rest) carries information that the sportsbook closing line does not. If it
does, a selective taker who crosses the spread only where the blended forecast
disagrees with the posted price by more than the full cost stack earns a positive
return, hold-to-settlement, pre-game.

The inverse of every failed thesis in `../polymarket`, `../venue-gate` and the
Kalshi gate: information not price, taker not maker, few deep markets not many thin
ones, pre-game not in-play, low frequency, out-of-sample first, loss-first gating.

## Data

- Outcomes and closing lines: ESPN public scoreboard + core odds history (ESPN BET /
  DraftKings close; `current` when no `close` is published), MLB 2024–2026,
  NBA 2023-24–2025-26, NHL 2023-24–2025-26, NFL 2022–2026. Pulled 2026-10-01 into
  `data/pl.sqlite`.
- Hyper-parameters tuned on the FIRST season of each league only, frozen in
  `data/backtest_results.json`, never re-tuned on test seasons.

## Primary test (one per league, four leagues, Bonferroni α = 0.0125)

`logit(y) = a + b·logit(p_close) + c·logit(p_model)` on test seasons, cluster-robust
(by date) Wald test of `c > 0`. The model is INFORMATIVE only if p < 0.0125. Everything
else in `docs/RESULTS.md` is diagnostic and does not license a bet.

## Paper rule (frozen; `pl/paper.py` implements it verbatim)

- Universe: regular-season and postseason games in MLB, NBA, NHL, NFL. No preseason,
  no college, no props, no in-play.
- Forecast: `p_blend` = walk-forward logistic stack of the sportsbook line and the
  model stack, fit on all settled games to date.
- Price: the executable ASK on Kalshi (taker fee 0.07·p(1−p)) or Polymarket (taker
  fee 0.05·p(1−p), the measured live sports rate), whichever gives the larger edge.
  Novig is recorded when its public book carries the game.
- Edge: `p · (1 / (ask + fee)) − 1`. Ticket only if edge > 0.02.
- Stake: 0.25 × Kelly, capped at 2% of a $1,000 paper bankroll, no compounding.
- One ticket per game at most. Hold to settlement. Settled from ESPN finals.
- EVERY slate game gets a prediction row and is scored on log-loss, bet or not.

## Kill rules (evaluated on settled paper rows, earliest 2026-11-01)

- K1 (forecast): paired mean log-loss (book − model) on ≥ 300 settled games has a
  95% date-clustered CI entirely below zero → the model is worse than the line → KILL.
- K2 (money): after ≥ 100 settled tickets, ROI 95% CI entirely below zero → KILL.
- K3 (loss-first): median loss per losing ticket exceeds median win per winning
  ticket by more than the implied odds justify (payoff ratio < (1−hit)/hit × 0.8)
  for 100 tickets → KILL regardless of P&L.
- Give-up date: 2026-12-31. No real capital before every open leg of `docs/RESULTS.md`
  is INFORMATIVE in held-out seasons AND K1–K3 are all un-triggered.

## Tripwire

Any change to the rule, the models or the data after this file is committed is
recorded in `docs/TRIPWIRE.md` with the output that prompted it. Committed verdicts
stand.
