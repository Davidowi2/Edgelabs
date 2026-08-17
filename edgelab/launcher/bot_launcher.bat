@echo off
REM EdgeLabs manual launcher — double-click to start the bot + dashboard.
REM (For auto-start at Windows logon, run install_task.bat once as Administrator.)
setlocal
set "LAUNCHER_DIR=%~dp0"
set "VENV_PY=C:\Users\Legacy\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"
set "RUN=%LAUNCHER_DIR%run.py"
if not exist "%RUN%" (
  echo ERROR: run.py not found next to this launcher.
  pause
  exit /b 1
)
start "" "%VENV_PY%" "%RUN%"
echo EdgeLabs starting... (detached). Dashboard: http://127.0.0.1:8080/
endlocal
