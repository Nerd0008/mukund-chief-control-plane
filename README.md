# Mukund Chief Control Plane

Private control plane for Mukund's AI-driven digital organisation: a governed multi-agent system where a Chief of Staff coordinates specialised AI workers, deterministic tools, resource telemetry, verification, audit trails, and human owner approval.

The project is being built so that independently operated agent systems can later collaborate through explicit interfaces without silently merging authority, state, credentials, or quality controls.

## What this project is

This repository is the **curated coordination and architecture layer** for Mukund's digital organisation.

The live system is centred around Hermes as the operational Chief of Staff, with ChatGPT and other AI systems contributing architecture, review, planning, specialist work, and future execution capacity.

The long-term goal is not a single chatbot. It is an AI management system capable of:

- understanding an owner's objective,
- breaking complex work into meaningful subtasks,
- assembling temporary teams of specialised AI workers,
- dynamically choosing workers based on task requirements and verified evidence,
- enforcing immutable quality and privacy constraints,
- monitoring provider/resource availability,
- integrating and independently verifying specialist outputs,
- recording why important management decisions were made,
- learning from real execution outcomes,
- escalating to the human owner when uncertainty or failure cannot be resolved safely.

<!-- BEGIN GENERATED: executive-status (scripts/status_render.py) -->
## Current Executive Brain roadmap

_Generated from the canonical status source (`status/canonical-status.json`, as of 2026-09-24T21:10:44Z). Regenerate with `python scripts/status_render.py`._

The Executive Brain is implemented in five layers. **Implementation completion,
Stage 2 enablement and production deployment are three different states.**

| Phase | State now | Implementation | Stage 2 | Production deployed |
|---|---|---|---|---|
| **E1** | ACTIVE | verified | n/a | no |
| **E2** | ACTIVE | verified | n/a | no |
| **E3** | IMPLEMENTED AND VERIFIED, STAGE 2 NOT ENABLED | verified | **NOT ENABLED** | no |
| **E4** | IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES) | verified | n/a | no |
| **E5** | IMPLEMENTED AND DRILL-VERIFIED (STUBBED PROVIDER FAILURES) | verified | n/a | no |

- **E1 — ACTIVE:** task classification, immutable quality floors, routing discipline, owner overrides, audit integrity.
- **E2 — ACTIVE:** Resource Governor telemetry, provider capacity/state tracking, deterministic Daily Resource Brief.
- **E3 — IMPLEMENTED AND VERIFIED, STAGE 2 NOT ENABLED:** multi-model orchestration, dynamic team assembly, evidence-backed worker qualification, execution DAGs, deterministic verification gates, decision-rationale audit trails. Stage 2 (production enablement) is gated on the seven absent provider credentials and an explicit owner step.
- **E4 — IMPLEMENTED AND DRILL-VERIFIED:** predictive exhaustion, protected reserves, resource-driven checkpointing, checkpoint/state handover and equivalent-worker failover. Drills use injected (stubbed) provider failures; real-provider failover is **not** claimed.
- **E5 — IMPLEMENTED AND DRILL-VERIFIED:** safe/degraded mode, failure drills, outage and malformed-output handling, bounded convergence enforcement, mature owner-override UX and a recovery path. The real provider-health probe before leaving safe mode is **not** wired.

**Production blockers remain open (10): the system is not production-deployed and no cutover is authorised.** See `status/executive-tracker.md` (section 10) for the explicit blocker list, and `state/current_company_state.md` for the live state.
<!-- END GENERATED: executive-status (scripts/status_render.py) -->

## Multi-model worker pool

The system is designed around a heterogeneous worker pool rather than a permanent mapping such as "model X always does coding."

Workers are treated as candidates whose capabilities must be verified for specific task families and roles.

The current E3 roster and model-selection authority lives in:

`handovers/2026-09-22-e3-model-roster-handover.md`

Important principle:

> Model capability metadata is routing evidence, not permanent routing policy.

The Executive Brain is intended to learn from verified outcomes and may assemble different workers for planning, research, architecture, coding, criticism, vision, integration, verification, and other roles within the same overall task.

## Operating model

