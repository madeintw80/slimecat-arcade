@echo off
chcp 65001 >nul
REM Heartbeat marker for _common/heartbeat.py (health check 2026-09 backlog level 1, item 4):
REM factory.log is shared with run_feedback.bat / run_weekly.bat, so its mtime stays fresh even
REM when production has stopped for weeks. Only THIS factory run touches factory_heartbeat.txt.
REM Redirection goes FIRST on the echo lines: a trailing digit before > (exit 0>>) would be
REM parsed by cmd as a file-handle redirect and silently break the marker.
set HB=C:\Users\User\projects\SlimeCatArcade\factory\factory_heartbeat.txt
> "%HB%" echo %date% %time% start
"C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe" "C:\Users\User\projects\SlimeCatArcade\factory\make_game.py" >> "C:\Users\User\projects\SlimeCatArcade\factory\factory.log" 2>&1
set RC=%ERRORLEVEL%
>> "%HB%" echo %date% %time% exit %RC%
exit /b %RC%
