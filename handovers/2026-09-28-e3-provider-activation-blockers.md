# Final activation blocker — make the E3 Hermes provider real

Date: 2026-09-28
Branch: `fix/e3-whole-repo-architecture`
Starting code commit: `9c1cdff32183937f85730335ba34d5b592a75d11`

The E3 model-provider files were copied locally, but Hermes has NOT been restarted. Do not restart it until this task is green.

## Observed local install

Current copied path:
`C:\Users\mukun\AppData\Local\hermes\hermes-agent\plugins\model-providers\e3`

Both `__init__.py` and `plugin.yaml` are present.

No runtime restart/provider call was performed.

## Blocker 1 — installer uses vendor/bundled tree instead of user provider tree

Current:
`scripts/install_e3_model_provider.py`

hardcodes:

`...\hermes\hermes-agent\plugins\model-providers\e3`

Current Hermes provider-plugin contract supports third-party/user providers at:

`$HERMES_HOME/plugins/model-providers/<name>/`

Use Hermes' authoritative profile/home resolution where possible. Do not edit the installed Hermes repo/bundled plugin tree for our provider.

Requirements:
- installer resolves active/default Hermes profile home correctly;
- supports explicit `--hermes-home` override;
- installs to `<HERMES_HOME>/plugins/model-providers/e3`;
- reversible backup/restore;
- remove/retire the stale vendor-tree copy created by the previous installer only after verifying it is our exact E3 plugin, never delete unrelated vendor files;
- tests prove no vendor-tree mutation.

## Blocker 2 — plugin resolves E3 runtime path incorrectly

Current plugin:

`Path(__file__).resolve().parents[2] / "exec-brain"`

This does not resolve to the actual runtime root for either the current vendor-tree copy or a normal user-provider install.

Actual local E3 runtime root is:
`%LOCALAPPDATA%\hermes\exec-brain`

Requirements:
- use explicit `HERMES_E3_RUNTIME_ROOT` override if set;
- otherwise use the deployed/runtime contract already used by the control plane;
- validate required modules before registering/creating a client;
- fail with a stable non-secret error if runtime is absent;
- zero secret values in diagnostics.

## Blocker 3 — real Hermes tool-call protocol is NOT preserved

Current test `test_hermes_agent_loop.py` uses a fake service that returns:
`{"tool_calls": ...}`

But real `E3ApplicationService.execute()` returns only:
- verified text content
- worker/provider/model metadata
- assignments

It:
- collapses the request to an objective string;
- does not pass full Hermes/OpenAI `messages`;
- does not pass `tools` / `tool_choice` to the selected worker;
- verifies `content_present=True`, which rejects a valid tool-call response with empty textual content;
- never returns real `tool_calls`.

Therefore the current provider plugin does NOT actually preserve the Hermes agent/tool loop.

Repair the E3 provider boundary so one Hermes chat-completions request can:
1. retain the complete normalized message sequence;
2. retain tool definitions + tool_choice;
3. use E3 ONLY to select an eligible Stage-2 worker/model;
4. dispatch the full provider request through that selected worker's compatible adapter/client;
5. return a Hermes/OpenAI-compatible assistant message containing either:
   - text content, or
   - tool_calls with the correct finish_reason;
6. preserve provider/model/worker metadata and E2/E3 telemetry;
7. verify legitimate tool-call responses without requiring non-empty text;
8. on the next Hermes iteration, accept the assistant tool-call row + tool-result row and route the next model call through E3 again.

Do not build a second unrelated router. Reuse E3 eligibility/ranking/Stage-2 gates.

Add a real integration test using the production E3 provider boundary with fake underlying worker adapters:
- first selected worker returns a valid tool call and no text;
- Hermes-side response exposes that tool call;
- a tool result is appended;
- second E3 request sees the full conversation and returns final text;
- selected worker metadata is present;
- zero real provider calls.

The existing fake-service-only test is insufficient and should remain only as a small unit test if useful.

## Blocker 4 — Chief/department routing disappeared from the new provider seam

Current `hermes-plugins/e3-model-provider/__init__.py` constructs:
`E3ModelClient(E3ApplicationService())`

and `hermes_e3_provider.py` sends the latest user text directly to E3 as:
`task_family="other", required_role="builder"`.

That means `ChiefRouteSelector` and `CareerOpsDepartment` are not in the actual provider path.

Result if activated as-is:
a request like
`the whole agent I want 10 jobs from all the job search agents`
would again become generic AI work instead of deterministic Career Ops ownership.

Repair requirement:

At the E3-backed Hermes provider boundary, on the first model call of a human turn:
- run the provider-neutral Chief intake classification;
- if the request belongs to a deterministic department workflow (Career Ops etc.), execute that department workflow and return its result as the assistant response WITHOUT a model/provider call when no semantic subtask is needed;
- if that workflow needs a semantic subtask, it must call the shared E3 service/provider-selection path;
- generic Chief AI requests proceed to E3 worker selection;
- subsequent model calls in an existing Hermes tool iteration must not re-run the deterministic department action accidentally.

You may factor the Chief provider boundary into a dedicated service; keep the layering:
Hermes agent/session/tools -> Chief intake/department ownership -> E3 model selection for AI work.

## Career Ops live flag

Current `CareerOpsDepartment` only executes discovery when `allow_external=True`, but the default dispatcher constructs it with False.

Define the activation contract explicitly:
- normal live Chief runtime uses the safe read-only external discovery mode for owner-approved Career Ops discovery;
- dry-run/tests remain offline;
- tracker/application mutations remain owner-gated;
- no hidden auto-enable of scheduled tasks.

Prove with a fake orchestrator that the live Chief provider path actually invokes Career Ops and returns bounded results.

## Persistent context

Keep the context work from `029ea7b`, but ensure the model-provider path receives the real Hermes system/memory messages rather than flattening them to `repr(context)`.

Run `scripts/chief_context_preflight.py` metadata-only against the host after code fix (0 provider calls). It must not print private source content.

## Validation

ZERO real provider calls.

Run:
- provider-plugin install/path tests;
- real production-boundary tool-call test with fake adapters;
- Chief/Career Ops provider-path test;
- persistent context preflight metadata only;
- E3 architecture audit;
- focused E3/Chief/Career tests;
- one final full regression.

Do not restart Hermes, select provider e3, or send a live model request.

## Completion report

Report:
- final commit;
- supported plugin install target resolved on this machine;
- stale vendor-copy cleanup status;
- exact E3 worker-selection -> full chat/tool dispatch flow;
- proof first tool-call and second tool-result iteration work through production boundary fakes;
- proof Career Ops is reached in the live Chief provider path;
- context preflight source IDs only;
- test counts;
- real provider calls = 0;
- exact activation + rollback commands for the next turn.

Only after this passes may we restart/switch Hermes to the E3 provider.
