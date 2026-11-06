@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PYCMD=py -3"
) else (
  set "PYCMD=python"
)
%PYCMD% -m xops_core init || (echo Python 3.11+ is required & pause & exit /b 1)
echo.
echo Review UI: http://127.0.0.1:8765/
echo Press Ctrl+C to stop. No content is automatically published.
%PYCMD% -m xops_core serve
pause
