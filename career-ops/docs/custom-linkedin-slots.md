# Custom LinkedIn publishing slots

Registry: runtime/linkedin/publish_slots.json, schema_version 1, weekdays maps English weekday names to unique Hermes scheduler job IDs. Existing installations without a registry retain the legacy three IDs. Invalid registries fail closed. Capturing a dated approved artifact supports every weekday. Scheduler registration is independent of text approval.

Provision another weekday:

    python scripts/register_linkedin_slot.py monday --apply

The registrar installs a thin wrapper and creates a paused no-agent dispatcher using the scheduler API. It is idempotent and never enables publishing. Friday 6 November is now supported; no draft from the handover was approved or scheduled. Actual publication still needs authenticated exact-body owner approval, complete reviews, integrity, exact-date/time manifest, publishing policy, image requirements and an armed job. A dormant weekly scheduler entry is dispatch infrastructure only and pauses when no exact eligible slot remains.

The canonical show/approve/capture/plan and scheduled CLI paths support all weekdays. The Sunday planner's default three-category cadence is unchanged. Custom dates supplement it. The publisher now respects the exact requested time instead of an 08:00 minimum, and computed arming matches the job's exact next_run_at.

Validation includes all-seven-weekday capture to simulated publication, 09:30 timing, duplicate prevention, exact artifact date binding, natural multi-post approval, registrar idempotence, invalid registries, earliest-slot selection, unapproved content, failed reviews and frozen-text changes. Live Friday wrapper dry run on 2026-11-06 returned NOT_SCHEDULED/no_approved_slot, zero network calls, as expected. Historical scheduler error fields were not rewritten to claim a successful execution.
