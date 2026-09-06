@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "CHECK_ARG="
if /i "%~1"=="--check" set "CHECK_ARG=-Check"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%launch-stimma-windows.ps1" %CHECK_ARG%
set "EXIT_CODE=%ERRORLEVEL%"
if "%EXIT_CODE%"=="0" exit /b 0

echo.
echo [Stimma] Le lancement a echoue avec le code %EXIT_CODE%.
echo.
if not defined CHECK_ARG pause
exit /b %EXIT_CODE%
