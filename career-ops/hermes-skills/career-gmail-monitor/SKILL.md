---
name: career-gmail-monitor
description: Read recruitment Gmail, reconcile Career Ops applications and assessment deadlines, and prepare Google Calendar deadline events. Use for application email monitoring or assessment/interview deadlines.
version: 1.0.0
metadata:
  hermes:
    tags: [career, gmail, applications, assessments, deadlines, calendar]
    category: operations
---

# Career Gmail monitoring

Owner-approved laptop integration. Use only the committed deterministic Career Ops monitor; do not use a general email tool or Google Workspace token files for this workflow.

Repository: `C:/Users/mukun/Documents/mukund-chief-control-plane`
Interpreter: `C:/Users/mukun/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`

Run from that repository:

```powershell
& 'C:/Users/mukun/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe' career-ops/career_mail_monitor.py status
& 'C:/Users/mukun/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe' career-ops/career_mail_monitor.py scan
```

Default is DRY RUN. Report counts and review the private local reconciliation report. Do not expose tokens, credential values, raw mailbox bodies or signed URL parameters in prompts/logs/evidence. Credentials are resolved internally from Windows Credential Manager under MISTY\mukun. Never dump Credential Manager or read token files.

Initial live report requires explicit owner review/approval before automatic tracker/calendar writes. Do not run enable-writes or install/enable scheduling merely because OAuth is configured. After explicit report approval, enable-writes requires its exact report ID; scan --apply is guarded. Use schedule-plan for the proposed hourly mechanism; it installs nothing.

Never send/reply/archive/delete/label messages or alter read state. Never submit applications or contact recruiters. Never invite event attendees. Canonical regional workbooks only; no competing tracker. Ambiguous deadlines/identities require review. Zero model calls are needed for scanning. A quota failure must be diagnosed before another attempt, not blindly retried.

Implementation/setup: `career-ops/docs/gmail-application-monitor.md`. Runtime private reports, checkpoints, receipts and backups: `%LOCALAPPDATA%/hermes/runtime/career-ops/gmail-monitor`.
