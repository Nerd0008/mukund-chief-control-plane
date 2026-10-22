# Handoff to Codex — concurrent edits in `career-ops/` (2026-10-22)

**From:** Hermes (Chief of Staff). **Why this file exists:** you and I are editing the same
repository at the same time, and we have edits in the same files. This note says exactly which
lines are mine, so you preserve or discard them deliberately rather than by accident.

---

## What I changed, and why

Owner instruction, 2026-10-22: **"still add if not verified open."**

Context that caused it: a real run classified 219 candidates, accepted 72, and wrote **0** rows to
the tracker. The availability gate rejected 71 of the 72 because the browserless HTTP verifier
cannot prove OPEN on JavaScript-rendered ATS pages (Workday, SmartRecruiters, LinkedIn). The
pipeline reported success while the tracker stayed empty.

New rule: **only POSITIVE evidence of closure blocks a role.** Absence of verification adds it,
flagged as unverified.

### 1. `career-ops/discovery/pipeline.py` — `deterministic_gates()`

- **~line 884** — `resolved_verified` now reads `(rec.get('vacancy_status') or {})`. The previous
  `.get('vacancy_status', {})` raised `AttributeError` when the key was present but explicitly
  `None` (the default only covers an absent key).
- **lines 892–909** — the `fetch_state` gate:
  - `validation_failed` → **rejected** with `source URL failed validation (fetch_state=…) — an
    unusable destination is never written`. A failed validation is a negative result (dead link,
    expired marker, non-2xx, robots refusal), not an absence of evidence.
  - `bot_wall` → **flagged** `HTTP page blocked (403/429); availability UNVERIFIED — added as an
    unverified lead, verify before applying`. 403/429 is not evidence of closure.
  - any other non-`validated_live` state → **flagged** `source URL not validated live
    (fetch_state=…); availability UNVERIFIED — added as an unverified lead, verify before applying`.
  - All three were previously hard `reasons` (rejects). Only `validation_failed` still is.
- **lines ~950–957** — the availability gate. This is the line that emptied the tracker:
  - only `vacancy_status.state == 'CLOSED'` rejects: `current vacancy availability is CLOSED
    (proven closed)`.
  - `state != 'OPEN'` (UNKNOWN, or absent) → **flagged** `availability UNVERIFIED (no confirmed
    OPEN check) — added as an unverified lead, verify before applying`.
  - Previously `state not in (None, 'OPEN')` was a hard reject.
- **lines 1270–1277** — new funnel counter `accepted_availability_unverified` plus a
  `funnel.note(...)`, so a run that added 40 unverified roles cannot look identical to a run that
  verified 40. The owner needs to know which rows still need checking.

### 2. Tests I changed — the old assertions encode a policy the owner has now overridden

- **NEW** `career-ops/tests/test_unverified_leads.py` — 9 tests pinning both halves of the rule
  (unverified accepted and flagged; dead link, proven-CLOSED, JD-stated-closed and clearance still
  rejected).
- `career-ops/tests/test_application_links.py` —
  `test_discovery_stale_transport_requires_positive_resolved_identity` became
  `test_discovery_stale_transport_is_accepted_as_an_unverified_lead`.
- `career-ops/tests/test_web_research.py` —
  `test_unverified_and_failed_destinations_never_reach_the_tracker` became
  `test_unverified_results_become_unverified_leads_while_dead_links_are_refused`;
  `test_a_run_over_only_unverified_results_collapses_to_an_attributable_zero` became
  `test_a_run_over_only_dead_links_collapses_to_an_attributable_zero`.

Verified: **195 passed** across `test_unverified_leads.py`, `test_web_research.py`,
`test_application_links.py`, `test_discovery_pipeline.py`, `test_job_availability.py`.

---

## Where our edits collide

- **`career-ops/discovery/pipeline.py`** — your `verified_api` block sits at **lines 887–891**;
  mine starts at **892**. Adjacent, inside the same function. Your `gate_rec` identity
  substitution at **1243–1245** also feeds records into the same `deterministic_gates()` call that
  my gates sit inside.
- **`career-ops/tests/test_application_links.py`** — we have both edited this file.

**They compose logically.** Your `verified_api` path keeps ATS-API-verified postings accepted via
`resolved_verified`; my change relaxes exactly what the verifier *cannot* check. There is no
semantic conflict between them.

**But if you rewrite `deterministic_gates()` or the eligibility loop wholesale, my four hunks above
are lost — none of my changes are committed anywhere.**

---

## A defect in the current working tree (yours, not mine)

`career-ops/tests/conftest.py` adds an autouse fixture:

```python
import gmail_discovery
monkeypatch.setitem(gmail_discovery.collect.__kwdefaults__, "root", tmp_path / "newsletter-fixtures")
```

`gmail_discovery.py` lives at `career-ops/discovery/gmail_discovery.py`, and `career-ops/discovery`
is not on `sys.path` in the test session, so the import fails during fixture setup. That errors
**26 tests** (tracker_rollover, linkedin_workflow, workbook_recovery) — they never run at all.

Fix: add `sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'discovery'))`
before the import, or import it as `from discovery import gmail_discovery`.

---

## My state

Nothing committed, nothing pushed, nothing reverted or stashed. The owner told me to stop and said
you are fixing this, so the repo is yours.
