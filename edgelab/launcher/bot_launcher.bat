@echo off
REM EdgeLabs launcher — starts the bot + dashboard as background (no console windows),
REM reading creds from .env next to this file. Run by Task Scheduler on logon,
REM or double-click to start manually.
setlocal
set "LAUNCHER_DIR=%~dp0"
set "VENV_PY=C:\Users\Legacy\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"
set "BOT=%LAUNCHER_DIR%..\scripts\bot_runner.py"
set "DASH=%LAUNCHER_DIR%..\scripts\run_dashboard.py"
set "LOGDIR=%LAUNCHER_DIR%..\logs"

REM --- load .env (lines: KEY=VALUE; '#' starts a comment) ---
for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%LAUNCHER_DIR%.env") do (
  if not "%%A"=="" set "%%A=%%B"
)

REM --- optionally launch the MT5 terminal (remembers last login) so the
REM     Python MetaTrader5 package can reach the broker. Remove if unwanted. ---
start "" "C:\Program Files\MetaTrader 5\terminal64.exe"

REM --- start bot + dashboard in the background (pythonw = no console window) ---
start "EdgeLabsBot" "%VENV_PY%" "%BOT%" >> "%LOGDIR%\launcher_bot.log" 2>&1
start "EdgeLabsDash" "%VENV_PY%" "%DASH%" >> "%LOGDIR%\launcher_dash.log" 2>&1

echo EdgeLabs started. Dashboard: http://127.0.0.1:%DASH_PORT%/
endlocal
