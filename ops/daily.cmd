@echo off
cd /d C:\Users\newce\prediction-lane
set PYTHONIOENCODING=utf-8
echo === settle overnight + score CLV
python -m pl.paper settle
echo.
echo === RI verdict (re-ruled from the journal)
python -m pl.evidence run | findstr /R "^| lane:mlb:open ^| lag: ^| kill: root"
echo.
echo === tonight's slate
python -m pl.paper tickets 2>nul | findstr /V FutureWarning
echo.
echo === tasks
schtasks /Query /TN prediction-lane-tickets /FO LIST | findstr /C:"Next Run" /C:"Last Result"
schtasks /Query /TN prediction-lane-settle /FO LIST | findstr /C:"Next Run" /C:"Last Result"
schtasks /Query /TN prediction-lane-snapshot /FO LIST | findstr /C:"Next Run" /C:"Last Result"
