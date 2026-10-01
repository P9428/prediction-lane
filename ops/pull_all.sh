#!/bin/bash
# full ESPN history walk; each league in its own process, odds after days
cd /c/Users/newce/prediction-lane
( python -m pl.pull mlb 2024-03-20 2024-11-02 && python -m pl.pull mlb 2025-03-18 2025-11-05 && python -m pl.pull mlb 2026-03-20 2026-10-01 && python -m pl.pull mlb --odds ) > data/pull_mlb.log 2>&1 &
( python -m pl.pull nba 2023-10-24 2024-06-20 && python -m pl.pull nba 2024-10-22 2025-06-25 && python -m pl.pull nba 2025-10-21 2026-06-25 && python -m pl.pull nba --odds ) > data/pull_nba.log 2>&1 &
( python -m pl.pull nhl 2023-10-10 2024-06-30 && python -m pl.pull nhl 2024-10-04 2025-06-30 && python -m pl.pull nhl 2025-10-07 2026-06-30 && python -m pl.pull nhl --odds ) > data/pull_nhl.log 2>&1 &
( python -m pl.pull nfl --weeks 2022 2023 2024 2025 2026 && python -m pl.pull nfl --odds ) > data/pull_nfl.log 2>&1 &
wait
echo ALL DONE
