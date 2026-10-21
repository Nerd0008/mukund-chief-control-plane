# Gmail monitoring repair — 21 October 2026

## Applied changes

- OAuth health distinguishes credential presence, refresh-token presence, expiry, verified refresh and failure reason. Presence alone is never ready.
- `career_google_auth.py status --verify` and `career_mail_monitor.py status` perform one bounded live refresh and return nonzero on failure. Normal token use caches successful refreshes and renews expired access tokens. Known invalid grants stop repeated scheduled refresh attempts until new authorization or an explicit health probe.
- Google OAuth string errors such as `invalid_grant` are parsed safely alongside API error objects. Error bodies and credentials are never printed.
- New authorization is checked by a live refresh before its CLI reports success. Existing Windows Credential Manager storage and the two scopes are preserved.
- Scheduled scans persist sanitized success/failure health, including the last success time and whether owner action is required. Failed scans do not advance the checkpoint.
- An operating-system-held scan lock releases on process exit or termination. A leftover file no longer permanently blocks future scans. Deploy with prior-version scans stopped; old and new lock protocols must not run concurrently.

## Verified state and remaining activation gates

The live refresh returned HTTP 400 `invalid_grant`. `ChiefCareerGmailMonitor` and `HermesRemoteQueuePoller` were already disabled and remain disabled during repair. The saved history cursor is 1034830; its last completed scan was 12 October 2026. No checkpoint reset, catch-up apply, Gmail mutation or Calendar write was performed.

Google Cloud's Audience page for the existing client project shows Testing. Google documents seven-day refresh-token expiry in that mode for these scopes. This is a verified configuration problem and a plausible explanation of the outage, not proof of the specific token's revocation cause. Publish app is disabled pending branding configuration. Moving to production requires the owner's approval of its changed audience/access duration and appropriate truthful app configuration.

After owner browser authorization: verify refresh and Gmail/Calendar reads; run the normal bounded dry-run from the existing checkpoint; inspect proposals and fingerprints; perform a bounded guarded apply under existing approved monitor authority; reconcile receipts and checkpoint; then enable the existing hourly task and verify one scheduled execution returns 0. Preserve the hidden VBS wrapper and owner principal. Its 20-minute execution limit should be assessed against the bounded backlog before activation.

## Validation

92 tests passed covering auth, scan recovery, mail monitoring and scheduled activation. The broader initial run passed 284 tests and failed four pre-existing tracker-layout assertions. All four failures were reproduced with the original auth and monitor modules from the private backup: two expect new-row insertion now refused by the sidecar writer, one expects historical snapshot recovery despite sidecar precedence, and one expects an outdated error message. No matching or write guard was weakened.

Private backup: `%LOCALAPPDATA%/hermes/runtime/career-ops/gmail-monitor/repair-20261021-192705`. Private mailbox evidence and credentials remain outside Git.

Google reference: https://developers.google.com/identity/protocols/oauth2/#expiration
