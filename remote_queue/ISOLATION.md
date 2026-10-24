# Remote queue isolation

The scheduled launcher reads `%LOCALAPPDATA%\hermes\remote-queue\poller.json`.
Missing or invalid configuration is a failure, never a fallback to the shared
working tree. The launcher remains hidden and returns the real poller exit code.

Use an **independent clone**, not a linked worktree: Git metadata, index and stash
must be separate. Configure these non-secret absolute paths/values:

- `repo_root`: dedicated queue clone
- `shared_repo_root`: protected interactive checkout
- `runtime_dir`: directory outside both checkouts
- `python_executable`: existing owner Hermes venv Python
- `branch`: queue feature branch, with matching `origin/<branch>` upstream
- `origin`: exact credential-free Git origin URL

No credentials belong in this file. Git uses the owner's existing credential
manager. Main/master are rejected by the scheduled bootstrap. Workers inherit
the clone root, queue root and hidden execution setting. This is checkout
isolation, not an OS sandbox restricting an authorized worker's arbitrary tools.

## Operation

`configured_poller.py --check-only` fetches and fast-forwards a clean clone,
reports pending count and never claims or dispatches. It works while halted.
Unpublished local commits block this check rather than being pushed by it.

Normal scheduled cycles use `configured_poller.py`. The existing two-minute
owner-account task can keep its hidden VBS action; it now calls this bootstrap.
The effective halt file is `<runtime_dir>/.poller.kill`; preserve an existing
halt until separately authorized activation. The old shared halt is untouched.
`last-check.json`, `last-run.json` and `logs/queue.log` live outside Git. Status
includes the effective clone and command; a halted exit 0 is explicitly HALTED,
not proof a worker executed. No raw task/provider output is copied to status.

Clean clones fetch then fast-forward. Dirty clones stop without stash, cleanup,
checkout or rebase. Publication commits only queue-state JSON paths and always
pushes `HEAD:refs/heads/<validated current branch>`, even if a prior attempt
already committed. Remote containment is verified. Non-fast-forward recovery is
bounded to one rebase/retry, exclusively in a clean independent clone; conflicts
are aborted there, preserving the local commit. Shared checkouts are never
rebased/stashed by these helpers. Other errors stop without history recovery.

A failed claim publication cannot dispatch. Its running record remains preserved
for explicit recovery/review; it is not automatically replayed. Existing stale
running records likewise are not restarted automatically. Inspect local history
and remote state before any owner-approved recovery. A dirty clone requires
review/checkpointing, not automatic stash/clean. The process mutex prevents
simultaneous cycles. No real task is used by regression/acceptance tests.

## Validation

Run `python -m pytest remote_queue/tests -q`. Tests use disposable repositories
and local bare origins, including feature-branch publication, retry of an
unpublished commit, rejected shared/dirty synchronization, claim failure,
check-only no-dispatch, configuration rejection and dispatcher path propagation.
The live kill switch is preserved as found, rather than deleted to pass tests.
