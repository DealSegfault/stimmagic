@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-windows-installer.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo [Stimma] La construction Windows a échoué avec le code %EXIT_CODE%.
)

if "%~1"=="" pause
exit /b %EXIT_CODE%
