#!/bin/bash
# resume any league: days are idempotent, odds only fetch what is missing
cd /c/Users/newce/prediction-lane
L=$1
case $L in
  mlb) python -m pl.pull mlb 2024-03-20 2024-11-02; python -m pl.pull mlb 2025-03-18 2025-11-05; python -m pl.pull mlb 2026-03-20 2026-10-01; python -m pl.pull mlb --odds ;;
  nba) python -m pl.pull nba 2023-10-24 2024-06-20; python -m pl.pull nba 2024-10-22 2025-06-25; python -m pl.pull nba 2025-10-21 2026-06-25; python -m pl.pull nba --odds ;;
  nhl) python -m pl.pull nhl 2023-10-10 2024-06-30; python -m pl.pull nhl 2024-10-04 2025-06-30; python -m pl.pull nhl 2025-10-07 2026-06-30; python -m pl.pull nhl --odds ;;
  nfl) python -m pl.pull nfl --weeks 2022 2023 2024 2025 2026; python -m pl.pull nfl --odds ;;
esac
echo "RESUME $L DONE"
