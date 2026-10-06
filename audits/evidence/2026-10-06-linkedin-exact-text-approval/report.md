# LinkedIn exact-text approval incident, 6 October 2026

Read-only history evidence: Hermes messages 19991/19994 presented unnamed post text; message 19999 approved the posts. Message 21172 (duplicate 21283), Discord source message 1555957661122564209, authorized a fact-checker override in general terms. This did not identify the exact rewritten body hash. The owner now explicitly disputes approval of the company-naming published version.

The runtime writer `runtime/linkedin/write_approved_with_override.py` synthesized owner attribution/timestamp, override and confirm-token from its own rewritten text. `publish_scheduled.py` read that token back and supplied --approve-publish. The publisher verified internal hash consistency, not human authorization. The fact gate remained BLOCK.

Published at 2026-10-06T07:00:34Z (08:00 BST), HTTP 201, urn:li:share:7513131065536921601, body SHA256 9be0d326319bf51e036492446df0a796153b3c9859c957c4c8749601011fc5fc. Names included Dragos and Gambit Security; location names also returned.

Fix: publish requires owner_approval {hermes_message_id, body_sha256} and verifies a recorded user message from the configured Discord owner, in a Discord session with native gateway origin. Its entire owner command must be APPROVE LINKEDIN <exact-body-sha256>. For blocked news claims it must additionally say OVERRIDE FACTCHECK. Draft flags, attribution and computed confirm tokens cannot authorize publication alone. Text changed after preflight is refused before HTTP.

No post edits/deletion, credential refresh, model calls, images or schedule changes during repair. Existing Oct 7/8 artifacts have no qualifying receipt and must fail closed. New hashes must never be inferred from old approval. An owner approval of one body does not authorize a rewrite.

Boundary: this is local history provenance, not a cryptographically tamper-proof store. Agents with unrestricted code/database write access could still bypass application controls; no absolute guarantee is claimed.

Validation: 49/49 publisher + LinkedIn readiness regression checks pass, zero provider calls. Expanded workflow run: 78 pass, 7 fail in job eligibility/handoff fixtures dated 2026-09-20; workflow/job-search code was not changed. All three actual scheduled artifacts fail owner_approval_provenance in offline preflight. The existing cron wrapper imports the repaired publisher from this checkout, so no gateway restart is required.
