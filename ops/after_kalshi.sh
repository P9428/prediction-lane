#!/bin/bash
cd /c/Users/newce/prediction-lane
export PYTHONIOENCODING=utf-8
count() { python -c "import sqlite3;c=sqlite3.connect('data/kalshi_hist.sqlite');print(c.execute('select count(*) from candle_pulls').fetchone()[0])"; }
prev=-1
while true; do
  cur=$(count)
  if grep -q "KXNFLGAME:" data/kalshi_hist.log && [ "$cur" = "$prev" ]; then break; fi
  prev=$cur; sleep 45
done
echo "first pass ended at $cur pulls; filling gaps"
python -m pl.kalshi_hist KXMLBGAME KXNFLGAME --workers 2 2>&1 | tail -n 3
python -m pl.lag_test kalshi 2>&1 | grep -v FutureWarning | head -n 40
python -m pl.evidence run 2>&1 | tail -n 20
echo "KALSHI LAG CHAIN DONE"
