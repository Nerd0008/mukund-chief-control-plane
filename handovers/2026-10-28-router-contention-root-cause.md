# Recurring router timeouts: reproduced root cause and repair

28 October 2026. Branch: fix/e3-whole-repo-architecture. No main merge.

## Root cause

Independent LinkedIn fact-check, native conversation and job-search processes
could dispatch the same Codex routing model simultaneously. There was no shared
cross-process admission control. The latest 14:55 failed receipts contained
rate-limit protocol evidence, but TIMEOUT classification took precedence.

A live three-caller synthetic reproduction captured the underlying CLI stderr:
`last status: 429 Too Many Requests` followed by an internal sampling-request
retry wait of about 197 seconds. One caller completed; two waited for that
backoff until Hermes killed them at its 45-second deadline. The same mechanism
can outlast the later 90-second deadline. The generic timeout hid the rate limit.
The CLI's internal network retry wait is distinct from replaying workflow actions.

The prior isolated smoke tests and longer deadline did not test or resolve this
contention. They were insufficient acceptance evidence. This repair was made
only after the failure was reproduced with captured transport evidence.

## Controlled comparisons

| Scenario | Outcome |
| --- | --- |
| Isolated selector, same executable/model/high effort | Passed in about 8–10 seconds |
| Same test with gateway certificate override | Passed in 9.2 seconds |
| Same test without desktop tool-call metadata | Passed in 7.7 seconds |
| Three simultaneous callers, before admission guard | 1 success, 2 HTTP429-backed timeouts |
| Three sequential callers after honoring provider backoff | 3 successes in about 11, 11 and 8 seconds |
| Three simultaneous callers through repaired admission | 3 successes; elapsed about 11, 21 and 29 seconds, including queue time |

These comparisons identify the reproduced software defect. They do not claim
OpenAI publishes a permanent one-request concurrency limit or that every older
unrecorded timeout had this cause. The guard conservatively serializes calls
per model based on the observed behavior and still respects external limits.

## Repair

- A shared per-model OS file lock coordinates Codex calls across processes,
  including routing, bounded workers and web research. Process exit/crash
  releases the lock. Waiting consumes the original deadline and is cancellable.
- Observed HTTP429 backoff is recorded as a small local shared cooldown. Calls
  during cooldown make no provider request. Invalid cooldown state fails closed.
- Cancel-aware production calls observe stderr and terminate the owned child
  tree when the CLI announces a rate-limit retry sleep, rather than sleeping
  until an unrelated timeout. Only typed status and retry timing are surfaced.
- Router errors now distinguish HTTP429, a busy admission slot, an actual CLI
  timeout, and genuine usage exhaustion. No opaque IDs/timestamps can be treated
  as HTTP429 merely because their digits contain 429.
- LinkedIn source verification stops after a typed routing/resource failure.
  It does not perform two more correction attempts or misclassify the problem
  as bad post content. Incomplete verification still cannot authorize publishing.
- Existing gpt-6.1-sol/high reasoning, provider-neutral worker selection,
  qualification, owner-context, deadline, consent and submission guards remain.
  No authentication or provider configuration was changed, no credits bought or
  reset redeemed, and no automatic workflow-action replay was introduced.

## Verification

456 relevant regressions passed. Cases include real child-process cleanup,
three-process exclusion, crash release, queue cancellation/deadline, shared
cooldown, expiry, malformed state, exact rate-limit classification, and stopping
the LinkedIn correction loop, plus existing router/controller/search/draft tests.

The deployed live LinkedIn test used synthetic references and drafts only. It
called the real router and native worker, made four provider calls and two
bounded native tool calls, and recovered the exact draft plus its approval
marker through show/build continuations. Selected worker: Step 3.7 Flash through
the existing approved Nous transport. No real owner profile or operational
snapshot was sent, no terminal action executed, and no post was published.

At the same time, the real UK production entrypoint completed 6/6 queries with
exit 0, advanced the cursor 8 -> 9 and added zero rows. Workbook hash was
identical before/after; 173 data rows, integrity verified. Its confirmation
receipt is 20261028T152903Z-19895437.json.

The ordinary scheduled 17:45 scan subsequently completed 12/12 queries with
exit 0 and complete coverage, adding zero rows. Receipt:
20261028T174500Z-94cc8a79.json. The earlier 15:38 run stopped on an explicit
router_cli_usage_limit refusal. That genuine account-limit outcome was not
reported as a timeout and no reset was redeemed. The repair respects limits;
it does not manufacture quota or silently choose a different routing brain.

Gateway PID 15128 is running through the guarded entrypoint, Discord connected.
Six deployed module hashes match source. Normal UK scanning and daily digests
remain enabled; next scan observed 19:45 London. The overnight Codex campaign
and duplicate Windows scans were not enabled. No running scan was interrupted.

The actual Wednesday draft JSON differs from the preceding repair's old
baseline because Hermes updated verification at 14:53:35, before this recurring
failure investigation began. That pre-existing state was preserved. The frozen
text, schedule and publication ledger still match that older baseline. This
report does not relabel those prior owner-workflow effects as actions performed
by the repair or replay any publication.

## Evidence and preservation

Private recovery/evidence:
C:/Users/mukun/Documents/Codex/native-router-contention-20261028/

Key files: concurrency-results.json, serial-results.json,
live-admitted-results.json, regressions-final.xml, deployment.json,
live-synthetic-workflow.json, live-acceptance.json and final-evidence.json.
Source snapshots and the initial diff/status are retained under before/.

Only legitimate source, tests and this handover belong in the repair commit.
Runtime locks/cooldowns, credentials, databases, logs, profiles, workbook backups
and private evidence remain outside the commit. Seven pre-existing Career Ops
source/test diffs are preserved and excluded. No reset, clean, stash, rebase,
blanket add or main merge was used.

Official CLI retry configuration reference consulted:
https://learn.chatgpt.com/docs/config-file/config-reference
