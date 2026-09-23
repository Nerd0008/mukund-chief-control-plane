# E4/E5 real-path drill evidence (stubbed provider failures)

- Task: `agent-e4e5-real-path-drill-harness-and-readiness-2026-09-23`
- Authority: `tasks-or-issues/2026-09-24-full-operational-vps-cutover.md`
- Code SHA: `bd0a7aaccf5b1c272181ad5d100b2071cac4d12a`
- Run started (UTC): 2026-09-23T23:55:06.425825+00:00
- Run finished (UTC): 2026-09-23T23:55:06.928692+00:00
- Evidence kind: `stubbed_provider_failure` — provider transport is a recorded in-process stub; these drills evidence OUR handling of injected failures on the real execution path and are NOT real external provider evidence
- Real provider calls: **0** (stub dispatches: 10)
- Stage 2 enabled: False; deployment performed: False
- Checks: **33/33 passed**

## Isolation

- Isolated orchestration DB: `C:\Users\mukun\AppData\Local\Temp\e4e5-drills-17_1uhao\orchestration.db`
- Live stores changed: none
- E2 rows written: 0 (stubbed (no live governor row written))

## Checks

| Check | Result |
|---|---|
| D1_checkpoint_created | PASS |
| D1_checkpoint_restore_matches_saved | PASS |
| D1_primary_worker_failed | PASS |
| D1_equivalent_worker_selected | PASS |
| D1_handover_state_delivered | PASS |
| D1_replacement_verified_complete | PASS |
| D1_failover_log_ordered | PASS |
| D1_failover_not_fabricated | PASS |
| D2_no_equivalent_returns_none | PASS |
| D2_owner_escalation_recorded | PASS |
| D2_quality_floor_not_lowered | PASS |
| D3_reported_outage_fails_node | PASS |
| D3_raised_transport_error_caught | PASS |
| D3_errors_recorded_verbatim | PASS |
| D3_no_failover_claimed | PASS |
| D4_validator_flags_structural_malformation | PASS |
| D4_validator_shallow_precheck_recorded | PASS |
| D4_sanitizer_strips_non_printables | PASS |
| D4_malformed_rejected_by_verifier | PASS |
| D4_repair_path_converges | PASS |
| D5_cap_bounded_no_infinite_loop | PASS |
| D5_quarantine_escalated | PASS |
| D5_safe_mode_entered | PASS |
| D6_safe_mode_event_persisted | PASS |
| D6_recovery_refused_without_override | PASS |
| D6_recovery_refused_when_unhealthy | PASS |
| D6_owner_override_audited | PASS |
| D6_recovery_succeeded | PASS |
| D6_mode_normal_after_recovery | PASS |
| D6_no_active_events_after_recovery | PASS |
| D1_live_registry_read_via_snapshot | PASS |
| isolation_live_stores_untouched | PASS |
| no_real_provider_calls | PASS |

## Drill detail

### D1 — D1_checkpoint_failover_handover

