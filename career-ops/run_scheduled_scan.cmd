@echo off
rem Chief Career Ops UNIFIED scheduled discovery launcher (Windows Task Scheduler).
rem Usage: run_scheduled_scan.cmd <region>
rem
rem Bounded discovery pass. The orchestrator itself is read-only and never
rem applies a manifest; the promote step at the end of this file writes the
rem discovered roles into the canonical tracker through the verified writer.
rem It never submits an application, never contacts anyone, never logs in
rem anywhere and never opens a browser or GUI.
rem
rem It invokes the unified scheduled orchestrator
rem (career-ops/discovery/scheduled_orchestrator.py run), which combines the
rem structured regional provider scan (the unchanged regional_job_search worker),
rem the bounded open-web/Codex research pass, Company Watch findings, the owner's
rem priority company watchlist findings and the recruiter-watch / LinkedIn-export
rem intakes into ONE unified funnel, then writes one unified candidate manifest
rem and one funnel document with source/funnel attribution.
rem
rem   --scheduled         read-only orchestrator pass (the promote step below
rem                       is what writes the tracker)
rem   --require-live-web  refuses to call the live research lane production-ready
rem                       when no current-web search mechanism is operational: the
rem                       run still completes truthfully from the other sources,
rem                       records the blocker and exits 3. No fixture fallback.
rem   --mode high_recall  production discovery policy (default). The owner's own
rem                       Intern/Internship-only rule remains available only as
rem                       an explicit diagnostic: --mode intern_only --compare
rem
rem Rollback (previous behaviour, one line; the launcher path is unchanged so no
rem task re-registration is needed) -- see career-ops/scheduled_orchestrator.md:
rem   "%PY%" "%CP%\career-ops\regional_job_search.py" run --region %REGION% --scheduled --timeout 1800 --record "%LOGDIR%"
rem
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
"%PY%" "%CP%\career-ops\discovery\scheduled_orchestrator.py" run --region %REGION% --scheduled --require-live-web --mode high_recall --semantic codex --codex-model gpt-6-sol --codex on --codex-budget 8 --budget-seconds 2700 --scan-timeout 900 --web-queries 28 --limit-per-query 10 --max-urls 60 --per-query-timeout 180 --retries 1 --out-dir "%CP%\runtime\career-ops\discovery" > "%LOGDIR%\%REGION%-unified-last-stdout.json" 2>&1
set RC=%ERRORLEVEL%
rem --- discovery -> tracker handoff (owner instruction 2026-10-09) -------
rem The orchestrator above is read-only: it writes a candidate manifest and
rem stops. Without this step a found role stayed in the manifest and never
rem reached the workbook. promote_manifest.py applies it through the same
rem verified writer (career_ops_cli.py write --apply), so duplicate
rem detection, the hash-checked backup and post-write verification still
rem apply. A locked workbook (Excel open) fails safely and changes nothing.
set PROMOTEDIR=%CP%\runtime\career-ops\promote
if not exist "%PROMOTEDIR%" mkdir "%PROMOTEDIR%"
"%PY%" "%CP%\career-ops\promote_manifest.py" --region %REGION% --apply > "%PROMOTEDIR%\%REGION%-promote-last.json" 2>&1
set PRC=%ERRORLEVEL%
if %PRC% neq 0 echo [warn] promote exited %PRC% for %REGION%; see %PROMOTEDIR%\%REGION%-promote-last.json
exit /b %RC%
