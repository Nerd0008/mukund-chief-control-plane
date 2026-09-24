# Company Watch — bounded integration evidence (20260924T022701Z)

- Task: `agent-company-watch-recovery-final-pass-2026-09-24`
- Region: `uk`
- Started / finished (UTC): 2026-09-24T02:27:01+00:00 → 2026-09-24T02:27:24+00:00 (23.2 s)
- Registry source: `C:\Users\mukun\Documents\ChatGPT\CV customizer\uk_application_company_history_18_months.md`
- Registry source SHA-256: `2fb46ce8e1da0508327940e6f7518f328810338ac3d2abc47027ada29d8dc663`
- Registry counts (parsed): {"employer": 203, "recruiter": 18, "other_application": 4, "unverified_candidate": 4}
- Declared-vs-parsed mismatches: {}

## Bounded live ATS run

- Companies probed: 12 (selection: {"start_index": 0, "limit": 12, "order": "evidence_class then name", "registry_companies": 229})
- Boards resolved: 1 (by vendor: {"ashby": 1})
- Attribution: {"high": 1, "low": 0, "manual_attribution_required": 11}
- HTTP: {"requests": 58, "ok": 19, "non_200": 39, "total_bytes": 245782}
- Budget exhausted: False

## Findings

- {"findings": 19, "by_decision": {"new": 19}, "tracker_eligible": 0, "owner_filter_eligible": 0, "routed_in_scope": 11, "routed_other_region": 0, "routed_unresolved": 8}
- Owner filters: {"location_always_allow": ["United Kingdom", "UK", "Remote, UK", "UK Remote"], "location_allow": ["United Kingdom", "England", "Scotland", "Wales", "Northern Ireland", "UK", "Remote, UK"], "location_block": ["United States", "USA", "Canada", "India", "Singapore", "Australia", "Abu Dhabi", "Sharjah", "Dubai", "United Arab Emirates", "UAE"], "title_positive": ["Intern", "Internship"], "title_negative": ["Senior", "Principal", "Lead ", "Manager", "Director", "Head of", "Vice President", "VP ", "Staff Security"], "max_posting_age_days": 14, "available": true, "parser": "pyyaml"}
- Shared dedupe: {"tracker": "C:\\Users\\mukun\\Downloads\\codex\\uk-cyber-job-tracker.xlsx", "tracker_sha256": "84c53dcb10c2a69a2de0da819498e15b89164cc03f56c655abfdc5d8b6b73f40", "canonical_data_rows": 34, "cross_month_keys": 154, "cross_month_sources": {"uk-cyber-job-tracker.xlsx": 34, "ledger:data/scan-history.tsv": 146}}

## Handoff

- Eligible-set dry-run against the canonical workbook: {"invoked": false, "mode": "dry-run", "exit_code": null, "counts": null, "tracker": null, "canonical_untouched": true, "note": "no eligible records for the strictly filtered set"}
- Marked-sample dry-run against the canonical workbook: {"invoked": true, "mode": "dry-run", "exit_code": 0, "counts": {"input": 3, "appended": 3, "duplicates": 0, "rejected": 0, "refreshed": 0}, "tracker": "C:\\Users\\mukun\\Downloads\\codex\\uk-cyber-job-tracker.xlsx", "rows_are_test_marked": true, "canonical_untouched": true, "note": "marked sample so the canonical dedupe path is exercised; --apply is NOT passed and the canonical workbook hash is re-checked after the call"}

## Acceptance write (safe copy)

- Copy: `runtime\company-watch\acceptance-recovery\uk-cyber-job-tracker.xlsx`
- Copies offered: 3 (of which 3 test rows)
- Copy SHA-256: 84c53dcb10c2a69a2de0da819498e15b89164cc03f56c655abfdc5d8b6b73f40 → b8a2b88b10100356ecce34502f2e7a1f7bc6d2045d3ba48b16d8cee2275b6af6
- First apply: exit 0, counts {"input": 3, "appended": 3, "duplicates": 0, "rejected": 0, "refreshed": 0}
- Repeat apply (dedupe proof): exit 1, counts {"input": 3, "appended": 0, "duplicates": 3, "rejected": 0, "refreshed": 0}
- Note: exit 1 on the repeat is the Career Ops writer's documented nothing-to-append signal for `--apply` (career_ops_cli.cmd_write), not an error; appended 0 with 3 duplicates is the dedupe proof.
- Data rows after: 37
- Canonical workbook untouched: True

## Monthly operational workbook

- Path: `C:\Users\mukun\Downloads\codex\company-watch\Company_Watch_2026-09.xlsx`
- Sheets: ["README", "Watch List", "Findings", "Tracker Handoff", "Run Log"]
- Archive-glob conflict check: {"path": "C:\\Users\\mukun\\Downloads\\codex\\company-watch\\Company_Watch_2026-09.xlsx", "name": "Company_Watch_2026-09.xlsx", "archive_glob_conflicts": [], "safe": true}
- Forbidden application-state columns found: []

Per-company registry and per-posting findings name owner job-search history and are kept in git-ignored runtime paths; this evidence records aggregate counts and verification results only.
