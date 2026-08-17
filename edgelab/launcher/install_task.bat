@echo off
REM Register EdgeLabs as a Windows Task Scheduler task that runs at user LOGON,
REM so the bot + dashboard keep running even when Hermes is closed.
REM
REM Run this ONCE. Right-click -> "Run as administrator" (the /rl highest needs
REM elevation; without it Windows returns "Access is denied"). After this, the
REM task auto-starts on every logon and survives Hermes closing.
setlocal
set "BAT=%~dp0bot_launcher.bat"
set "PYW=C:\Users\Legacy\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"
set "RUN=%~dp0run.py"

REM Prefer calling pythonw run.py directly (robust, no .bat quoting issues).
if exist "%RUN%" (
  schtasks /create /tn "EdgelabsBot" /tr "\"%PYW%\" \"%RUN%\"" /sc onlogon /rl highest /f
) else (
  schtasks /create /tn "EdgelabsBot" /tr "\"%BAT%\"" /sc onlogon /rl highest /f
)

if %errorlevel%==0 (
  echo.
  echo Task 'EdgelabsBot' installed. It will auto-start at your next logon.
  echo To start now without logging off:  schtasks /run /tn "EdgelabsBot"
  echo Dashboard: http://127.0.0.1:8080/
) else (
  echo.
  echo Install failed. Right-click this file -> "Run as administrator".
)
pause
endlocal
