# VERDICT — read from the RI belief state, run 39f81d39cb6b

log entries 26, root at read `39f81d39cb6bf598…`, file `data\evidence\pl_39f81d39cb6b.ri`; replay with `python -m pl.evidence replay data\evidence\pl_39f81d39cb6b.ri`

| proposition | rule | verdict |
|---|---|---|
| lane:mlb:close | lane-informative v1 | **REDUNDANT** |
| lane:mlb:open | lane-informative v1 | **INFORMATIVE** |
| lane:nba:close | lane-informative v1 | **REDUNDANT** |
| lane:nba:open | lane-informative v1 | **REDUNDANT** |
| lane:nhl:close | lane-informative v1 | **REDUNDANT** |
| lane:nhl:open | lane-informative v1 | **REDUNDANT** |
| lane:nfl:close | lane-informative v1 | **REDUNDANT** |
| lane:nfl:open | lane-informative v1 | **REDUNDANT** |
| lag:P1 | lag-primary v1 | **FAIL** |
| lag:P2 | lag-primary v1 | **FAIL** |
| lag:poly:P1 | lag-primary v1 | **FAIL** |
| lag:poly:P2 | lag-primary v1 | **FAIL** |
| kill:K1 | paper-K1 v1 | **NOT_ASSERTED** |
| kill:K2 | paper-K2 v1 | **NOT_ASSERTED** |
| kill:K3 | paper-K3 v1 | **NOT_ASSERTED** |

A verdict here is the engine's projection of the logged claims under the logged rules; docs/RESULTS.md and docs/KALSHI_LAG.md are the measurements those claims were read from.
