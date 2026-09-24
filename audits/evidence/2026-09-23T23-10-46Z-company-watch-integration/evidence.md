# Company Watch — bounded integration evidence (20260923T231046Z)

- Task: `agent-company-watch-job-search-integration-2026-09-23`
- Region: `uk`
- Started / finished (UTC): 2026-09-23T23:10:46+00:00 → 2026-09-23T23:12:43+00:00 (116.6 s)
- Registry source: `C:\Users\mukun\Documents\ChatGPT\CV customizer\uk_application_company_history_18_months.md`
- Registry source SHA-256: `2fb46ce8e1da0508327940e6f7518f328810338ac3d2abc47027ada29d8dc663`
- Registry counts (parsed): {"employer": 203, "recruiter": 18, "other_application": 4, "unverified_candidate": 4}
- Declared-vs-parsed mismatches: {}

## Bounded live ATS run

- Companies probed: 60 (selection: {"start_index": 0, "limit": 60, "order": "evidence_class then name", "registry_companies": 229})
- Boards resolved: 8 (by vendor: {"ashby": 2, "greenhouse": 4, "smartrecruiters": 2})
- Attribution: {"high": 6, "low": 2, "manual_attribution_required": 54}
- HTTP: {"requests": 300, "ok": 82, "non_200": 218, "total_bytes": 1016662}
- Budget exhausted: False

## Findings

- {"findings": 594, "by_decision": {"new": 507, "duplicate-in-run": 87}, "tracker_eligible": 0, "owner_filter_eligible": 0, "routed_in_scope": 64, "routed_other_region": 4, "routed_unresolved": 526}
- Owner filters: {"location_always_allow": ["United Kingdom", "UK", "Remote, UK", "UK Remote"], "location_allow": ["United Kingdom", "England", "Scotland", "Wales", "Northern Ireland", "UK", "Remote, UK"], "location_block": ["United States", "USA", "Canada", "India", "Singapore", "Australia", "Abu Dhabi", "Sharjah", "Dubai", "United Arab Emirates", "UAE"], "title_positive": ["Intern", "Internship"], "title_negative": ["Senior", "Principal", "Lead ", "Manager", "Director", "Head of", "Vice President", "VP ", "Staff Security"], "max_posting_age_days": 14, "available": true, "parser": "pyyaml"}
- Shared dedupe: {"tracker": "C:\\Users\\mukun\\Downloads\\codex\\uk-cyber-job-tracker.xlsx", "tracker_sha256": "84c53dcb10c2a69a2de0da819498e15b89164cc03f56c655abfdc5d8b6b73f40", "canonical_data_rows": 34, "cross_month_keys": 154, "cross_month_sources": {"uk-cyber-job-tracker.xlsx": 34, "ledger:data/scan-history.tsv": 146}}

## Handoff

- Dry-run against canonical workbook: {"invoked": false, "mode": "dry-run", "exit_code": null, "counts": null, "tracker": null, "canonical_untouched": true}

## Acceptance write (safe copy)

- Copy: `runtime\company-watch\acceptance\uk-cyber-job-tracker.xlsx`
- Copies offered: 3 (of which 3 test rows)
- Copy SHA-256: 84c53dcb10c2a69a2de0da819498e15b89164cc03f56c655abfdc5d8b6b73f40 → a634cfd3046dde2ca4cdd8f9e12edc292a2280a3c76cdb30c0a3af555e63dad1
- First apply: exit 0, counts {"input": 3, "appended": 3, "duplicates": 0, "rejected": 0, "refreshed": 0}
- Repeat apply (dedupe proof): exit 1, counts {"input": 3, "appended": 0, "duplicates": 3, "rejected": 0, "refreshed": 0}
- Data rows after: 37
- Canonical workbook untouched: True

## Monthly operational workbook

- Path: `C:\Users\mukun\Downloads\codex\company-watch\Company_Watch_2026-09.xlsx`
- Sheets: ["README", "Watch List", "Findings", "Tracker Handoff", "Run Log"]
- Archive-glob conflict check: {"path": "C:\\Users\\mukun\\Downloads\\codex\\company-watch\\Company_Watch_2026-09.xlsx", "name": "Company_Watch_2026-09.xlsx", "archive_glob_conflicts": [], "safe": true}
- Forbidden application-state columns found: []

Per-company registry and per-posting findings name owner job-search history and are kept in git-ignored runtime paths; this evidence records aggregate counts and verification results only.
