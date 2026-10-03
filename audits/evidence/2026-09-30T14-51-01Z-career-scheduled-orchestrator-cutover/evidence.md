# Unified scheduled Career discovery cutover acceptance — 2026-09-30T14-51-01Z

Status: **PASS** (23/23 checks)

Committed revision under test: `95600d94655afc1095ea2089d4304511fabbe8aa` (worktree at run: {"modified_tracked": 2, "untracked": 108})

Live pass attempted: False

- [x] `launcher_invokes_the_unified_orchestrator` — {"active_lines": 12}
- [x] `launcher_requires_a_live_current_web_mechanism` — "--require-live-web present"
- [x] `launcher_uses_the_high_recall_production_policy` — "--mode high_recall present"
- [x] `launcher_no_longer_runs_the_old_single_worker` — "old worker only inside the documented rollback"
- [x] `launcher_keeps_crlf_line_endings` — "CRLF preserved (bytes)"
- [x] `launcher_never_applies_or_submits` — "read-only"
- [x] `production_discovery_policy_is_high_recall` — "high_recall"
- [x] `owner_intern_rule_is_a_declared_diagnostic_only` — "the owner's own Intern/Internship title filter (title_policy.py) kept for diagnostic/compare runs only; it is never the scheduled discovery gate"
- [x] `five_coverage_states_are_declared` — ["blocked", "not_applicable", "reached", "searched_no_results", "unavailable"]
- [x] `every_required_source_class_is_declared` — ["public_linkedin_jobs", "public_indeed", "web_index", "ats_employer_careers"]
- [x] `budgets_lock_and_rollback_are_declared` — "budgets/lock/rollback/no-go present"
- [x] `operational_documentation_covers_required_sections` — "complete"
- [x] `no_browser_or_gui_imports_on_this_path` — "clean"
- [x] `whole_company_regression_run_all_completes` — {"rc": 0}
- [x] `one_unified_run_covers_all_four_regions` — ["dubai", "japan", "singapore", "uk"]
- [x] `one_unified_candidate_manifest_is_written` — {"records": 5, "tracker_candidates": 4}
- [x] `aggregate_counters_are_the_sum_of_the_regions` — "sum verified"
- [x] `every_region_records_a_source_coverage_matrix` — {"dubai": {"public_linkedin_jobs": "not_applicable", "public_indeed": "not_applicable", "web_index": "not_applicable", "ats_employer_careers": "reached"}, "japan": {"public_linkedin_jobs": "not_applicable", "public_indeed": "not_applicable", "web_index": "not_applicable", "ats_employer_careers": "reached"}, "singapore": {"public_linkedin_jobs": "not_applicable", "public_indeed": "not_applicable", 
- [x] `no_coverage_state_is_the_bare_word_empty` — "states restricted to the declared vocabulary"
- [x] `daily_brief_reads_the_unified_source_coverage` — ["dubai", "japan", "singapore", "uk"]
- [x] `a_repeat_run_is_bounded_and_idempotent` — "offline replay is not live proof"
- [x] `canonical_workbooks_byte_identical_after_the_offline_regression` — {"uk": "10b4181f6af50eafed8a649a9195d77352beedea27cb3298bbc1f26e72562e9c", "dubai": "495edb450c5f00f235cdefcb73c28e396757ef050a219306cb3ef96c12a745ca", "japan": "a8c4ef9014bd9b852d634bbe945fafe615e5aa873370cc96e7d940ee8df73c89", "singapore": "25c7b95b541a5072f2c1ab8a0cb0e123f78be62195ae3fadcedd7bf3b1e63bf1"}
- [x] `canonical_workbooks_byte_identical_after_every_run` — {"uk": "10b4181f6af50eafed8a649a9195d77352beedea27cb3298bbc1f26e72562e9c", "dubai": "495edb450c5f00f235cdefcb73c28e396757ef050a219306cb3ef96c12a745ca", "japan": "a8c4ef9014bd9b852d634bbe945fafe615e5aa873370cc96e7d940ee8df73c89", "singapore": "25c7b95b541a5072f2c1ab8a0cb0e123f78be62195ae3fadcedd7bf3b1e63bf1"}

Raw result URLs stay in the git-ignored runtime directory; this evidence is aggregate only. No canonical workbook was written and no application, outreach, LinkedIn mutation, login, cookie/session or browser action occurred.
