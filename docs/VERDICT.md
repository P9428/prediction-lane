# VERDICT — read from the RI belief state, run 465ac9bbbbf5

log entries 27, root at read `465ac9bbbbf5dd9b…`, file `data\evidence\pl_465ac9bbbbf5.ri`; replay with `python -m pl evidence replay data\evidence\pl_465ac9bbbbf5.ri`

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
| kill:K1 | paper-K1 v1 | **LIVE** |
| kill:K2 | paper-K2 v1 | **NOT_ASSERTED** |
| kill:K3 | paper-K3 v1 | **NOT_ASSERTED** |

A verdict here is the engine's projection of the logged claims under the logged rules; docs/RESULTS.md and docs/KALSHI_LAG.md are the measurements those claims were read from.
