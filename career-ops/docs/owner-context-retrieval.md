# Owner context retrieval repair — 2026-10-12

Root causes: live owner-context SKILL.md had escaped YAML delimiters/headings, so Hermes native parser returned no name/description. The detailed references existed, but the observed aspirations response did not request them. Compact USER.md was mistaken for a complete profile. Native continuing sessions also reuse their stored system prompt, ignoring newly supplied system-message additions.

Owner explicitly approved sending relevant detailed profile information to the existing Nous/LongCat provider on 2026-10-12. No credentials, provider or billing settings change.

hermes_owner_context.required_references selects all five current local references for private owner-profile/ambition questions. Professional/application/public requests omit personal_context.md. Career, public voice, open questions and superseded-history references retain correction boundaries. Read required files at each relevant turn, with byte limits and SHA-256 provenance. Missing/invalid references fail before model invocation. Private content remains laptop-local; no profile bodies in Git or evidence.

The existing native agent wrapper now sets ephemeral_system_prompt for the duration of run_conversation, restoring it in finally. Hermes adds that field at API construction time, even when the stable system prompt is restored from an old session. No private payload is copied into the frozen system cache or user conversation rows by this code. This also fixes the English policy for restored sessions. Existing prior ephemeral context is preserved. No tools, provider transport, sessions or approval loop changes.

Local skill metadata repaired with a private before-copy at Documents/Codex/owner-context-recovery-20261012. Source references are not rewritten. Tests cover actual native build_api_messages, frozen sessions, missing files, live corrections, unrelated turns and private/public separation. No real provider calls used for validation.
