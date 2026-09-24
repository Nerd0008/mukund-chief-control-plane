# Canonical project status

This directory holds the **single canonical machine-readable project-status
source** and the executive tracker generated from it.

```
status/canonical-status.json     canonical status source   (authored, evidence-referenced)
status/executive-tracker.md      executive tracker         (GENERATED — do not hand-edit)
status/README.md                 this document
```

## Why

Project status used to be maintained by hand in several places (README roadmap,
`state/current_company_state.md` header, `state/full_build_tracker.md`, and the
rendered PDF). Those surfaces drifted: the README still said E3 was *planned* and
E4/E5 *future* after both were implemented and evidenced, and the company-state
header was older than the newest incorporated work.

Now there is one source. Every drift-prone surface is rendered from it, and a
verification command fails when a generated surface is stale or when a figure in
the source disagrees with the recorded evidence artifact it cites.

## Commands

```bash
# regenerate the executive tracker + the derived status summaries
python scripts/status_render.py

# verify (exit 1 on any failure) — also run as a regression suite
python scripts/status_verify.py
python scripts/status_verify.py --strict          # treat warnings as failures
python scripts/tests/test_status_consistency.py   # the registered suite
```

`scripts/status_render.py --check` is an alias for the verification command.
The suite is registered in `scripts/evidence_runner.py`, so it runs with the rest
of the repository acceptance suite. Add `--only status` to the runner to run just
this one.

## Generated surfaces

| Surface | How it is maintained |
|---|---|
| `status/executive-tracker.md` | fully generated file |
| `README.md` → `## Current Executive Brain roadmap` | generated block between `BEGIN/END GENERATED: executive-status` markers |
| `state/current_company_state.md` → top block | generated block; the historical evidence chronology below it is untouched |
| `state/full_build_tracker.md` → top block | generated block; the narrative lanes below it are untouched |

Once the markers exist, the renderer replaces the block in place. **Do not edit a
generated block by hand** — change `status/canonical-status.json` and regenerate.

## What the source contains

`current code/release identity`, `E1–E5 state`, `roster accounting`, `latest
evidence timestamps`, `regression counts`, `Career discovery state`, `queue/service
state`, `provider credential readiness`, `Stage 2 state`, `deployment state`,
`production blockers`, optional/feature-gated owner decisions, unresolved
unknowns, and an evidence chronology.

The source is populated **only** from verifiable repository/runtime evidence, and
each figure carries the `source.path` of the artifact it came from.

## Verification guarantees

`status_verify.py` fails when any of these is true:

1. a required section is missing from the canonical source;
2. a referenced evidence path does not exist;
3. a figure in the source disagrees with the evidence artifact it names
   (regression counts, roster counts, credential presence, deployment preflight,
   E4/E5 drill results, boot-persistence evidence);
4. a required production blocker is missing, or an optional/feature-gated item
   has been wrongly promoted to a production blocker;
5. the generated executive tracker, or a generated summary block, is stale
   relative to the canonical source;
6. the generated output contains possible secret material;
7. the status claims readiness while production blockers remain open.

It warns (and fails under `--strict`) when an evidence directory newer than the
source `as_of` has not been incorporated, so static drift is visible rather than
silently accepted.

## Truth rules

- **UNKNOWN stays UNKNOWN.** No owner-gated unknown is rendered as PASS.
- **Implementation completion, Stage 2 enablement and production deployment are
  three separate states** and are never collapsed into one.
- **Production blockers are listed separately** from implementation completion,
  and separately again from optional/feature-gated owner decisions (Gmail
  read-only OAuth, research provider, live LinkedIn account access, live
  recruiter feed and the regional work-authorisation facts are optional /
  feature-gated, not release blockers).
- **No secrets.** Only presence booleans and store names already published by the
  presence-only probe are stored; the generator makes no network call, reads no
  credential value and touches no private runtime database.
- **Historical evidence is never overwritten** — the renderer only replaces its
  own marked blocks and the generated tracker file.