```json
{
  "drill": "D1_checkpoint_failover_handover",
  "plan_id": "drill-e4-failover",
  "task_id": "drill-task-e4-1",
  "expected_token": "HANDOVER-5501",
  "checkpoint": {
    "checkpoint_id": "ckpt-4f1cc980884b",
    "state_saved": {
      "attempt": 1,
      "completed_substeps": [
        "read_objective",
        "draft_outline"
      ],
      "residual_requirement": "reply with exactly HANDOVER-5501",
      "checkpoint_reason": "resource_driven_pre_dispatch"
    },
    "checkpoints_for_task": [
      {
        "checkpoint_id": "ckpt-4f1cc980884b",
        "node_id": "node-drill-e4-failover-1",
        "created_at": "2026-09-23T23:55:06.529219"
      }
    ],
    "restored": {
      "state": {
        "attempt": 1,
        "completed_substeps": [
          "read_objective",
          "draft_outline"
        ],
        "residual_requirement": "reply with exactly HANDOVER-5501",
        "checkpoint_reason": "resource_driven_pre_dispatch"
      },
      "created_at": "2026-09-23T23:55:06.529219"
    },
    "restore_matches_saved": true
  },
  "primary_dispatch": {
    "worker_id": "deepseek-v41-flash",
    "stub_behaviour": "transport_error",
    "node_state": "FAILED",
    "dispatch_attempts": [
      {
        "attempt": 1,
        "dispatch_id": null,
        "status": "FAILED",
        "provider": null,
        "model": null,
        "error": "ProviderOutage: stub outage: deepseek-v41-flash unreachable",
        "runtime_s": 0.0,
        "usage": null,
        "usage_exposed": false,
        "objective_hash": "0bf6af515a19",
        "e2_request_id": "e2-stub-f8dad87c",
        "content_present": false,
        "finish_reason": null,
        "image_mime": null,
        "image_dims": null,
        "image_size_bytes": null,
        "image_decode_ok": null,
        "prompt_feedback": null,
        "requested_model": null,
        "candidate_count": null,
        "candidate_finish_reasons": null,
        "response_part_kinds": null,
        "response_text_chars": null,
        "response_text_excerpt": null
      }
    ],
    "verification_attempts": [
      {
        "attempt": 1,
        "method": "test",
        "outcome": "FAIL",
        "passed": false,
        "issues": [
          "Test 'node-drill-e4-failover-1 exact token': expected HANDOVER-5501, got None"
        ]
      }
    ],
    "failure_attribution": "verification_fail",
    "persisted_node": {
      "node_id": "node-drill-e4-failover-1",
      "plan_id": "drill-e4-failover",
      "task_subtask_id": null,
      "objective": "Drill objective. Reply with exactly HANDOVER-5501.",
      "capability_roles": "[\"builder\"]",
      "dependencies": "[]",
      "inputs": "{}",
      "expected_outputs": "{}",
      "floor_id": null,
      "allowed_tools": "[]",
      "permissions": "{}",
      "verification_method": "test",
      "assigned_worker": "deepseek-v41-flash",
      "fallback_candidates": "[]",
      "state": "FAILED",
      "attempts": 1,
      "defect_attempts": "{}",
      "created_at": "2026-09-23 23:55:06",
      "updated_at": "2026-09-23 23:55:06"
    }
  },
  "equivalent_selection": {
    "worker_id": "codex-cli",
    "task_family": "code",
    "role": "builder",
    "equivalence": "partial",
    "reason": "Same role/task family qualified worker available"
  },
  "capability_fixture": {
    "kind": "drill_fixture_not_qualification_evidence",
    "db": "isolated drill orchestration db",
    "records": [
      {
        "worker_id": "deepseek-v41-flash",
        "task_family": "code",
        "capability_role": "builder",
        "previous_state": "UNPROVEN",
        "new_state": "QUALIFIED",
        "evidence_count": 1,
        "first_pass_successes": 0,
        "first_pass_attempts": 0,
        "recorded_at": "2026-09-23T23:55:06.517228"
      },
      {
        "worker_id": "codex-cli",
        "task_family": "code",
        "capability_role": "builder",
        "previous_state": "UNPROVEN",
        "new_state": "QUALIFIED",
        "evidence_count": 1,
        "first_pass_successes": 0,
        "first_pass_attempts": 0,
        "recorded_at": "2026-09-23T23:55:06.520234"
      }
    ]
  },
  "live_registry_read_only": {
    "source": "live_registry_read_only_snapshot",
    "db_path": "C:\\Users\\mukun\\AppData\\Local\\hermes\\exec-brain\\orchestration.db",
    "snapshot_path": "C:\\Users\\mukun\\AppData\\Local\\Temp\\e4e5-drills-17_1uhao\\live-registry-snapshot\\live-orchestration-snapshot.db",
    "live_file_untouched": true,
    "rows": [
      {
        "worker_id": "codex-cli",
        "task_family": "code",
        "capability_role": "builder",
        "state": "QUALIFIED",
        "evidence_count": 3,
        "first_pass_successes": 3,
        "first_pass_attempts": 3
      },
      {
        "worker_id": "deepseek-v41-flash",
        "task_family": "code",
        "capability_role": "builder",
        "state": "QUALIFIED",
        "evidence_count": 8,
        "first_pass_successes": 3,
        "first_pass_attempts": 8
      }
    ]
  },
  "handover": {
    "from_worker": "deepseek-v41-flash",
    "to_worker": "codex-cli",
    "restored_checkpoint_id": "ckpt-4f1cc980884b",
    "restored_state": {
      "attempt": 1,
      "completed_substeps": [
        "read_objective",
        "draft_outline"
      ],
      "residual_requirement": "reply with exactly HANDOVER-5501",
      "checkpoint_reason": "resource_driven_pre_dispatch"
    },
    "failed_node_state": "FAILED",
    "failed_dispatch_errors": [
      "ProviderOutage: stub outage: deepseek-v41-flash unreachable"
    ]
  },
  "handover_objective_hash": "fad233b817d5",
  "handover_objective_delivered_to_replacement": true,
  "replacement_dispatch": {
    "worker_id": "codex-cli",
    "node_state": "COMPLETE",
    "dispatch_attempts": [
      {
        "attempt": 1,
        "dispatch_id": "stub-codex-cli-1",
        "status": "COMPLETED",
        "provider": "stub",
        "model": "codex-cli-stub",
        "error": null,
        "runtime_s": 0.0,
        "usage": null,
        "usage_exposed": false,
        "objective_hash": "fad233b817d5",
        "e2_request_id": "e2-stub-8f74700d",
        "content_present": true,
        "finish_reason": null,
        "image_mime": null,
        "image_dims": null,
        "image_size_bytes": null,
        "image_decode_ok": null,
        "prompt_feedback": null,
        "requested_model": null,
        "candidate_count": null,
        "candidate_finish_reasons": null,
        "response_part_kinds": null,
        "response_text_chars": null,
        "response_text_excerpt": null
      }
    ],
    "verification_attempts": [
      {
        "attempt": 1,
        "method": "test",
        "outcome": "PASS",
        "passed": true,
        "issues": []
      }
    ],
    "final_verification": "PASS",
    "evidence_id": "evidence-1915c0390179",
    "persisted_node": {
      "node_id": "node-drill-e4-failover-1",
      "plan_id": "drill-e4-failover",
      "task_subtask_id": null,
      "objective": "Drill objective. Reply with exactly HANDOVER-5501.",
      "capability_roles": "[\"builder\"]",
      "dependencies": "[]",
      "inputs": "{}",
      "expected_outputs": "{}",
      "floor_id": null,
      "allowed_tools": "[]",
      "permissions": "{}",
      "verification_method": "test",
      "assigned_worker": "codex-cli",
      "fallback_candidates": "[]",
      "state": "COMPLETE",
      "attempts": 1,
      "defect_attempts": "{}",
      "created_at": "2026-09-23 23:55:06",
      "updated_at": "2026-09-23 23:55:06"
    }
  },
  "failover_state_log": [
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "PLANNED",
      "new_state": "READY",
      "cause": "dependencies_satisfied",
      "dispatch_reference": null,
      "verification_reference": null,
      "timestamp": "2026-09-23 23:55:06"
    },
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "READY",
      "new_state": "RUNNING",
      "cause": "dispatch_attempt_1",
      "dispatch_reference": null,
      "verification_reference": null,
      "timestamp": "2026-09-23 23:55:06"
    },
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "RUNNING",
      "new_state": "VERIFYING",
      "cause": "verify_attempt_1",
      "dispatch_reference": null,
      "verification_reference": null,
      "timestamp": "2026-09-23 23:55:06"
    },
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "VERIFYING",
      "new_state": "FAILED",
      "cause": "verification_failed_no_repair_budget_attempt_1",
      "dispatch_reference": null,
      "verification_reference": "verify-node-drill-e4-failover-1-1",
      "timestamp": "2026-09-23 23:55:06"
    },
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "PLANNED",
      "new_state": "READY",
      "cause": "dependencies_satisfied",
      "dispatch_reference": null,
      "verification_reference": null,
      "timestamp": "2026-09-23 23:55:06"
    },
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "READY",
      "new_state": "RUNNING",
      "cause": "dispatch_attempt_1",
      "dispatch_reference": null,
      "verification_reference": null,
      "timestamp": "2026-09-23 23:55:06"
    },
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "RUNNING",
      "new_state": "VERIFYING",
      "cause": "verify_attempt_1",
      "dispatch_reference": "stub-codex-cli-1",
      "verification_reference": null,
      "timestamp": "2026-09-23 23:55:06"
    },
    {
      "node_id": "node-drill-e4-failover-1",
      "previous_state": "VERIFYING",
      "new_state": "COMPLETE",
      "cause": "verified_pass_attempt_1",
      "dispatch_reference": null,
      "verification_reference": "verify-node-drill-e4-failover-1-1",
      "timestamp": "2026-09-23 23:55:06"
    }
  ],
  "failover_state_log_note": "the replacement dispatch reuses the same node id (real failover), so the persisted log shows the failed cycle followed by the replacement cycle on one node",
  "failover_log_shows_failed_then_complete": true
}
```

