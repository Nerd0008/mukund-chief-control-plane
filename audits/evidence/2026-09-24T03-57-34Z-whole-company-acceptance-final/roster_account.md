# Roster account — every v1 roster item, 2026-09-24

| ID | Worker / service | Status | Evidence |
|---|---|---|---|
| A01 | Hermes Chief of Staff / owner interface | **PASS** | live gateway; this session; state/current_company_state.md |
| A02 | E1 intake, classification, immutable quality floor | **PASS** | this run: chief_intake_e1_classify + e1_quality_floor_audit (chain + integrity PASS) |
| A03 | E2 Resource Governor / provider telemetry | **PASS** | this run: e2_gov_verify PASS + e2_telemetry + e2_resource_brief |
| A04 | Daily Resource Brief generator | **PASS** | this run: e2_resource_brief (eb brief); unknown dimensions stay UNKNOWN |
| A05 | E3 Planner / decomposer | **PASS** | exec-brain/e3_planner.py; regression suite in full_regression |
| A06 | E3 Router / meta-selector / Qualification Gate | **PASS** | exec-brain/e3_router.py + qualification_gate.py; evidence-driven capability_registry; this run: e3_status |
| A07 | E3 Context Compiler | **PASS** | exec-brain/e3_context.py; full_regression |
| A08 | E3 Permission Compiler | **PASS** | exec-brain/e3_permissions.py; full_regression |
| A09 | E3 Dynamic Team Assembler | **PASS** | exec-brain/e3_team_assembly.py; decomposed multi-worker rehearsal evidence 2026-09-23T21:32:41Z |
| A10 | E3 Worker Execution Manager | **PASS** | exec-brain/e3_execution.py; this run: e4e5_drill_harness on the real execution abstractions |
| A11 | E3 Integrator | **PASS** | exec-brain/e3_integrator.py; multi-worker rehearsal scenario F COMPLETE |
| A12 | E3 Independent Critic / Verifier | **PASS** | exec-brain/e3_verifier.py; a node cannot reach COMPLETE without a verification PASS |
| A13 | E3 Conflict / targeted rework / replanning / escalation | **PASS** | exec-brain/e3_conflict.py, e3_replan.py, e3_escalate.py; full_regression |
| A14 | E3 Capability Learning / benchmark / qualification manager | **PASS** | exec-brain/e3_qualification_benchmark.py + scripts/e3_qualification_from_evidence.py (evidence-backed bar; qualified_rows_without_evidence = 0) |
| A15 | E4 Resource Continuity / checkpoint / failover manager | **PASS** | exec-brain/resource_monitor.py, checkpoint/failover paths; this run: e4e5 drills D1/D3/D7 |
| A16 | E5 Safe Mode / failure-drill / convergence manager | **PASS** | exec-brain/safe_mode.py; this run: e4e5 drills D5/D6 (stubbed-failure level) |
| A17 | Audit / decision-journal / evidence-state reconciler | **PASS** | decision_rationale + blocked-work reconciliation 2026-09-24T02:45Z; this run's evidence bundle |
| A18 | Remote Queue Scheduler / watchdog / recovery supervisor | **PASS** | remote_queue/ + tests; this run: remote_queue_scheduler_state (read-only) + full_regression queue/bridge suites |
| A19 | Discord Chief Gateway + archive/sync worker | **PASS** | gateway connected; this run: discord_sync_dry_run (no publish performed in acceptance) |
| A20 | Company Registry / system inventory worker | **PASS** | scripts/company_inventory.py; 50/50 roster items mapped (2026-09-23 audit) |
| A21 | Local health / backup / restore / boot-persistence worker | **PASS** | this run: operational_health_snapshot + operational_backup_dry_run + backup_restore_drill + validate-persistence (reboot itself owner-gated, recorded) |
| A22 | Morning Chief Brief aggregator | **PASS** | this run: morning_chief_brief |
| B01 | Career Ops Manager / Chief integration | **PASS** | career-ops/career_ops_cli.py single Chief entry point; this run: career_ops_cli_inventory |
| B02 | UK Job Search Agent | **PASS** | career-ops/regional_job_search.py + ChiefCareerScan-UK (dry-run); this run: regional_jobs_eligibility_uk |
| B03 | Dubai Job Search Agent | **PASS** | lane built + scheduled (dry-run); this run: regional_jobs_eligibility_dubai. Limitation: no UAE-specific provider (owner decision, item 7) — thin results are a coverage fact, not a vacancy fact |
| B04 | Japan Job Search Agent | **PASS** | lane built + scheduled (dry-run); this run: regional_jobs_eligibility_japan. Limitation: no Japan-specific provider (owner decision, item 7) |
| B05 | Singapore Job Search Agent | **PASS** | lane built + scheduled (dry-run); this run: regional_jobs_eligibility_singapore |
| B06 | Job Eligibility / role-policy filter | **PASS** | career-ops/regional_policy.json + evaluate_record; fail-closed when scope unresolved |
| B07 | Job / Company / Application dedupe-state manager | **PASS** | shared tracker_writer primitives (normalize_url/pair_key/cross-month index); this run: dedupe replay per region |
| B08 | Excel Tracker Writer (openpyxl, artifact-tool replaced) | **PASS** | career-ops/tracker_writer.py; this run: career_ops_scan_dedupe_write on a dated copy |
| B09 | Monthly Tracker Rollover / archive worker | **PASS** | career-ops/tracker_rollover.py; this run: tracker_rollover acceptance |
| B10 | Company Watch Agent | **PASS** | company-watch/; this run: company_watch_registry + company_watch_handoff_dry_run |
| B11 | Recruiter / intermediary Watch Agent | **PASS** | recruiters parsed from the recorded history into the watched registry; read-only discovery, no contact |
| B12 | Application Inbox / Status Monitor | **READY_NEEDS_OWNER_CONFIG** | built + tested; this run: application_status_monitor passes on fixtures/local export. Live mailbox feed needs the owner's Gmail read-only OAuth (overnight-owner-actions item 9) |
| B13 | Job Description Analyzer / requirement extractor | **PASS** | career-ops/job_intelligence.py; this run: jobbrief_cv_cover_reviewer |
| B14 | Company / Role Research Brief Agent | **READY_NEEDS_OWNER_CONFIG** | built; every brief reports research_needed while no research provider is owner-approved (item 11). Cited-file path works |
| B15 | CV Tailor Agent | **PASS** | career-ops/cv_workflow.py (deterministic reordering, provenance per line); this run: cv_cover_linkedin_handoff |
| B16 | Cover Letter Agent | **PASS** | career-ops/cv_workflow.py + cv_render_cover.mjs; this run: cv_cover_linkedin_handoff |
| B17 | Application Pack Reviewer / truth & completeness gate | **PASS** | career-ops/application_pack_review.py; this run: jobbrief_cv_cover_reviewer |
| B18 | Submission Gate / owner-approval handoff | **PASS** | career-ops/submission_gate.py; this run: owner_escalation_and_gates refuses the external action |
| B19 | LinkedIn Job Discovery Agent (read-only) | **PASS** | career-ops/linkedin_workflow.py intake/dedupe/handoff; owner-exported local files only |
| B20 | LinkedIn Profile / Post Draft Agent | **PASS** | unsent drafts with provenance; this run: cv_cover_linkedin_handoff |
| B21 | Networking / Recruiter Outreach Draft Agent | **PASS** | three unsent variants, explicit unsent state; this run: linkedin_outreach_interview_prep |
| B22 | Interview Prep Agent | **PASS** | career-ops/interview_prep.py; this run: linkedin_outreach_interview_prep |
| B23 | Career Daily Brief / Pipeline Prioritizer | **PASS** | career-ops/daily_brief.py; this run: career_daily_brief + career_brief_status |
| B24 | Regional Scheduler / run-health monitor | **PASS** | career-ops/install_schedules.py + dept_run_health; this run: regional_jobs_lanes + validate-persistence |
| C01 | Whole-company Local Acceptance Runner | **PASS** | scripts/whole_company_acceptance.py; this acceptance run's evidence bundle |
| C02 | Owner-Action Consolidator | **PASS** | consolidated order in tasks-or-issues/overnight-owner-actions-2026-09-24.md + the handover's ordered afternoon list |
| C03 | Deployment Prep / Manifest / Restore Agent | **READY_NEEDS_OWNER_CONFIG** | deployments/ manifest, preflight GO, backup/restore drill pass; cutover itself is owner-gated (architecture + VPS details + authorisation) |
| C04 | Final Morning Handover Generator | **PASS** | handovers/2026-09-24-morning-handover.md (this run) |

