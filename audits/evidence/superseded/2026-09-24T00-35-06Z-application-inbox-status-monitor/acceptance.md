# Application Inbox / Status Monitor — acceptance evidence

- Task: `agent-application-inbox-status-monitor-2026-09-23`
- Run: 2026-09-24T00-35-06Z (4.4s)
- Code SHA: `b4727cf0040742c48dadfcbea97670f3dc08d6d7`
- Verdict: **PASS**
- Checks: 33/33 passed

## Evidence modes

- `repo_fixture_mailbox`: EXECUTED — synthetic committed fixtures
- `canonical_derived_synthetic_mailbox`: EXECUTED — synthetic message envelopes referencing real canonical rows, read-only
- `live_mailbox`: NOT RUN — no Gmail credentials exist on this machine

## Adapters

- `local_mailbox`: {"implemented": true, "tested": true, "available": true}
- `gmail_readonly`: {"implemented": true, "tested": "interface+refusal only", "available": false, "fetch_path_executed": false, "verification": "UNVERIFIED", "reason": "adapter is disabled in configuration; the owner-exported local mailbox path is the active one"}

## Canonical workbooks (read-only, hash-verified unchanged)

- uk: 34 rows, sha256 `84c53dcb10c2a69a…`, unchanged=True
- dubai: 21 rows, sha256 `495edb450c5f00f2…`, unchanged=True
- japan: 41 rows, sha256 `a8c4ef9014bd9b85…`, unchanged=True
- singapore: 22 rows, sha256 `25c7b95b541a5072…`, unchanged=True

## Counts

```
{
  "fixture": {
    "messages": 16,
    "already_ingested": 0,
    "new_signals": 16,
    "unknown": 5,
    "ambiguous_classification": 2,
    "matched_high": 0,
    "matched_medium": 0,
    "ambiguous_match": 0,
    "unmatched": 16,
    "status_events": 0,
    "no_status_events": 0,
    "already_recorded_events": 0,
    "owner_actions": 14,
    "review_items": 16,
    "signals_by_kind": {
      "application_acknowledgement": 4,
      "interview_invite": 2,
      "rejection": 2,
      "unknown": 5,
      "assessment_invite": 1,
      "follow_up_request": 1,
      "recruiter_outreach": 1
    }
  },
  "derived": {
    "messages": 6,
    "already_ingested": 0,
    "new_signals": 6,
    "unknown": 1,
    "ambiguous_classification": 0,
    "matched_high": 4,
    "matched_medium": 0,
    "ambiguous_match": 0,
    "unmatched": 2,
    "status_events": 4,
    "no_status_events": 0,
    "already_recorded_events": 0,
    "owner_actions": 5,
    "review_items": 2,
    "signals_by_match": {
      "matched": 4,
      "unmatched": 2
    },
    "signals_by_kind": {
      "application_acknowledgement": 3,
      "rejection": 1,
      "interview_invite": 1,
      "unknown": 1
    }
  }
}
```

## Proposals and safety

```
{
  "proposals": {
    "total": 4,
    "all_within_region_vocabulary": true,
    "all_requiring_owner_confirmation": true,
    "state_written_to_workbook": 0
  },
  "idempotency": {
    "replay_new_signals": 0,
    "replay_new_events": 0,
    "store_byte_identical": true
  },
  "safety": {
    "emails_sent": 0,
    "replies_sent": 0,
    "mailbox_mutations": 0,
    "workbooks_written": 0,
    "applications_created": 0,
    "canonical_workbooks_unchanged": true,
    "mutations_refused": 12,
    "ingest_path_network_used": false
  }
}
```

## Checks

- [x] fixture_run_completed
- [x] fixture_expected_kinds_present
- [x] fixture_unknown_never_guessed
- [x] fixture_ambiguous_classification_flagged
- [x] fixture_contradictory_message_left_for_human
- [x] fixture_nothing_matched_so_no_state_proposed
- [x] fixture_evidence_mode_labelled
- [x] non_envelope_files_skipped_not_guessed
- [x] derived_mailbox_generated_with_real_canonical_references
- [x] derived_run_completed
- [x] derived_url_match_exercised
- [x] derived_id_reference_match_exercised
- [x] derived_unmatched_still_unmatched
- [x] derived_status_proposals_created
- [x] derived_no_applications_created
- [x] proposed_statuses_are_in_region_vocabulary
- [x] unrecorded_application_requires_owner_confirmation
- [x] state_never_written_to_workbook
- [x] replay_adds_no_signals
- [x] replay_adds_no_events
- [x] store_is_byte_identical_on_replay
- [x] canonical_workbooks_unchanged
- [x] default_runtime_store_untouched
- [x] no_workbooks_written
- [x] no_mail_sent
- [x] no_mailbox_mutations
- [x] ingest_path_declares_no_network
- [x] every_mailbox_mutation_refused
- [x] gmail_adapter_reports_unavailable
- [x] gmail_fetch_refuses_without_credentials
- [x] gmail_scope_is_read_only
- [x] no_credential_contents_reported
- [x] ingest_module_imports_no_network_or_mail_library

Raw signal and status store (git-ignored): `C:\Users\mukun\Documents\mukund-chief-control-plane\audits\evidence\2026-09-24T00-35-06Z-application-inbox-status-monitor\status-store`

No live mailbox evidence is claimed: no Gmail credentials exist on this machine, so the Gmail read-only adapter reports itself UNVERIFIED and refused the fetch.
