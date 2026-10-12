# Read-only assessment status

Hermes uses `career_gmail_assessments` for questions about valid, expired or completed assessments. It queries the last 30 days independently of the automatic monitor checkpoint, matches against the current canonical tracker, and returns evidence-backed OPEN, EXPIRED, COMPLETED or UNKNOWN. It does not change classification/deadline write rules, remove locks, or write tracker/Calendar/checkpoint state.

A reliable future deadline supports OPEN (deadline window only; portal availability is explicitly unconfirmed). Past deadlines or explicit closure support EXPIRED. Explicit submission/completion confirms COMPLETED. A link or invitation alone is UNKNOWN. Date-only deadlines today remain UNKNOWN because the cutoff is unestablished. Newsletters are excluded. Thread/reference boundaries prevent employer-only merging; later notifications supersede earlier invitations within the same assessment thread.

No assessment portal is clicked, authenticated, started or submitted by this tool. UNKNOWN must be reported honestly; checking authenticated portal state requires a separately safe read-only route. Private signed URLs and email bodies are never returned. The native response should contain only assessment statuses, not unrelated application/CV maintenance.

Command: Hermes Python `career-ops/career_assessment_status.py scan`. At most 200 queried messages; API/cap failures fail closed rather than reporting incomplete conclusions. No provider/model calls.
