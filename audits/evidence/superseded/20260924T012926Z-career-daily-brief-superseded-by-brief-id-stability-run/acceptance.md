# Career Daily Brief / Pipeline Prioritizer (B23) acceptance — 20260924T012926Z

Overall: PASS  
Code SHA: `26908646d126a4b5a4249cb31710eef253bd1ab4`  
Brief: `cdb-20260924T070000Z-ceba76cd` (content digest `ceba76cded33dcaf…`)  
Canonical workbooks unchanged: YES

## Checks

| check | result |
|---|---|
| stage1 the live brief parses and carries every required section | PASS |
| stage1 the brief is marked read-only with its source of truth | PASS |
| stage1 the declared priority policy is carried with its hash | PASS |
| stage2 an empty-input run still builds a valid brief | PASS |
| stage2 every missing input is reported, none is read as healthy or zero | PASS |
| stage2 no priority item is invented from absent inputs | PASS |
| stage3 a partial-input run still builds a valid brief | PASS |
| stage3 the absent owner-action file is named as a missing input | PASS |
| stage3 no owner action is invented when the owner-action file is absent | PASS |
| stage3 an unavailable input section reports unavailable plus its reason | PASS |
| stage4 a repeat run yields the same digest and the same input fingerprint | PASS |
| stage4 a repeat run writes no new bytes and says so | PASS |
| stage4 a run inside the same declared quantum is the same brief and writes nothing | PASS |
| stage4 the brief reports the quantum its identity is derived from | PASS |
| stage4 a different window is a genuinely different brief | PASS |
| stage5 every score equals the sum of its declared component contributions | PASS |
| stage5 no unknown input is also reported as a known component | PASS |
| stage5 a zero-coverage item is labelled unscoreable, never silently scored | PASS |
| stage5 unknowns are recorded with a reason | PASS |
| stage6 regional scan health is present for every scheduled region | PASS |
| stage6 newly added jobs and duplicates suppressed are both reported | PASS |
| stage6 application-status changes are reported (zero is stated, not omitted) | PASS |
| stage6 interview/follow-up items are reported | PASS |
| stage6 owner actions are reported with their open/unknown split | PASS |
| stage6 a region whose tracker has no deadline column is labelled unknown | PASS |
| stage7 the canonical workbooks are byte-identical after the run | PASS |
| stage7 the brief records zero submissions, zero messages, zero canonical writes | PASS |
| stage7 no external delivery channel is claimed healthy | PASS |
| stage7 the local write is verified by sha256 read-back | PASS |
| stage8 the Chief summary is concise and factual | PASS |
| stage8 the summary states the delivery channel honestly | PASS |
| stage9 a morning schedule is declared for the brief | PASS |
| stage9 the scheduled launcher exists | PASS |
| stage9 the task state is read from Task Scheduler, not assumed | PASS |

## Chief-facing summary produced by this run

