@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-local\Scripts\python.exe" (
  ".venv-local\Scripts\python.exe" -B -m deploy.compose start %*
) else (
  py -3 -m deploy.compose start %*
)
exit /b %errorlevel%