### D2 — D2_no_equivalent_escalation

```json
{
  "drill": "D2_no_equivalent_escalation",
  "equivalent_found": null,
  "escalation_record": {
    "escalation_type": "no_equivalent_worker",
    "failed_worker": "deepseek-v41-flash",
    "task_family": "code",
    "role": "verifier",
    "timestamp": "2026-09-23T23:55:06.610017",
    "owner_action": "Provide alternative worker or approve quality floor reduction",
    "auto_approve": false
  },
  "escalation": {
    "escalation_id": "escalate-4313521e1a04",
    "trigger": "no_qualified_worker",
    "context": "Drill: worker failed on role 'verifier' and the capability registry records no qualified equivalent",
    "owner_decision_needed": "Provide alternative worker or approve quality floor reduction",
    "recommended_action": "owner provides an equivalent worker or explicitly approves a floor change"
  },
  "rationale_id": "rationale-493fb25e0c32",
  "active_escalations": 1,
  "gate_result": "OWNER_APPROVAL_REQUIRED",
  "quality_floor_lowered": false
}
```

### D3 — D3_provider_outage

```json
{
  "drill": "D3_provider_outage",
  "variants": {
    "reported_provider_error": {
      "worker_id": "deepseek-v41-flash",
      "node_state": "FAILED",
      "dispatch_attempts": [
        {
          "attempt": 1,
          "dispatch_id": "stub-deepseek-v41-flash-1",
          "status": "FAILED",
          "provider": "stub",
          "model": "deepseek-v41-flash-stub",
          "error": "provider_unavailable: HTTP 503 from stub",
          "runtime_s": 0.0,
          "usage": null,
          "usage_exposed": false,
          "objective_hash": "b588939d9a0b",
          "e2_request_id": "e2-stub-cdaa3df4",
          "content_present": false,
          "finish_reason": null,
          "image_mime": null,
          "image_dims": null,
          "image_size_bytes": null,
          "image_decode_ok": null,
          "prompt_feedback": null,
          "requested_model": null,
          "candidate_count": null,
          "candidate_finish_reasons": null,
          "response_part_kinds": null,
          "response_text_chars": null,
          "response_text_excerpt": null
        }
      ],
      "verification_attempts": [
        {
          "attempt": 1,
          "method": "test",
          "outcome": "FAIL",
          "passed": false,
          "issues": [
            "Test 'node-drill-e5-outage-1 exact token': expected OUTAGE-8801, got None"
          ]
        }
      ],
      "failure_attribution": "verification_fail",
      "blocking_reason": null,
      "evidence_id": "evidence-d0ab841bd296",
      "persisted_node_state": "FAILED",
      "complete": false
    },
    "raised_transport_error": {
      "worker_id": "deepseek-v41-flash",
      "node_state": "FAILED",
      "dispatch_attempts": [
        {
          "attempt": 1,
          "dispatch_id": null,
          "status": "FAILED",
          "provider": null,
          "model": null,
          "error": "ProviderOutage: stub connection reset",
          "runtime_s": 0.0,
          "usage": null,
          "usage_exposed": false,
          "objective_hash": "b588939d9a0b",
          "e2_request_id": "e2-stub-f15f7de1",
          "content_present": false,
          "finish_reason": null,
          "image_mime": null,
          "image_dims": null,
          "image_size_bytes": null,
          "image_decode_ok": null,
          "prompt_feedback": null,
          "requested_model": null,
          "candidate_count": null,
          "candidate_finish_reasons": null,
          "response_part_kinds": null,
          "response_text_chars": null,
          "response_text_excerpt": null
        }
      ],
      "verification_attempts": [
        {
          "attempt": 1,
          "method": "test",
          "outcome": "FAIL",
          "passed": false,
          "issues": [
            "Test 'node-drill-e5-outage-1 exact token': expected OUTAGE-8801, got None"
          ]
        }
      ],
      "failure_attribution": "verification_fail",
      "blocking_reason": null,
      "evidence_id": "evidence-9b6779b34a66",
      "persisted_node_state": "FAILED",
      "complete": false
    }
  },
  "no_node_reached_complete": true,
  "errors_recorded_verbatim": [
    "provider_unavailable: HTTP 503 from stub",
    "ProviderOutage: stub connection reset"
  ],
  "failover_claimed": false
}
```