```
Career Daily Brief — 2026-09-24T07:00:00+00:00 (window 24h)
Status: 0 new tracker row(s); 8 dated deadline(s); 15 open owner action(s); 6 unknown(s) recorded
Scan health: uk=ok(ok, 6.73h); dubai=ok(ok, 6.7h); japan=ok(ok, 6.68h); singapore=ok(ok, 6.68h)
New: 0 tracker row(s) in window, 5 scan offer(s) needing a URL
Duplicates suppressed: scan=3, prior-run=2, writer=0
Deadlines known: 8 (unknown: 1 region(s) have no deadline column: uk)
Application status: 0 proposal(s), 0 owner action(s) from the monitor
Interviews/follow-ups: 0 prep pack(s)
Owner actions: 15 open, 0 with no readable status
Priorities:
  P2 score 63.0 (coverage 85.0%) tracker_row japan JP-20260911-03 — Security Engineer - SOC, Vulnerability & Zero Trust [unknown: eligibility_certainty]
  P2 score 63.0 (coverage 85.0%) tracker_row japan JP-20260911-02 — Security Patch Updates / Infrastructure Operations [unknown: eligibility_certainty]
  P2 score 63.0 (coverage 85.0%) tracker_row japan JP-20260911-04 — Infrastructure Security Operations [unknown: eligibility_certainty]
  P2 score 63.0 (coverage 85.0%) tracker_row japan JP-20260911-05 — Infrastructure Monitoring & Alert Design [unknown: eligibility_certainty]
  P2 score 63.0 (coverage 85.0%) tracker_row japan JP-20260911-01 — Entry-level Security Log Collection & Analysis [unknown: eligibility_certainty]
  P2 score 52.5 (coverage 85.0%) tracker_row japan JP-20260914-02 — 2027 New Graduate Engineer [unknown: eligibility_certainty]
  P2 score 48.0 (coverage 70.0%) tracker_row dubai DUBAI-2026-09-01-07 — Cybersecurity Consultant [unknown: eligibility_certainty,freshness]
  P2 score 24.0 (coverage 30.0%) owner_action - owner-action-1-configure-all-remaining-provider-credentials — Configure all remaining provider credentials [unknown: deadline,eligibility_certainty,freshness]
  P2 score 24.0 (coverage 30.0%) owner_action - owner-action-10-two-tracker-vocabulary-gaps-worth-a-decision-not — Two tracker-vocabulary gaps worth a decision (not blocking) [unknown: deadline,eligibility_certainty,freshness]
  P2 score 24.0 (coverage 30.0%) owner_action - owner-action-11-optional-authorise-a-company-role-research-provi — Optional — authorise a company/role research provider [unknown: deadline,eligibility_certainty,freshness]
  P2 score 24.0 (coverage 30.0%) owner_action - owner-action-13-decide-whether-the-live-linkedin-surface-should- — Decide whether the live LinkedIn surface should ever have account access [unknown: deadline,eligibility_certainty,freshness]
  P2 score 24.0 (coverage 30.0%) owner_action - owner-action-14-decide-whether-the-career-daily-brief-should-be- — Decide whether the Career Daily Brief should be *delivered* anywhere (not blocking) [unknown: deadline,eligibility_certainty,freshness]
Unknowns: 6 item(s) — uk: tracker schema has no deadline column, so deadline is UNKNOWN for all 34 row(s); recorded work-authorisation state is UNKNOWN — not resolved to a known position; no posting date or date-found value in the source record
Delivery: channel=local_file mode=write (sha256 read-back); external channels not_verified
Safety: read-only aggregation; no submission, no outreach, no canonical write.
```

## Counts

- scan regions: {"uk": {"health": "ok", "last_status": "ok", "age_hours": 6.73, "accepted": 0, "duplicates_suppressed": {"scan_duplicates": 1, "policy_duplicate_prior_run": 2, "writer_duplicates": 0}, "new_offers_without_url": 1}, "dubai": {"health": "ok", "last_status": "ok", "age_hours": 6.7, "accepted": 0, "duplicates_suppressed": {"scan_duplicates": 0, "policy_duplicate_prior_run": 0, "writer_duplicates": 0}, "new_offers_without_url": 0}, "japan": {"health": "ok", "last_status": "ok", "age_hours": 6.68, "accepted": 0, "duplicates_suppressed": {"scan_duplicates": 0, "policy_duplicate_prior_run": 0, "writer_duplicates": 0}, "new_offers_without_url": 0}, "singapore": {"health": "ok", "last_status": "ok", "age_hours": 6.68, "accepted": 0, "duplicates_suppressed": {"scan_duplicates": 2, "policy_duplicate_prior_run": 0, "writer_duplicates": 0}, "new_offers_without_url": 4}}
- newly added jobs: {"tracker_rows_in_window": 0, "scan_offers_without_url": 5}
- duplicates suppressed: {"scan_duplicates": 3, "policy_duplicate_prior_run": 2, "writer_duplicates": 0}
- application-status changes: {"signals_ingested": 0, "status_events": 0, "proposed_status_changes": 0, "owner_actions_required": 0, "review_items": 0}
- interviews/follow-ups: {"packs": 0, "pack_items": 0, "application_rows_past_first_stage": 0}
- owner actions: {"items_parsed": 17, "open": 15, "unknown_status": 0, "from_monitor": 0}
- deadlines: {"deadlines_known": 8, "deadlines_unknown_regions": 1} (no deadline column: ['uk'])
- priority items: 30, unknowns: 6

## Not performed

- Any application submission or application preparation action
- Any contact with an employer, recruiter, agency or candidate
- Any LinkedIn or other social-platform action
- Any write to a canonical tracker or any other workflow's store
- Any invented deadline, eligibility position, priority score component, metric or owner state
- Any interactive browser, GUI application or network call
