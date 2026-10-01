@echo off
cd /d C:\Users\newce\prediction-lane
set PYTHONIOENCODING=utf-8
python -m pl.paper snapshot >> data\paper_snapshot.log 2>&1
