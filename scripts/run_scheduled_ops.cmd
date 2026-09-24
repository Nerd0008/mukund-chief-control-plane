@echo off
rem Chief operational-services launcher (called by Windows Task Scheduler).
rem Usage: run_scheduled_ops.cmd <backup|logs|health|brief>
rem
rem Read-only against live state and databases. Each service writes ONLY its own
rem artifact:
rem   backup -> %LOCALAPPDATA%\hermes\backups\operational\snapshot-<stamp>\ (outside
rem             the repository) plus an aggregate report under runtime\chief\
rem   logs   -> archives beside the live log it rotates, under the declared policy
rem   health -> runtime\chief\health-snapshot\
rem   brief  -> runtime\chief\morning-brief\
rem
rem No external delivery destination is configured or claimed: the Morning Chief
rem Brief stays a local artifact. No provider/network call and no credential value
rem is read. This launcher never creates, modifies, starts, stops or deletes a
rem scheduled task.
rem
rem NOTE: this file must keep CRLF line endings; cmd.exe mis-parses LF-only batches.
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set SERVICE=%~1
set CP=C:\Users\mukun\Documents\mukund-chief-control-plane
set PY=C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
set OPS=%CP%\scripts\operational_services.py
set LOGDIR=%CP%\runtime\chief\logs
set REPORTS=%CP%\runtime\chief\ops-reports
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
if not exist "%REPORTS%" mkdir "%REPORTS%"

if /I "%SERVICE%"=="backup" goto backup
if /I "%SERVICE%"=="logs" goto logs
if /I "%SERVICE%"=="health" goto health
if /I "%SERVICE%"=="brief" goto brief
echo unknown service "%SERVICE%" (expected backup^|logs^|health^|brief) >> "%LOGDIR%\operational-services.log"
exit /b 2

:backup
"%PY%" "%OPS%" backup --keep 7 --out-dir "%REPORTS%\backup" >> "%LOGDIR%\operational-services.log" 2>&1
exit /b %ERRORLEVEL%

:logs
"%PY%" "%OPS%" rotate-logs --apply --keep 5 --out-dir "%REPORTS%\log-rotation" >> "%LOGDIR%\operational-services.log" 2>&1
exit /b %ERRORLEVEL%

:health
"%PY%" "%OPS%" health-snapshot --out-dir "%CP%\runtime\chief\health-snapshot" >> "%LOGDIR%\operational-services.log" 2>&1
exit /b %ERRORLEVEL%

:brief
"%PY%" "%OPS%" morning-brief --out-dir "%CP%\runtime\chief\morning-brief" >> "%LOGDIR%\operational-services.log" 2>&1
exit /b %ERRORLEVEL%