### D4 — D4_malformed_output

```json
{
  "drill": "D4_malformed_output",
  "malformed_content_repr": "'\\x00\\x01\\x02{{{not json, not the token'",
  "validator": {
    "cases": {
      "none": {
        "valid": false,
        "errors": [
          "Output is None"
        ],
        "warnings": []
      },
      "empty_string": {
        "valid": false,
        "errors": [
          "Output is empty"
        ],
        "warnings": []
      },
      "missing_required_field": {
        "valid": false,
        "errors": [
          "Missing required field: content_stripped"
        ],
        "warnings": []
      },
      "non_empty_garbage_string": {
        "valid": true,
        "errors": [],
        "warnings": []
      }
    },
    "flags_structural_malformation": true,
    "shallow_precheck_passes_garbage_string": true,
    "authority": "the independent deterministic verifier decides contract conformance; the pre-check does not",
    "sanitized_repr": "'{{{not json, not the token'",
    "sanitizer_removed_non_printables": true
  },
  "handler": {
    "worker_id": "deepseek-v41-flash",
    "task_id": "node-drill-e5-malformed-1",
    "validation_error": "output does not match the deterministic contract",
    "is_recoverable": true,
    "action": "retry_with_correction",
    "output_preview": "\u0000\u0001\u0002{{{not json, not the token",
    "timestamp": "2026-09-23T23:55:06.689327"
  },
  "no_repair_budget": {
    "node_state": "FAILED",
    "verification_attempts": [
      {
        "attempt": 1,
        "method": "test",
        "outcome": "FAIL",
        "passed": false,
        "issues": [
          "Test 'node-drill-e5-malformed-1 exact token': expected WELLFORMED-3320, got \u0000\u0001\u0002{{{not json, not the token"
        ]
      }
    ],
    "rejections": [
      {
        "attempt": 1,
        "outcome": "FAIL",
        "issues": [
          "Test 'node-drill-e5-malformed-1 exact token': expected WELLFORMED-3320, got \u0000\u0001\u0002{{{not json, not the token"
        ]
      }
    ],
    "failure_attribution": "verification_fail",
    "dispatch_count": 1
  },
  "with_repair_budget": {
    "node_state": "COMPLETE",
    "dispatch_count": 2,
    "verification_attempts": [
      {
        "attempt": 1,
        "method": "test",
        "outcome": "FAIL",
        "passed": false,
        "issues": [
          "Test 'node-drill-e5-malformed-1 exact token': expected WELLFORMED-3320, got \u0000\u0001\u0002{{{not json, not the token"
        ]
      },
      {
        "attempt": 2,
        "method": "test",
        "outcome": "PASS",
        "passed": true,
        "issues": []
      }
    ],
    "repairs": [
      {
        "attempt": 1,
        "issues": [
          "Test 'node-drill-e5-malformed-1 exact token': expected WELLFORMED-3320, got \u0000\u0001\u0002{{{not json, not the token"
        ]
      }
    ],
    "final_verification": "PASS",
    "state_log": [
      {
        "node_id": "node-drill-e5-malformed-repaired-1",
        "previous_state": "PLANNED",
        "new_state": "READY",
        "cause": "dependencies_satisfied",
        "dispatch_reference": null,
        "verification_reference": null,
        "timestamp": "2026-09-23 23:55:06"
      },
      {
        "node_id": "node-drill-e5-malformed-repaired-1",
        "previous_state": "READY",
        "new_state": "RUNNING",
        "cause": "dispatch_attempt_1",
        "dispatch_reference": null,
        "verification_reference": null,
        "timestamp": "2026-09-23 23:55:06"
      },
      {
        "node_id": "node-drill-e5-malformed-repaired-1",
        "previous_state": "RUNNING",
        "new_state": "VERIFYING",
        "cause": "verify_attempt_1",
        "dispatch_reference": "stub-deepseek-v41-flash-1",
        "verification_reference": null,
        "timestamp": "2026-09-23 23:55:06"
      },
      {
        "node_id": "node-drill-e5-malformed-repaired-1",
        "previous_state": "VERIFYING",
        "new_state": "REWORK",
        "cause": "targeted_repair_after_attempt_1",
        "dispatch_reference": null,
        "verification_reference": "verify-node-drill-e5-malformed-repaired-1-1",
        "timestamp": "2026-09-23 23:55:06"
      },
      {
        "node_id": "node-drill-e5-malformed-repaired-1",
        "previous_state": "REWORK",
        "new_state": "RUNNING",
        "cause": "dispatch_attempt_2",
        "dispatch_reference": null,
        "verification_reference": null,
        "timestamp": "2026-09-23 23:55:06"
      },
      {
        "node_id": "node-drill-e5-malformed-repaired-1",
        "previous_state": "RUNNING",
        "new_state": "VERIFYING",
        "cause": "verify_attempt_2",
        "dispatch_reference": "stub-deepseek-v41-flash-2",
        "verification_reference": null,
        "timestamp": "2026-09-23 23:55:06"
      },
      {
        "node_id": "node-drill-e5-malformed-repaired-1",
        "previous_state": "VERIFYING",
        "new_state": "COMPLETE",
        "cause": "verified_pass_attempt_2",
        "dispatch_reference": null,
        "verification_reference": "verify-node-drill-e5-malformed-repaired-1-2",
        "timestamp": "2026-09-23 23:55:06"
      }
    ]
  },
  "malformed_never_accepted": true
}
```

