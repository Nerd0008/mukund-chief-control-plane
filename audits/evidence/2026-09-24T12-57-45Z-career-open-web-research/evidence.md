# Open-web research lane acceptance — 2026-09-24T12-57-45Z

Status: **PASS** (22/22 checks)

- [x] `query_matrix_covers_role_families` — ["analyst", "cross_family_entry", "cybersecurity", "graduate_new_grad", "grc", "iam", "information_security", "junior_associate", "l1_tier1", "level_coverage", "soc_security_operations", "technology_risk"]
- [x] `query_matrix_covers_owner_ats_site_patterns` — ["ashby", "employer_careers", "google_index", "greenhouse", "icims", "indeed", "lever", "linkedin_jobs", "smartrecruiters", "teamtailor", "workable", "workday"]
- [x] `query_matrix_covers_broad_public_surfaces` — ["linkedin_jobs", "indeed", "google_index"]
- [x] `query_matrix_is_per_region` — ["uk", "dubai", "japan", "singapore"]
- [x] `watchlist_hook_adds_company_queries_and_is_optional` — {"generic": 22, "with_watchlist": 31}
- [x] `surface_classifier_maps_linkedin_indeed_ats_employer` — "all ok"
- [x] `captured_run_normalises_into_the_candidate_schema` — {"candidates": 5}
- [x] `per_result_provenance_is_complete` — "query/surface/url/state/timestamp"
- [x] `a_posting_seen_by_two_queries_collapses_to_one_candidate` — 1
- [x] `every_declared_telemetry_counter_exists` — ["candidate_urls", "deterministic_eligibility_pass", "discovered_unverified", "duplicates_collapsed", "fetch_states", "queries_executed", "rejections_by_reason", "results_seen", "semantically_reviewed", "tracker_candidates", "validated_live", "validation_failed", "zero_attribution"]
- [x] `a_zero_is_attributable_to_the_failing_stage` — {"validation": "no discovered destination validated as live"}
- [x] `a_result_without_an_observed_search_is_never_accepted` — {"search_not_observed": 1}
- [x] `only_the_validated_destination_passes_the_gates` — {"accepted": "accepted", "rejected": 3}
- [x] `unverified_and_failed_destinations_are_refused_by_the_gate` — "deterministic gate reason present"
- [x] `web_research_and_the_regional_lane_collapse_to_one_candidate` — {"shared": 1, "sources": ["explicit records file", "open-web research (codex-style)"]}
- [x] `codex_provider_reports_unavailability_truthfully_when_absent` — "Codex CLI unavailable: RuntimeError: Codex CLI not found (acceptance)"
- [x] `lane_default_run_is_read_only_and_declares_zero_attribution` — {"search": "no live search was observed for the query, so no result from it is accepted (a memory recall is never treated as a search result)", "queries": "no query was executed", "candidate_urls": "no candidate URL was discovered"}
- [x] `canonical_workbooks_byte_identical` — {"uk": "84c53dcb10c2a69a2de0da819498e15b89164cc03f56c655abfdc5d8b6b73f40", "dubai": "495edb450c5f00f235cdefcb73c28e396757ef050a219306cb3ef96c12a745ca", "japan": "a8c4ef9014bd9b852d634bbe945fafe615e5aa873370cc96e7d940ee8df73c89", "singapore": "25c7b95b541a5072f2c1ab8a0cb0e123f78be62195ae3fadcedd7bf3b1e63bf1"}
- [x] `live_codex_web_search_capability_proven` — "available"
- [x] `live_research_produced_real_candidates` — {"queries_executed": 5, "results_seen": 16, "candidates": 14, "source_classes_reached": ["employer_careers", "indeed", "lever", "linkedin_jobs"]}
- [x] `live_research_declares_only_reached_source_classes` — ["employer_careers", "indeed", "lever", "linkedin_jobs"]
- [x] `canonical_workbooks_byte_identical_after_live_pass` — {"uk": "84c53dcb10c2a69a2de0da819498e15b89164cc03f56c655abfdc5d8b6b73f40", "dubai": "495edb450c5f00f235cdefcb73c28e396757ef050a219306cb3ef96c12a745ca", "japan": "a8c4ef9014bd9b852d634bbe945fafe615e5aa873370cc96e7d940ee8df73c89", "singapore": "25c7b95b541a5072f2c1ab8a0cb0e123f78be62195ae3fadcedd7bf3b1e63bf1"}

Raw result URLs stay in the git-ignored runtime directory; this evidence is aggregate only. No canonical workbook was written and no application, outreach, browser or account action occurred.
