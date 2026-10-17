@echo off
rem Chief NIGHTLY Career pipeline launcher (Windows Task Scheduler).
rem ONE scheduled job runs ALL FOUR regional scan agents in a single bounded,
rem read-only unified run, then maintains each region's own canonical Excel
rem tracker through the canonical writer (dedupe + hash-verified backup +
rem verification). Previously the four region tasks each took the same global
rem lock, so only the first region ran and the rest exited overlap_skipped.
rem
rem Args pass straight through to career-ops/nightly_career_run.py
rem   (e.g. --dry-run-trackers, --skip-scan, --budget-seconds N).
rem
rem NOTE: this file must keep CRLF line endings; cmd.exe mis-parses LF-only batches.
setlocal
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set CP=C:\Users\mukun\Documents\mukund-chief-control-plane
set PY=C:\Users\mukun\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe
set LOGDIR=%CP%\runtime\career-ops\nightly
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
"%PY%" "%CP%\career-ops\nightly_career_run.py" %* > "%LOGDIR%\nightly-last-stdout.json" 2>&1
set RC=%ERRORLEVEL%
exit /b %RC%