- **Mukund is the owner and final authority.**
- **Hermes owns live operational state.** Hermes runs the organisation day to day, invokes workflows, tracks execution, verifies outcomes, and maintains the authoritative operational picture.
- **ChatGPT and other AI systems contribute through proposal/review surfaces** rather than silently changing production authority.
- **Deterministic gates remain authoritative** for quality floors, qualification rules, privacy/egress controls, state transitions, and audit integrity.
- **Local machines / VPS store raw and high-frequency data** such as databases, session state, caches, detailed logs, and provider credentials.
- **GitHub stores curated shared context** such as current state, approved architecture, decisions, handovers, audits, plans, and summaries.

## Agent review / collaboration entry point

This repository may be shared with trusted collaborators whose own agent systems need to understand Mukund's architecture before future interoperability work.

For an external agent reviewing this repository, use this order:

1. `README.md`
2. `state/current_company_state.md`
3. `approved-architecture/`
4. `decisions/`
5. `architecture-proposals/` and `proposals/` for pending work
6. `handovers/` for current continuation context
7. `resource-status/` and future orchestration-status summaries for operational snapshots

### Collaboration boundary

This repository currently represents **Mukund's side** of the system.

A collaborator's agent stack may have similar orchestration, memory, workers, or control-plane capabilities, but the two systems should not assume shared authority.

Future collaboration should use explicit, auditable interfaces for things such as:

- cross-agent task delegation,
- capability discovery,
- handover packages,
- verification requests,
- shared project context,
- status exchange,
- permission-scoped artifact access,
- provenance and decision records.

Until a federation/collaboration design is explicitly approved:

- external agents should treat this repository as review/context unless Mukund authorises changes,
- neither side should silently mutate the other's operational state,
- credentials and secrets remain local to their owning system,
- each side retains its own quality, privacy, qualification, and owner-approval controls,
- shared work should preserve provenance so both systems can determine who decided, executed, verified, or changed something.

This separation is intentional so future collaboration can be added without creating a single uncontrolled trust domain.

## Decision transparency

A core E3 requirement is owner-reviewable management reasoning.

For consequential AI decisions, the system is designed to retain concise structured rationale records showing:

- what was decided,
- meaningful alternatives considered,
- why alternatives were rejected,
- evidence used,
- important assumptions and uncertainties,
- confidence,
- trade-offs,
- planned verification,
- and the eventual outcome.

The design explicitly avoids storing raw private chain-of-thought or secrets. The goal is an auditable **decision journal**, not unrestricted model scratch-work.

## Directory map

| Directory | Contents |
|---|---|
| `status/` | **Canonical machine-readable project status** + the generated executive tracker |
| `state/` | Current company state snapshot |
| `docs/` | Setup and release/reproducibility documentation |
| `conversations/` | Curated conversation summaries |
| `runtime/` | Runtime status notes |
| `resource-status/` | Resource Governor / provider status |
| `execution-logs/` | Curated execution records |
| `decisions/` | Owner-approved decisions and rollouts |
| `approved-architecture/` | Current approved architecture |
| `proposals/` | Review copies of proposed changes |
| `reviews/` | Reviews |
| `architecture-proposals/` | Proposed architecture / implementation plans |
| `tasks-or-issues/` | Tasks and issues |
| `audits/` | Audit records |
| `handovers/` | Cross-chat / cross-agent continuation documents |
| `incidents/` | Incident records |
| `orchestration-status/` | Future curated E3 orchestration summaries |

## Recommended source-of-truth rules

When documents disagree, use the following priority:

1. `status/canonical-status.json` for every project-status figure (phase state, roster
   accounting, regression counts, credential readiness, Stage 2, deployment and blockers) —
   it is the machine-readable source from which the executive tracker
   (`status/executive-tracker.md`) and the status blocks in `README.md`,
   `state/current_company_state.md` and `state/full_build_tracker.md` are generated and
   verified (`python scripts/status_verify.py`),
2. latest owner-approved architecture / decision record,
3. `state/current_company_state.md`,
4. live implementation verification,
5. latest handover,
6. pending proposals / older planning documents.

Always check recent commits before assuming a handover is still current.

## Career discovery architecture (B25, 2026-09-24)

Job discovery was rebuilt so that the deterministic safety controls are kept while
the semantic breadth is restored. The previous behaviour used the owner's
`portals.yml` title filter (`positive = [Intern, Internship]`) as a *required*
discovery gate; as a precision filter that produced a false
"no eligible roles" result (a UK scan processed ~2861 postings and Company Watch
found 19 new ones, with 0 tracker-eligible).

