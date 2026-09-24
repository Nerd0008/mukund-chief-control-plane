@echo off
rem Chief Career Daily Brief launcher (called by Windows Task Scheduler).
rem Usage: run_scheduled_brief.cmd
rem
rem Read-only aggregation only. The brief reads the canonical regional workbooks
rem and the other workflows' runtime outputs, and writes ONLY its own artifact
rem under runtime\career-ops\daily-brief. It never writes a tracker, never
rem submits an application, never contacts anyone and never delivers to an
rem external channel (no messaging/Discord delivery is configured or claimed).
rem NOTE: this file must keep CRLF line endings; cmd.exe mis-parses LF-only batches.
setlocal
rem Force UTF-8 for the redirected stdout: the scheduled run writes to a file
rem whose default ANSI code page cannot encode non-Latin job titles (observed
rem on the regional scan: an already-successful run aborted with
rem UnicodeEncodeError and reported exit code 1).
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set CP=C:\Users\mukun\Documents\mukund-chief-control-plane
set PY=C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
set BRIEFDIR=%CP%\runtime\career-ops\daily-brief
if not exist "%BRIEFDIR%" mkdir "%BRIEFDIR%"
"%PY%" "%CP%\career-ops\daily_brief.py" build --out-dir "%BRIEFDIR%" > "%BRIEFDIR%\brief-last-stdout.json" 2>&1
set RC=%ERRORLEVEL%
exit /b %RC%
