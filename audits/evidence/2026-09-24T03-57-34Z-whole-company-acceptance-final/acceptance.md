# Whole-company local acceptance — 2026-09-24T03-57-34Z

- Verdict: **PASS**
- Steps: 34 run — 33 PASS, 0 FAIL, 1 owner-gated, 0 unavailable
- External mutations performed: **0**; provider calls spent: **0**

| Step | Category | Status | Detail |
|---|---|---|---|
| `chief_intake_e1_classify` | chief_intake_e1 | **PASS** | intake record eb-20260924-edf746ec |
| `e1_quality_floor_audit` | chief_intake_e1 | **PASS** | chain + integrity verify PASS |
| `e2_resource_brief` | e2_telemetry | **PASS** | exit 0 in 0.19s |
| `e2_gov_verify` | e2_telemetry | **PASS** | governor verify PASS |
| `e2_telemetry` | e2_telemetry | **PASS** | exit 0 in 2.53s |
| `e3_status` | e3_delegation | **PASS** | exit 0 in 0.19s |
| `e3_verify_db` | e3_delegation | **PASS** | schema v2 / all tables present |
| `e4e5_drill_harness` | e3_delegation_e4e5 | **PASS** | 36/36 drill checks, real_provider_calls=0 |
| `regression_runner` | full_regression | **PASS** | 21 suites / 579 collected / 579 passed / 0 failed / 0 unavailable; runner exit 0 |
| `remote_queue_scheduler_state` | remote_queue_watchdog | **PASS** | 9 Chief tasks inspected read-only; 2 configured to survive a reboot (reboot itself not performed) |
| `discord_sync_dry_run` | discord_sync | **PASS** | exit 0 in 0.13s |
| `career_ops_scan_dedupe_write` | career_records | **PASS** | exit 0 in 2.95s |
| `career_ops_cli_inventory` | career_records | **PASS** | exit 0 in 0.92s |
| `regional_jobs_lanes` | regional_jobs | **PASS** | exit 0 in 0.51s |
| `regional_jobs_eligibility_uk` | regional_jobs | **PASS** | exit 0 in 0.51s |
| `regional_jobs_eligibility_dubai` | regional_jobs | **PASS** | exit 0 in 0.49s |
| `regional_jobs_eligibility_japan` | regional_jobs | **PASS** | exit 0 in 0.51s |
| `regional_jobs_eligibility_singapore` | regional_jobs | **PASS** | exit 0 in 0.51s |
| `company_watch_registry` | company_watch | **PASS** | exit 0 in 0.15s |
| `company_watch_handoff_dry_run` | company_watch | **PASS** | exit 0 in 1.04s |
| `application_status_monitor` | application_status | **PASS** | exit 0 in 5.17s |
| `jobbrief_cv_cover_reviewer` | jobbrief_cv_reviewer | **PASS** | exit 0 in 1.13s |
| `cv_cover_linkedin_handoff` | linkedin_draft_readonly | **PASS** | exit 0 in 2.68s |
| `linkedin_outreach_interview_prep` | linkedin_draft_readonly | **PASS** | exit 0 in 0.69s |
| `career_daily_brief` | career_brief | **PASS** | exit 0 in 5.4s |
| `career_brief_status` | career_brief | **PASS** | exit 0 in 0.52s |
| `tracker_rollover` | career_records | **PASS** | exit 0 in 15.98s |
| `owner_escalation_and_gates` | owner_escalation | **PASS** | exit 0 in 0.13s |
| `operational_health_snapshot` | morning_brief | **PASS** | verdict=ATTENTION fail_count=0 attention=2 |
| `morning_chief_brief` | morning_brief | **PASS** | verdict=ATTENTION active=2 blocked=12 owner_actions=18 escalations=3 |
| `operational_backup_dry_run` | backup_restore | **PASS** | exit 0 in 0.16s |
| `backup_restore_drill` | backup_restore | **PASS** | status=PASS; artifacts=10; exit 0 |
| `deployment_preflight` | deployment_prep | **PASS** | verdict=GO; checks=11; fail=0; warn=1 |
| `credential_presence_probe` | owner_gated_credentials | **OWNER_GATED** | presence-only probe: 7/7 API worker credentials absent — owner action, not a defect |

## Roster account

All 50/50 roster items accounted for — see `roster_account.md` (and `roster_account.json`). No UNKNOWN omission.
