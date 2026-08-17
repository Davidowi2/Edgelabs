@echo off
REM Register EdgeLabs as a Windows Task Scheduler task that runs at user LOGON,
REM so the bot + dashboard keep running even when Hermes is closed.
REM Run this once (right-click -> Run as Administrator if needed).
set "BAT=%~dp0bot_launcher.bat"
schtasks /create /tn "EdgelabsBot" /tr "\"%BAT%\"" /sc onlogon /rl highest /f
if %errorlevel%==0 (
  echo.
  echo Task 'EdgelabsBot' installed. It will auto-start at your next logon.
  echo To start now without logging off:  schtasks /run /tn "EdgelabsBot"
  echo Dashboard: http://127.0.0.1:8080/
) else (
  echo.
  echo Install failed. Try right-clicking this file -> "Run as administrator".
)
pause