### D5 — D5_convergence_cap

```json
{
  "drill": "D5_convergence_cap",
  "cap": 3,
  "iterations": [
    {
      "iteration": 1,
      "attempt": 1,
      "node_state": "FAILED",
      "convergence": {
        "worker_id": "deepseek-v41-flash",
        "task_family": "code",
        "failure_count": 1,
        "action_taken": "log_and_retry",
        "escalated": false,
        "timestamp": "2026-09-23T23:55:06.798248"
      }
    },
    {
      "iteration": 2,
      "attempt": 2,
      "node_state": "FAILED",
      "convergence": {
        "worker_id": "deepseek-v41-flash",
        "task_family": "code",
        "failure_count": 2,
        "action_taken": "warn_and_reduce_scope",
        "escalated": false,
        "timestamp": "2026-09-23T23:55:06.827223"
      },
      "mode_transition": "DEGRADED"
    },
    {
      "iteration": 3,
      "attempt": 3,
      "node_state": "FAILED",
      "convergence": {
        "worker_id": "deepseek-v41-flash",
        "task_family": "code",
        "failure_count": 3,
        "action_taken": "quarantine_worker",
        "escalated": true,
        "timestamp": "2026-09-23T23:55:06.860423"
      },
      "mode_transition": "SAFE_MODE"
    },
    {
      "iteration": 4,
      "stopped": true,
      "reason": "Max retries (3) reached for node-drill-e5-convergence-1"
    }
  ],
  "dispatches_performed": 3,
  "loop_terminated_by_cap": true,
  "stop_markers": 1,
  "iterations_total": 4,
  "iterations_bounded": true,
  "convergence_event_count": 3,
  "escalations": [
    {
      "event_id": 3,
      "worker_id": "deepseek-v41-flash",
      "task_family": "code",
      "failure_count": 3,
      "action_taken": "quarantine_worker",
      "created_at": "2026-09-23T23:55:06.860423"
    }
  ],
  "quarantine_recorded": true,
  "system_mode": "SAFE_MODE",
  "active_safe_mode_events": [
    {
      "event_id": 2,
      "trigger_type": "repeated_failure",
      "severity": "safe_mode",
      "description": "convergence cap 3 reached for deepseek-v41-flash",
      "affected_workers": [
        "deepseek-v41-flash"
      ],
      "created_at": "2026-09-23T23:55:06.862458"
    },
    {
      "event_id": 1,
      "trigger_type": "repeated_failure",
      "severity": "degraded",
      "description": "deepseek-v41-flash failed 2x on code",
      "affected_workers": [
        "deepseek-v41-flash"
      ],
      "created_at": "2026-09-23T23:55:06.830223"
    }
  ]
}
```

