# E3 architecture

## Ownership and call path

`Discord / scheduled task / CLI / remote queue -> Chief/E1 -> deterministic department or workflow -> E3 only for an AI subtask -> Stage 2 -> adapter -> E2 telemetry and E3 verification -> calling workflow -> response`.

Chief owns authorization, intake, session continuity and department routing. Career Ops,
Company Watch, schedules, trackers, approval gates, inbox monitors, CV/application
workflows, the regional job-search workers, the remote queue/watchdog and operational
services keep their existing ownership. E3 is their AI compute dependency; it is not a
replacement for any deterministic workflow.

`ChiefRouteSelector` classifies a turn without naming a provider. A Career Ops turn is
handed to its department dispatcher without a provider call. A Chief AI subtask is declared
once to `E3ApplicationService.execute(objective, task_family, required_role, risk_class,
reasoning_depth, context)`. The service checks Stage 2, creates the task fingerprint and
lets the E3 planner/router choose only an eligible worker. It returns a verified result or a
stable failure category; it never falls through to a native model selector.

Before that dispatch, `ChiefContextCompiler` selects bounded, relevant persistent sources
from canonical project state, the live local `mukund-owner-context` and
`mukund-company-registry` skills, local owner memory, and the append-only Discord/Chief
archive when configured. It includes source hashes and safe paths, labels retrieved facts
separately from inferences, excludes secret-bearing fields, and carries the same package
regardless of which E3 worker is selected. Recent transcript, department state and task
records are optional bounded inputs; provider memory is never treated as the system's
source of truth.

## Discord and scheduled paths

The Discord plugin is observer-only. It cannot reply, return `skip`, classify text, or call
E3. Authenticated Discord traffic continues through Hermes' normal authorization/session
path to the reversible, source-controlled `install_discord_e3_bridge.py` seam. The seam
invokes `dispatch_chief_message()` after authentication and carries session/tool/skill
preservation metadata, while the normal Hermes agent loop remains available for turns
outside the configured Chief channel. `CareerOpsDepartment` binds Career Ops to the
existing scheduled orchestrator and run-health/summary readers; it returns a bounded
read-only workflow result rather than a generic completion or placeholder handoff.

Scheduled and background Career Ops workflows retain their deterministic collection,
eligibility, dedupe, tracker and approval stages. Their semantic classifications call the
same E3 service boundary; they do not construct DeepSeek or Codex adapters or choose a
model. The historical function names remain for compatibility with run records, but the
runtime metadata records E3's actual worker/provider result.

## Provider and safety boundaries

LongCat, Codex and the image-only Google worker are selected only inside E3 according to
the Stage-2 state and task capabilities. DeepSeek's credit state and any disabled provider
cannot stop an eligible E3 fallback. Provider adapters are permitted only in `exec-brain/`
core and named diagnostic scripts. Production business modules, Chief workflows and plugins
must use E3 or deterministic code.

Stage 2 is fail-closed. E3 returns no successful content unless execution and verification
complete. E2 receives the execution telemetry through the existing E3 execution leg. E4/E5
consume the same recorded execution evidence for continuity/safe-mode decisions; neither
changes a worker automatically during a normal request.

## Provenance, rollback and validation

`deploy_e3_runtime.py` has the complete source-controlled runtime module list and creates a
hash manifest plus byte-for-byte backup before a deployment. `e3_runtime_provenance.py` is a
read-only checker: it reports every missing or hash-mismatched Chief/E3 runtime module as
`DRIFT`. This repair intentionally leaves a detected drift un-deployed until the owner
approves activation.

`e3_architecture_audit.py` enforces import boundaries, deployment provenance and the
observer-only Discord invariant with zero provider calls. The deployment script is reversible
with `--restore`; the Discord gateway patcher also takes a timestamped backup and refuses an
unknown gateway shape. No normal path may use native Hermes MoA/OpenRouter as an automatic
fallback.
