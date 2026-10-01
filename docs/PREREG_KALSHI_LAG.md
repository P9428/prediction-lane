# PREREGISTRATION 2 — is Kalshi's game price beatable? (frozen 2026-10-01, before any join or test ran)

## Why this test, and why now

The walk-forward verdict (RESULTS.md) says the past-performance model is redundant
against the sportsbook CLOSE in every league and informative only against the MLB
OPEN. Money does not come from beating a sportsbook we cannot bet; it comes from a
venue whose posted price is stale relative to information that is public at the
moment we would click. Kalshi publishes hourly bid/ask history for every settled game
market, so the question can be answered on prints that already happened:

> At h hours before first pitch, is the Kalshi ask below what public information
> (the sportsbook line already posted, the model) says the side is worth, by more
> than the taker fee?

## Data

- Kalshi settled `KXMLBGAME` and `KXNFLGAME` markets (API lists ~900 MLB games from
  2026-07-24 and ~97 NFL games from 2026-09-09), hourly candlesticks (yes_bid,
  yes_ask, price, volume) from market open to close. NHL settled markets at probe time
  are preseason and are excluded.
- ESPN game rows (outcome, DraftKings/ESPN BET open and close moneylines) joined by
  date and team pair. Model probabilities are the walk-forward `p_model` and the
  walk-forward open-line blend `p_blend_open` already written to
  `data/backtest_<league>.csv`; nothing is refit here.
- Kalshi taker fee 0.07·p(1−p) per contract (public fee schedule).

## Definitions

- `ask_h`, `bid_h`: close of the last hourly candle ending at or before
  `start − h`, requiring both sides quoted and ask − bid ≤ 0.10. If no such candle,
  the game is absent at that horizon (counted, not imputed).
- `kalshi_close`: mid of the last candle ending before the scheduled start.
- Edge at price a for a side with probability p: `p / (a + 0.07·a·(1−a)) − 1`.
- A bet is one $1 contract at the ask (no size model; this is a price test).
- CLV (closing-line value) of a bet at ask a: `kalshi_close_side − a`, where
  kalshi_close_side is the pre-start mid for that side.

## Pre-registered tests, horizon h = 3 hours for both primaries

- **P1 (lag vs sportsbook OPEN, tradeable at h):** bet the side whose edge, using the
  Shin-devigged DraftKings/ESPN BET **opening** line as p, exceeds 0.02. Report ROI per
  $ staked with a date-clustered bootstrap 95% CI and mean CLV with CI.
  PASS iff ROI CI lower bound > 0 **and** CLV CI lower bound > 0.
- **P2 (model, tradeable at h):** same rule with p = `p_blend_open` (open line blended
  with the model, walk-forward). Same pass condition.
- Two primaries → each at α = 0.025 (CI reported at 95%; the pass rule uses the 97.5%
  lower bound).

Diagnostics (not scored): h ∈ {24, 12, 6, 1}; the same rules with the sportsbook
CLOSE as p (NOT tradeable at h: measures how much of the close Kalshi has not yet
absorbed); per-league splits; price-bin splits.

## What a pass licenses

A pass licenses a forward paper test of the same rule with live quotes (the hourly
snapshot job), not real capital. A fail on both kills the "stale venue" lane for
MLB/NFL on Kalshi; Polymarket is a separate measurement.

## Tripwire

Any horizon, threshold, or fee changed after the first run is logged in TRIPWIRE.md.
