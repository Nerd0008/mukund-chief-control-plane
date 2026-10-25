# LinkedIn workflow-state repair

Owner-requested repair on fix/e3-whole-repo-architecture. No main merge or publishing activation.

## Failure and repair

Owner approval existed in chat, but the armer discarded it when an independent news review failed. Text/hash equality was mislabeled approval, schedulers disagreed, weekday wrappers discarded dry-run/nonzero exits, and a keyword fallback accepted negated or non-owner messages. Old instructions told the agent to rebuild weekly publisher code.

`linkedin_state.py` now computes one authoritative view from the canonical artifact, verified consent, both specialist reviews, frozen text, exact-date manifest and actual job enablement. Approval, readiness and scheduling are separate facts:

- AWAITING_OWNER_APPROVAL: no verified exact-post consent.
- APPROVED_BUT_BLOCKED: consent retained; review/integrity incomplete.
- APPROVED_READY_PAUSED: verified content; publish job disabled or unavailable.
- APPROVED_READY_UNSCHEDULED: verified content; no exact matching manifest.
- SCHEDULED: exact artifact/body/image/date pinned and corresponding job enabled.
- CANCELLED/PUBLISHED: cancellation and published-ledger facts take precedence.
- NO_ARTIFACT: chat drafts/approvals are unknown, not falsely rejected.

`linkedin_approval.py` checks recorded owner/platform identity and exact presented content. Strict hash commands or short affirmative replies to the latest exact post are accepted. Negation, questions, tool completions, unrelated historical yes, different posts and ambiguous newer presentations fail closed. Overrides need distinct explicit owner consent. The owner need not type a hash to approve an unambiguous exact presentation.

## Normal data-only commands

Use the existing Hermes interpreter:

```
python career-ops/linkedin_state.py capture --text-file <exact-body.txt> --date YYYY-MM-DD --approve-message-id <real-Hermes-ID> --source-url <URL>
python career-ops/linkedin_state.py reconcile --drafts <artifact.json>
python career-ops/linkedin_state.py status --drafts <artifact.json>
python career-ops/linkedin_state.py plan --drafts <artifact.json> --date YYYY-MM-DD
python career-ops/linkedin_state.py week
python career-ops/linkedin_state.py check-jobs
python runtime/linkedin/publish_scheduled.py tuesday --date YYYY-MM-DD --dry-run
```

Capture validates consent before writing. Explicitly approved replacements preserve prior versions and invalidate old review receipts. Reconcile persists genuine consent independently of later review failure; it reuses valid exact-body reviews and recovers a complete historical pass only against unchanged source hashes. A later complete block cannot be replaced with an older pass. Personal review uses the existing deterministic local Node verifier. Model news judging requires explicit --refresh-news; no repeated repair loop is introduced.

Mutations share an OS-backed lock, fingerprint checks, fsynced atomic replacement and durable intent/commit audit records. Cancellation preserves historical consent but blocks publication and removes only references to that exact artifact. Planning pins body/image hashes and timezone-aware 08:00 Europe/London time, without enabling a job.

## Scheduled execution

`linkedin_scheduled.py` is the sole scheduled executor; installed wrappers are thin delegates under the current interpreter. All flags and child exit codes propagate. Preview makes no provider/subprocess/account or approval/schedule/published-ledger writes. Execution requires today's due date, enabled job, pinned unchanged content, genuine consent/reviews and no duplicate. The lower-level publisher also refuses early/wrong-week execution of dated artifacts. A successful scheduled result needs a returned post URN and a published ledger record.

Old ad-hoc approved-draft/override writers are retired with recovery backups. Readiness checks no longer regex-parse obsolete script code. Weekly instructions and its existing drafting prompt query canonical state before reporting. Scripts are installed once; weekly posts change bounded data only.

## Verified recovery

The unchanged Tuesday PHP post was reconciled from its real owner message, its valid audited news pass and a fresh real local personal review. Body and image did not change. Its manifest pins 27 October 2026 at 08:00 Europe/London (UTC+00:00). All three publish jobs remain disabled: APPROVED_READY_PAUSED. Installed and repository previews agree; wrong-date previews return nonzero; preview leaves protected hashes unchanged.

Final Career Ops regression: **1669 passed, zero failed** (203.70 s). Installed-path previews passed with zero state/ledger changes and correct nonzero wrong-date failure. Regression cases cover exact/natural consent, altered bodies, negation/questions, unknown artifacts, failed reviews, receipt recovery, later factual block, audit failure, concurrency, cancellation, exact dates/DST, dry-run, child failure and ledger-backed deduplication.

No post, message, connection, OAuth/provider change, CV change, Gmail mutation or Calendar change was made. No model/provider call was needed. Only the existing weekly drafting prompt was updated, with its draft-only permissions preserved. Unrelated concurrent Hermes edits are excluded from this commit.

## Installation

`scripts/install_linkedin_state.py` previews by default. --apply backs up and installs only known thin wrappers, canonical workflow guidance and retired helper delegates; it refuses installation while a publish job is enabled. --update-weekly-prompt changes only that existing job's prompt through the scheduler API. No gateway restart is required.

A later, separately authorized enablement must use the manifest's timezone-aware publish_at rather than a stale disabled-job next_run_at, especially across the London clock change.
