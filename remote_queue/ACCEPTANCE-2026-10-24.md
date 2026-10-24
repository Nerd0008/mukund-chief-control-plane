# Queue isolation acceptance — 24 October 2026

Implementation: `1c0216cebdb5acdd5c8629527a633e73a37ccf14`, branch
`fix/e3-whole-repo-architecture`. No main merge.

## Repair and proof

- Preserved 110 files in a private hash-verified recovery snapshot before edits.
- Removed all automatic stash/pull/rebase behavior from shared-checkout polling.
- Scheduled VBS calls a fail-closed configured bootstrap. It resolves an
  independent clone under the existing owner's local Hermes installation.
- Poller, queue storage and worker cwd resolve to that clone. Separate Git
  metadata/index/stash; not a linked worktree. Private config/logs/status/control
  files are outside both checkouts.
- Publication targets validated current/upstream feature branch, verifies remote
  containment, retries already-committed unpublished state, and excludes logs and
  unrelated staged files. Bounded non-fast-forward recovery requires a clean
  independent clone. Failed claim publication prevents worker dispatch.
- Full queue regression: **106 passed; 18 subtests passed; 0 failures**, 69.03s.
- Live configured `--check-only`: exit 0, pending 0, dispatches 0, halted true;
  authenticated Git fetch/branch comparison succeeded against the actual origin.
- Actual `HermesRemoteQueuePoller` task: enabled, every two minutes, existing owner
  account, hidden VBS, LastTaskResult 0, structured status **halted**, dispatches 0.
- 104 pre-existing working files hash-checked unchanged; 65 original queue
  records unchanged; shared Git index and stash ref unchanged during acceptance.
  No real job dispatched or manufactured. Old stale running record untouched.
- Original shared kill switch and new isolated-runtime kill switch both retained.

## Activation explicitly pending

Automatic approval review rejected removal of the isolated halt and live restart:
resuming unattended dispatch requires separate explicit owner approval. The
rejection occurred before command execution. No activation occurred. Exit 0 is
reported as HALTED, not as successful execution of a worker.

Owner action: explicitly approve resuming unattended dispatch from the repaired
isolated poller. After approval, remove only the isolated-runtime halt and perform
one normal scheduled-path acceptance. Do not remove the old shared halt or replay
the stale running record. The task's existing cadence/registration was preserved.

Private recovery, original task XML, test output, effective paths, current config
and detailed hash inventories remain outside Git in the owner's Codex recovery
folder. Only source/tests/docs and this sanitized aggregate report are committed.
