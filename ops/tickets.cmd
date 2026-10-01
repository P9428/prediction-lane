@echo off
cd /d C:\Users\newce\prediction-lane
set PYTHONIOENCODING=utf-8
python -m pl.paper tickets >> data\paper_tickets.log 2>&1
