@echo off
title Ascend Limits Bot
echo Starting Bot...
:loop
python main.py
echo Bot crashed or stopped. Restarting in 5 seconds...
timeout /t 5
goto loop