```
broad collection (existing Career Ops scan lanes + Company Watch)
  -> light deterministic prefilter   career-ops/discovery/title_policy.py
  -> DeepSeek bulk semantic triage   career-ops/discovery/classifiers.py
  -> bounded Codex second pass       ambiguous / high-value candidates only
  -> deterministic eligibility       location, work authorisation, clearance,
                                     mandatory experience, application URL
  -> shared dedupe                   career-ops/tracker_writer.py primitives
  -> tracker manifest / Chief brief  manifest only; --apply stays explicit
```

Truth boundaries that hold in this repository:

- Discovery code lives in the control plane as an **overlay**
  (`career-ops/discovery/`). Nothing in it edits, patches or migrates the owner's
  external Career Ops install.
- Title matching is a **prefilter, never an eligibility decision**. The
  authoritative gates (region/location, work authorisation, clearance or
  citizenship, explicit mandatory experience, application-URL validity) run *after*
  semantic classification and **cannot be overridden by a model**.
- A model label is evidence about a posting, never a fact about the owner's
  eligibility. Nothing may be inferred about him from a discovery run.
- Where a source exposes no job-description text, the classification says so
  (`jd_available=false`, `classification_basis=title_company_location_only`) and
  is explicitly not JD analysis. No JD fact is ever invented.
- Funnel metrics make a zero explainable: a zero names the stage where the funnel
  went to zero and why, and a run limit or a disabled stage is recorded as a limit
  or as `not_applicable`, never as a market fact.
- Codex escalation is bounded by a per-run budget and its spend is evidenced;
  DeepSeek is the bulk classifier.
- No application, message, employer/recruiter contact, browser/GUI action or
  account mutation is performed by any discovery path.
- Canonical workbooks stay byte-identical through engineering acceptance
  (hash-verified before and after).

Details, commands and measured evidence: `career-ops/README.md`
(§ "High-recall semantic discovery pipeline") and
`audits/evidence/2026-09-24T04-58-25Z-career-high-recall-discovery/`.

## Reproducible setup and releases

The repository is set up to be reproducible from a clean clone or an exported
release archive.

- Dependency manifest: `requirements.txt` (direct, human-readable).
- Pinned lock for CPython 3.11.16: `requirements.lock` (hash-pinned transitive
  closure — install from this, never from an unpinned `pip install`).
- Clean-clone instructions, per-area test commands, and the machine-local
  provisioning checklist with deterministic probes: `docs/SETUP.md`.
- Release identity + archive build/verify tooling: `docs/RELEASE.md`,
  `scripts/release_manifest.py`, `scripts/make_release_archive.py`,
  `scripts/verify_release_archive.py`.
- Dependency honesty check: `python scripts/dependency_inventory.py --check`
  fails if any third-party import is missing from `requirements.txt`.
- Codex worker identity contract and its offline fixtures:
  `scripts/codex_identity_contract_check.py`.
- Canonical project status + generated executive tracker:
  `status/canonical-status.json` (source), `scripts/status_render.py` (generator),
  `scripts/status_verify.py` (verification), suite
  `scripts/tests/test_status_consistency.py`. The tracker and the derived status
  blocks in this README, `state/current_company_state.md` and
  `state/full_build_tracker.md` are regenerated, never hand-edited.

A release archive deliberately carries **no Git history** — it proves which
commit and dependency set it represents through the recorded commit SHA and
content hashes, never through fabricated history.

## Security

- This repository **must remain private** unless Mukund explicitly changes that policy.
- Never commit secrets, credentials, API tokens, cookies, keys, `.env` files, Hermes databases/session state, or caches/temp files.
- Provider credentials remain in local secret storage and are referenced by name, never by value.
- Raw and high-frequency operational data stays on local machines / VPS.
- Curated GitHub publications must be sanitised before commit.
- External collaborators should receive only the repository access necessary for the agreed collaboration role.

## Current collaboration direction

Mukund expects to collaborate later with a family member who operates a similar agent-based system.

The intended future work is to explore how both independently governed systems can cooperate while preserving:

- separate owner authority,
- explicit permissions,
- quality guarantees,
- decision provenance,
- security boundaries,
- and independent failure containment.

No cross-system federation is implemented yet. That should be designed and approved as its own architecture phase after Mukund's current control-plane work is sufficiently complete.