### D6 — D6_safe_mode_override_and_recovery

```json
{
  "drill": "D6_safe_mode_override_and_recovery",
  "safe_mode_entry": {
    "safe_event_id": 3,
    "active_events_before": []
  },
  "recovery_refused_without_override": {
    "recovered": false,
    "refusal_reasons": [
      "active owner-only safe-mode trigger(s) without a recorded owner override: no_equivalent_worker"
    ],
    "owner_only_event_ids": [
      3
    ],
    "mode_after_refusal": "SAFE_MODE"
  },
  "recovery_refused_when_unhealthy": {
    "recovered": false,
    "refusal_reasons": [
      "health check not healthy: stubbed_local_probe (injected unhealthy probe)",
      "active owner-only safe-mode trigger(s) without a recorded owner override: no_equivalent_worker"
    ]
  },
  "owner_override": {
    "event_id": 4,
    "rationale_id": "rationale-45cedf529cbb",
    "owner": "Mukund",
    "scope": "safe_mode_recovery",
    "reason": "Drill: authorise leaving safe mode for the no-equivalent-worker trigger after the owner supplies an equivalent worker.",
    "recorded_at": "2026-09-23T23:55:06.881735",
    "trigger_type": "owner_override"
  },
  "overrides_before": [],
  "gate_after_override": {
    "can_recover": true,
    "refusal_reasons": [],
    "active_event_ids": [
      4,
      3,
      2,
      1
    ],
    "owner_only_event_ids": [
      3
    ],
    "owner_override_present": true,
    "health": {
      "healthy": true,
      "source": "stubbed_local_probe",
      "detail": "drill db integrity_check=ok",
      "provider_health_verified": false
    }
  },
  "recovery": {
    "recovered": true,
    "gate": {
      "can_recover": true,
      "refusal_reasons": [],
      "active_event_ids": [
        4,
        3,
        2,
        1
      ],
      "owner_only_event_ids": [
        3
      ],
      "owner_override_present": true,
      "health": {
        "healthy": true,
        "source": "stubbed_local_probe",
        "detail": "drill db integrity_check=ok",
        "provider_health_verified": false
      }
    },
    "mode": "NORMAL",
    "resolved_events": [
      {
        "event_id": 4,
        "trigger_type": "owner_override",
        "auto_resolved": true
      },
      {
        "event_id": 3,
        "trigger_type": "no_equivalent_worker",
        "auto_resolved": false
      },
      {
        "event_id": 2,
        "trigger_type": "repeated_failure",
        "auto_resolved": true
      },
      {
        "event_id": 1,
        "trigger_type": "repeated_failure",
        "auto_resolved": true
      }
    ]
  },
  "owner_override_audit_rows": [
    {
      "rationale_id": "rationale-45cedf529cbb",
      "decision_actor": "owner",
      "gate_result": "OWNER_APPROVAL_REQUIRED",
      "concise_rationale": "Owner Mukund authorised safe_mode_recovery: Drill: authorise leaving safe mode for the no-equivalent-worker trigger after the owner supplies an equivalent worker.",
      "timestamp": "2026-09-23T23:55:06.881735"
    }
  ],
  "resolved_event_rows": [
    {
      "event_id": 1,
      "trigger_type": "repeated_failure",
      "auto_resolved": 1,
      "resolved_at": "2026-09-23T23:55:06.893269"
    },
    {
      "event_id": 2,
      "trigger_type": "repeated_failure",
      "auto_resolved": 1,
      "resolved_at": "2026-09-23T23:55:06.890258"
    },
    {
      "event_id": 3,
      "trigger_type": "no_equivalent_worker",
      "auto_resolved": 0,
      "resolved_at": "2026-09-23T23:55:06.887250"
    },
    {
      "event_id": 4,
      "trigger_type": "owner_override",
      "auto_resolved": 1,
      "resolved_at": "2026-09-23T23:55:06.885060"
    }
  ],
  "active_events_after_recovery": [],
  "final_mode": "NORMAL",
  "provider_health_verified": false,
  "provider_health_note": "the drill's health probe is a labelled local stub (db integrity); real provider-health re-verification before leaving safe mode on the live system remains owner-gated"
}
```

