@echo off
rem Chief Career Ops regional scan launcher (called by Windows Task Scheduler).
rem Usage: run_scheduled_scan.cmd <region>
rem
rem Bounded DRY-RUN only. Never writes a tracker, never submits anything.
rem It invokes the shared regional worker (regional_job_search.py run --scheduled),
rem which performs the bounded Career Ops scan, applies the shared eligibility
rem policy, runs the shared dedupe probe (dry-run), and writes run-health +
rem idempotency metadata. The worker can never apply to a workbook.
rem NOTE: this file must keep CRLF line endings; cmd.exe mis-parses LF-only batches.
setlocal
rem Force UTF-8 for the redirected stdout: the scheduled run writes to a file
rem whose default ANSI code page cannot encode non-Latin job titles, which used
rem to abort an already-successful scan (UnicodeEncodeError, exit code 1).
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set REGION=%~1
set CP=C:\Users\mukun\Documents\mukund-chief-control-plane
set PY=C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
set LOGDIR=%CP%\runtime\career-ops\scan-runs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
"%PY%" "%CP%\career-ops\regional_job_search.py" run --region %REGION% --scheduled --timeout 1800 --record "%LOGDIR%" > "%LOGDIR%\%REGION%-last-stdout.json" 2>&1
set RC=%ERRORLEVEL%
exit /b %RC%
