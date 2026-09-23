@echo off
setlocal EnableDelayedExpansion
set "REPO_ROOT=%~dp0.."
set "PYTHON=%REPO_ROOT%\..\..\..\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
set "POLLER=%REPO_ROOT%\remote_queue\poller.py"
set "TASK_NAME=HermesRemoteQueuePoller"

if "%~1"=="" goto :install
if /i "%~1"=="uninstall" goto :uninstall
if /i "%~1"=="status" goto :status
goto :install

:install
schtasks /create /tn "%TASK_NAME%" /tr "%PYTHON% %POLLER%" /sc minute /mo 2 /f /rl highest
if %ERRORLEVEL% neq 0 echo Failed - run as administrator
goto :eof

:uninstall
schtasks /delete /tn "%TASK_NAME%" /f
goto :eof

:status
schtasks /query /tn "%TASK_NAME%" /v /fo LIST 2>nul
goto :eof
