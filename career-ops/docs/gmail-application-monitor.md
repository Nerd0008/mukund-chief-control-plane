# Gmail application monitoring and Calendar deadlines

Status: offline implementation validated; live acceptance awaits laptop OAuth. Automatic writes and schedule installation are disabled. No initial live scan has occurred.

## Owner OAuth setup
Enable Gmail API and Google Calendar API in your Google Cloud project. Configure the consent screen for your account and create an OAuth **Desktop app** client. Do not save downloaded client JSON in this repository or send credentials in chat.

Run from the repository in your MISTY\mukun interactive session:

```powershell
$careerPython = "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe"
& $careerPython career-ops/career_google_auth.py store-client
& $careerPython career-ops/career_google_auth.py authorize
& $careerPython career-ops/career_google_auth.py status
& $careerPython career-ops/career_mail_monitor.py scan
```

The first command uses hidden prompts. Client values, refresh/access tokens and expiry metadata live only in Windows Credential Manager. Consent requests exactly Gmail `gmail.readonly` and Calendar `calendar.events.owned` (events on calendars owned by you, no calendar administration). OAuth uses PKCE and a transient loopback callback with state validation. A testing-mode Google OAuth project may require periodic consent renewal; status and failures never print tokens.

## Initial acceptance and write approval
`scan` defaults to dry-run. It reads the previous 30 days, reads existing canonical regional workbooks and saves a private reconciliation report under `%LOCALAPPDATA%/hermes/runtime/career-ops/gmail-monitor/last-dry-run.json`. Inspect likely applications, existing matches, proposed rows, assessments/interviews, exact/derived/ambiguous deadlines, proposed events and unresolved review items. No tracker/calendar write or persistent mailbox checkpoint occurs in dry-run. Do not commit or upload private mailbox reports.

Return that report to the owner for approval before enabling writes. Only after approval run `career_mail_monitor.py enable-writes --approve-report <exact-report-id>`. This enables subsequent `scan --apply`; it does not itself write anything. `schedule-plan` prints the current-user hourly task plan; it installs nothing. Change `scan_interval_minutes` to change cadence when the owner approves installation.

## Data and recovery
Canonical workbooks are resolved through `regional_profiles.json`. Existing company/role and owner status/notes are preserved; email-owned stage/status, assessment, source IDs, deadline evidence and event metadata are added as columns to those same workbooks. No competing tracker is created. Unresolved region/company/role or conflicting application matches require review. Matching uses thread evidence, then company/role and application reference. Owner-confirmed fields in saved record metadata are protected. Received date supplies the confirmation's application-date estimate; it does not replace existing owner dates.

Incremental reads use Gmail history IDs with complete pagination; expired history replays the 30-day window with message-ID dedupe. A safety cap fails without advancing the checkpoint. Workbook writes have verified backups, concurrency checks and literal strings to prevent formula injection. Calendar events use deterministic IDs, ownership markers and content fingerprints. Pending event writes survive partial workbook/calendar failures and retry safely on the next scan. Checkpoints advance only after successful receipts. Audit files contain source IDs and workbook hashes, never OAuth values.

Relative deadlines are explicitly DERIVED from the received timestamp. Date-only deadlines create all-day events; missing years, conflicting dates, business-day wording and ambiguous timezones require review. No guessed deadline generates an event. Assessment URL query strings/fragments are omitted to avoid persisting embedded access tokens; open the original Gmail message for a complete signed link. Calendar descriptions contain source message/thread IDs and extraction reasoning, not email bodies. Reminders default to 24 hours and 3 hours. Deadline extensions update the same event. No attendees are invited (`sendUpdates=none`).

Gmail exposes GET-only allowlisted endpoints. No sending, replying, deleting, archiving, labels or read-state changes exist. No applications, outreach, model calls or unrelated runtime changes occur. Google Calendar can be displayed on iPhone by adding the same Google account and enabling Calendars; no Apple automation is needed.

## Verification
134 offline tests passed across `tests/test_career_mail_monitor.py` and `tests/test_application_inbox.py` using Hermes Python. Includes requested classification/deadline/dedupe/calendar/extension/rejection/alert/safety cases and partial-failure recovery. Fixtures use fake transports and temporary workbooks, with zero live API calls. Live OAuth, mailbox classification quality and Calendar delivery remain unverified until owner consent and subsequent acceptance.

Primary references: [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app), [Gmail sync](https://developers.google.com/workspace/gmail/api/guides/sync), [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth), [event insert IDs](https://developers.google.com/workspace/calendar/api/v3/reference/events/insert).

## Laptop activation (6 October 2026)
Desktop OAuth client and tokens were securely installed under MISTY\mukun; both APIs are enabled and the two-scope consent succeeded. No credential values are recorded here. The Hermes `career-gmail-monitor` skill is installed in its operations skill directory and native skills_list verified discovery. Automatic writes/scheduling remain disabled pending initial reconciliation review.

Gmail request pacing is 0.5 seconds (at most 120 requests/minute). New projects have 6,000 units/user/minute and messages.get costs 20 units, so the previous 0.15-second rate was excessive: [current quota reference](https://developers.google.com/workspace/gmail/api/reference/quota). Initial quota errors did not advance checkpoints or mutate Gmail/workbooks/calendar.
