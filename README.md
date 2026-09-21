# Mukund Chief Control Plane

Private shared control plane for Mukund's digital organisation.

## Purpose

This repository is the shared, curated context layer between the systems that
manage Mukund's digital organisation — primarily Hermes (Chief of Staff) and
ChatGPT (contributing system).

## Operating model

- **Hermes owns live operational state.** Hermes runs the company day to day:
  it invokes workflows, tracks execution, verifies outcomes, and maintains the
  authoritative picture of what is happening.
- **ChatGPT contributes through the proposal/review areas**, not live
  operations. Its input lands in `proposals/`, `architecture-proposals/`,
  `reviews/`, and feeds `decisions/` and `approved-architecture/` once the
  owner approves.
- **Local machines / VPS store raw and high-frequency data** — databases,
  session state, caches, full logs, raw conversation history. That material is
  never pushed here.
- **GitHub stores only curated shared context** — current state, decisions,
  approved architecture, handovers, audits, and summaries.

## Directory map

| Directory | Contents |
|---|---|
| `state/` | Current company state snapshot |
| `conversations/` | Curated conversation summaries |
| `runtime/` | Runtime status notes |
| `resource-status/` | Status of tracked resources |
| `execution-logs/` | Curated execution records |
| `decisions/` | Owner decisions |
| `approved-architecture/` | Approved architecture documents |
| `proposals/` | Proposals |
| `reviews/` | Reviews |
| `architecture-proposals/` | Architecture proposals |
| `tasks-or-issues/` | Tasks and issues |
| `audits/` | Audits |
| `handovers/` | Handover documents |
| `incidents/` | Incident records |

## Security

- This repository **must remain private**. Do not make it public.
- Never commit secrets, credentials, tokens, cookies, keys, `.env` files,
  Hermes databases/session state, or caches/temp files.
- Raw and high-frequency operational data stays on local machines / VPS.