Roster items accounted for: 50/50 (PASS=47, READY_NEEDS_OWNER_CONFIG=3). No UNKNOWN omission.

## Supplementary owner-gated / external items (not roster rows)

| Item | What | Status | Detail |
|---|---|---|---|
| provider-credentials | 7 API worker credentials (Mistral, GLM, Qwen, LongCat, MiniMax, Step, Hunyuan) | **READY_NEEDS_OWNER_CONFIG** | presence probe: 0/7 configured; owner action item 1; use scripts/set_provider_key.py |
| e3-stage2 | E3 local Stage 2 production enablement | **BLOCKED_EXTERNAL** | gated on the 7 credentials + explicit owner step; anti-loop directive forbids re-staging while 0/7 |
| live-provider-e4e5 | Live-provider E4 failover / E5 recovery drill | **BLOCKED_EXTERNAL** | harness has no live-provider mode by design; owner acceptance question recorded (item 8) |
| deployment-architecture | Deployment architecture choice + VPS host/account details | **BLOCKED_EXTERNAL** | owner decision items 3 + 4; no cutover authorised |
| reboot-persistence | Reboot survival of the 7 non-`Hermes_Gateway` Chief tasks | **BLOCKED_EXTERNAL** | read-only validation done; a reboot is prohibited by this contract, so survival is UNVERIFIED (item 6) |
| laptop-security-audit | Owner-attended laptop UI-event attribution audit | **BLOCKED_EXTERNAL** | item 5; evidence preserved, no destructive cleanup performed |
| rollover-policy | Rotate 2026-09 out of the live workbooks (owner-column rows blocked) | **BLOCKED_EXTERNAL** | uk 26 / dubai 8 / singapore 4 owner-state rows; refused, not deleted |
| regional-work-auth | Work-authorisation facts for UAE / Japan / Singapore | **BLOCKED_EXTERNAL** | every non-UK record stays labelled UNKNOWN (item 6) |
| linkedin-live-surface | Whether the live LinkedIn account may ever be read | **BLOCKED_EXTERNAL** | owner-export path only today (item 13) |
| ops-scheduling | Scheduling cadence for operational backup / log rotation / briefs | **BLOCKED_EXTERNAL** | runs on demand only until the owner approves a cadence (item 15) |
