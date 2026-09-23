@echo off
setlocal EnableDelayedExpansion
set "REPO_ROOT=%~dp0.."
set "PYTHON=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
set "POLLER=%REPO_ROOT%\remote_queue\poller.py"
set "RUNNER=%REPO_ROOT%\remote_queue\run_poller_hidden.vbs"
set "TASK_NAME=HermesRemoteQueuePoller"

if "%~1"=="" goto :install
if /i "%~1"=="install" goto :install
if /i "%~1"=="repair" goto :repair
if /i "%~1"=="run" goto :run
if /i "%~1"=="uninstall" goto :uninstall
if /i "%~1"=="status" goto :status
goto :install

:install
echo Installing %TASK_NAME% as a hidden one-shot poller every 2 minutes...
schtasks /create /tn "%TASK_NAME%" /tr "\"%SystemRoot%\System32\wscript.exe\" //B \"%RUNNER%\"" /sc minute /mo 2 /f /rl highest /it
if %ERRORLEVEL% neq 0 (
  echo Failed - run this installer from an elevated terminal while logged in.
  exit /b 1
)
echo Installed successfully.
goto :eof

:repair
echo Repairing %TASK_NAME%...
schtasks /end /tn "%TASK_NAME%" >nul 2>&1
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
call "%~f0" install
if %ERRORLEVEL% neq 0 exit /b %ERRORLEVEL%
call "%~f0" run
goto :eof

:run
echo Starting %TASK_NAME% now...
schtasks /run /tn "%TASK_NAME%"
goto :eof

:uninstall
schtasks /end /tn "%TASK_NAME%" >nul 2>&1
schtasks /delete /tn "%TASK_NAME%" /f
goto :eof

:status
schtasks /query /tn "%TASK_NAME%" /v /fo LIST 2>nul
goto :eof
