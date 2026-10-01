@echo off
cd /d C:\Users\newce\prediction-lane
set PYTHONIOENCODING=utf-8
python -m pl.paper settle >> data\paper_settle.log 2>&1
