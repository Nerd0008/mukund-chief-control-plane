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

## Current Executive Brain roadmap

The Executive Brain is being implemented in staged phases.

- **E1 — ACTIVE:** task classification, immutable quality floors, routing discipline, owner overrides, audit integrity.
- **E2 — ACTIVE:** Resource Governor telemetry, provider capacity/state tracking, deterministic Daily Resource Brief.
- **E3 — PLANNED / next:** intelligent multi-model orchestration, dynamic team assembly, worker qualification, execution DAGs, integration/verification, and decision-rationale audit trails.
- **E4 — future:** predictive exhaustion, protected reserves, checkpointing, resource-driven handover.
- **E5 — future:** safe mode, resilience drills, and mature owner-override UX.

See `state/current_company_state.md` for the current live status rather than relying on this summary.

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
| `state/` | Current company state snapshot |
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

1. latest owner-approved architecture / decision record,
2. `state/current_company_state.md`,
3. live implementation verification,
4. latest handover,
5. pending proposals / older planning documents.

Always check recent commits before assuming a handover is still current.

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
