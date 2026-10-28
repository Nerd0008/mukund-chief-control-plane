# Restart-safe Hermes router resolution — 28 October 2026

The registered Windows gateway task inherited a PATH containing the npm Codex launcher but no desktop Codex build. The resolver accepted the first launcher whose version check succeeded. That launcher (0.156.1) rejected the required gpt-6.1-sol model with model_not_found, whereas the desktop installation accepted the same isolated request. Recorded routes succeeded at 22:01 using desktop Codex and failed at 22:04 using the npm launcher. Generic configuration classification hid the model incompatibility, and the native terminal error header incorrectly blamed the configured downstream provider, Nous, even though routing failed first.

Resolution now honours an explicit executable override, otherwise chooses the highest validated native desktop build independently of PATH, and uses PATH only as a fallback. Discovery remains installation-hash agnostic so desktop updates do not require editing a pinned executable path. Invalid installations are excluded; an explicit invalid override is never silently replaced. A working fallback remains available when no desktop build validates. Actual requested-model compatibility is checked by the live verification below rather than inferred from --version.

Model-not-found/unsupported-model failures receive a distinct sanitized error category. Typed router failures now get a router-specific terminal heading; real downstream provider failures retain their existing provider attribution. No model, account, qualification, approval, publishing or fallback policy was changed.

## Validation

Before the repair, four regression checks failed and two controls passed. After it, 128 tests passed across executable resolution, routing, controller eligibility, admission and guarded Windows lifecycle. The regression matrix covers identical selection with service and interactive PATHs, explicit overrides, invalid desktop fallback, unsupported-model classification and correct error attribution.

A temporary non-recurring Windows scheduled task ran under the same principal and startup environment as Hermes. It had no desktop Codex PATH entries. It performed a real routing-model request and then a harmless request through the configured native transport and qualified controller selection. Both completed, with the final response exactly READY. No CV compilation, LinkedIn action or owner message was replayed. No chat message was sent.

The gateway was stopped through its canonical lifecycle and started through its registered Windows task. The same scheduled verification then ran again after restart and selected the same native executable, with both routing and the final task-model response succeeding. The test task was removed after verification. Gateway reconnection and process liveness were checked separately; Discord presence alone was not used as proof of routing readiness.

Private pre/post service-probe JSON and JUnit evidence remain in the owner's workspace under search_fix/. Only source, regression tests and this summary are committed. Runtime copies were checked against the tested source hashes before restart.
