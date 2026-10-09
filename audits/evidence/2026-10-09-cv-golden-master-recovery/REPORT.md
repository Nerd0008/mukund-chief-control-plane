# CV architecture recovery — 2026-10-09

Root cause: the generic Hermes tool/skill agent handled CV production with terminal/patch access. The installed intake skill explicitly told it to extend cv_tailor.py during an application. The redaction/reinsertion renderer removed neighbouring baseline text; subsequent font/CMap/manual/x-offset repairs compounded corruption. --force and a misleading top-level ok value could leave a failed output available. No programmatic Discord verification gate prevented its attachment.

The visible 150 limit comes from `%LOCALAPPDATA%/hermes/config.yaml` -> `agent.max_turns: 150`, read by `hermes-agent/gateway/run.py::_current_max_iterations` and used when `gateway/run_turn.py` constructs the native AIAgent. It is the general tool-agent budget, not a CV fit budget. The old workflow had no separate fail-closed CV boundary, so model iterations continued after corruption and could patch production code.

SQLite session 20261003_010551_5b27acbc records renderer patches at message IDs 24803/24805/24807/24809/24811/24813, then manual corruption admitted at 24877 (2026-10-08T23:52:09Z), followed by further renderer x-offset patches 24883/24885. The pre-repair dirty renderer/auditor copies were preserved privately outside the live source, with hashes recorded in verification.json. No full session/token dump is committed.

The authoritative owner-uploaded master and current canonical master have the same SHA-256. No current master mutation is present; no evidence of master alteration was found. The failed workflow also referenced a different historical Downloads master, which is now rejected. The renderer WAS modified during the failed run.

A second confirmed interference source is HermesRemoteQueuePoller: remote_queue/poller.py::git_pull_safely uses stash push -> pull --rebase -> stash pop in the active checkout every two minutes. Git stash creates reset-to-HEAD reflog entries and temporarily replaces tracked dirty content; this can disrupt simultaneous repair. Reflog at 01:08/01:10/01:12 BST and queue.log corroborate the synchronizer, not recovery commands. This recovery did not run reset, clean or checkout. The queue/scheduler was not redesigned; committed checkpoints preserve this repair. Future engineering should isolate its active checkout from that synchronizer.

The new CV pipeline has three content-fit attempts per span, one render per job and an eight-turn CV-only native budget. Protected files remain immutable during generation. Discord receives a PDF only after independent PASS validation. The historical overlapping-redaction corruption, font substitution, baseline movement, overflow and unexpected pixels fail regression. Identical inputs produce identical PDF bytes.

The Allstate Graduate Product Engineer CV was rebuilt from the untouched current master, changing only three Professional Summary spans. Structural verification covered 109 spans. Visual diff: zero changed pixels outside authorised boxes at 144 DPI, zero RGB tolerance and documented one-pixel mask-edge rounding. Protected hashes before/after match. The final page preview was inspected; no collision, missing neighbouring text or layout change was observed. The final delivery predicate passes. Existing master facts/content outside those three lines are preserved, not re-authored or fact-certified.

The plugin and revised intake skill are installed. Native initialization and real hook dispatch were proved offline with zero provider calls. The running gateway logged the actual lazy-loaded Discord delivery binding at 01:18:39 BST (PID 70840). No Discord test post or model request was initiated by this recovery.

Final test counts are recorded in verification.json. No main merge.
