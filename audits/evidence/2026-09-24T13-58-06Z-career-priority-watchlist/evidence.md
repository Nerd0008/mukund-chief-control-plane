# Owner priority watchlist acceptance (B27) — 2026-09-24T13-58-06Z

Status: **PASS** (32/32 checks)

- [x] `watchlist_template_is_a_valid_empty_watchlist` — {"kind": "career-ops.company-watchlist", "companies": 0}
- [x] `an_empty_watchlist_is_valid_and_the_lane_runs_with_zero_companies` — {"empty_lane_companies": 0, "zero_stage": "no_company_in_watchlist"}
- [x] `a_missing_watchlist_file_is_valid_and_says_so` — "no watchlist file at this path — this is valid: the lane runs with zero watchlist companies until the owner supplies the list"
- [x] `names_objects_and_notes_are_accepted_and_malformed_rows_are_reported` — {"companies": ["Bare Name Ltd", "Object Name Ltd"], "malformed": 2}
- [x] `fixture_aliases__duplicate_spellings_collapse` — {"canonical": ["Fixture Security Ltd", "Fixture Security Group", "Overlap Test Ltd", "No Surface Co", "Quiet Roles Ltd"], "collapsed": 2}
- [x] `fixture_aliases__distinct_companies_never_merge` — {"merged_from": ["Fixture Security", "fixture security LTD"], "group_key": "fixturesecuritygroup", "merged_key": "fixturesecurity"}
- [x] `fixture_aliases__every_merge_records_its_basis` — ["legal_form_suffix", "exact_normalised_name"]
- [x] `identity_is_deterministic_and_order_independent` — "mapping identical for the reversed input"
- [x] `declared_ats_families_include_the_required_set_plus_region_specific` — ["ashby", "bamboohr", "breezy", "greenhouse", "icims", "jobcan_hrmos", "jobvite", "lever", "recruitee", "smartrecruiters", "teamtailor", "workable", "workday"]
- [x] `every_declared_family_has_a_site_query_host_labels_and_probe_mode` — ["ashby", "bamboohr", "breezy", "greenhouse", "icims", "jobcan_hrmos", "jobvite", "lever", "recruitee", "smartrecruiters", "teamtailor", "workable", "workday"]
- [x] `fixture_ats_discovery__hosts_classified_on_whole_labels_never_substrings` — "all ok"
- [x] `a_workday_tenant_comes_from_the_url_and_is_never_guessed` — {"tenant": "acme", "no_tenant_host_tenant": null}
- [x] `owner_supplied_careers_url_is_verified_before_it_is_trusted` — {"trusted": "found", "unreachable": "unavailable"}
- [x] `a_structured_board_is_used_only_when_the_payload_names_the_company` — {"attributed": "found", "unattributed": "unknown"}
- [x] `fixture_company_with_no_careers_page_is_unavailable_not_no_jobs` — {"state": "unavailable", "reason": "no structured ATS board was resolved from the deterministic slug guesses (no_vendor_board_resolved_via_slug_guess) — the research lane's careers/ATS discovery query family is what may still resolve the official careers surface; this is UNAVAILABLE/UNKNOWN, not 'no jobs'"}
- [x] `fixture_company_with_a_resolved_surface_and_zero_matching_roles` — {"state": "found", "reason": "no live vacancy destination was observed for this company in this run (results_seen=0, validation_failed=0, listing_pages_refused=0) — a zero observed by this run's own queries, not a market fact"}
- [x] `fixture_ats_discovery__careers_surface_discovered_by_the_research_lane` — {"ats_family": "workday", "source": "discovered_via_research_lane"}
- [x] `both_query_families_are_generated_for_every_company` — {"families": ["official_careers_ats", "company_role_family_research"]}
- [x] `the_careers_family_covers_every_declared_ats_surface_not_one_board` — ["ashby", "greenhouse", "lever", "smartrecruiters", "teamtailor", "workable", "workday"]
- [x] `a_query_limit_never_drops_a_whole_family` — {"planned": 20, "kept": 6}
- [x] `per_company_health_record_is_complete` — {"companies": 5, "fields": ["company", "last_checked", "careers_source_found", "careers_state", "queries_executed", "live_vacancies_observed", "findings", "candidates_after_funnel", "access_blocking_reason", "next_retry_at"]}
- [x] `the_lane_is_published_as_one_more_source_with_the_flag` — {"findings": 6, "companies": 5}
- [x] `the_flag_never_bypasses_the_deterministic_gates` — {"decision": "rejected"}
- [x] `fixture_listing_page_is_never_written_as_a_vacancy` — {"tracker_candidates": 2, "accepted": 4}
- [x] `fixture_duplicate_vacancy_from_company_watch_and_watchlist_collapses_with_both_provenances` — {"duplicates_removed": 2}
- [x] `the_watchlist_is_additive_to_broad_market_search_not_a_replacement` — {"market_only_discovered": 2}
- [x] `fixture_watchlist_vacancy_stays_visible_even_when_not_top_ranked_globally` — {"items": 6, "orders": [0, 1, 2, 3, 4, 5], "companies": ["Fixture Security Group", "Fixture Security Ltd", "No Surface Co", "Overlap Test Ltd"]}
- [x] `a_watchlist_item_that_did_not_reach_the_gates_stays_visible_in_the_section` — {"not_ranked": 2, "items_total": 6}
- [x] `the_read_only_manifest_lists_findings_and_writes_no_tracker` — {"companies": 5, "accepted": 4}
- [x] `the_lane_uses_no_browser_gui_or_signed_in_session` — "no browser/session construct present"
- [x] `no_fixture_claims_a_real_employer_or_vacancy` — {"hosts": 5}
- [x] `canonical_workbooks_byte_identical_before_and_after` — {"uk": "84c53dcb10c2a69a2de0da819498e15b89164cc03f56c655abfdc5d8b6b73f40", "dubai": "495edb450c5f00f235cdefcb73c28e396757ef050a219306cb3ef96c12a745ca", "japan": "a8c4ef9014bd9b852d634bbe945fafe615e5aa873370cc96e7d940ee8df73c89", "singapore": "25c7b95b541a5072f2c1ab8a0cb0e123f78be62195ae3fadcedd7bf3b1e63bf1"}

Read-only: no canonical workbook was written and no application, outreach, browser or account action occurred.
