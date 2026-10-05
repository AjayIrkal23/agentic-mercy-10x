@echo off
setlocal
set "NoDefaultCurrentDirectoryInExePath=1"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set RC=%ERRORLEVEL%
if "%~1"=="" if not "%RC%"=="0" echo "%cmdcmdline:"=%" | "%SystemRoot%\System32\find.exe" /i "%~nx0 """ >nul && (echo. & echo Install failed, code %RC%. & pause)
exit /b %RC%
