# Native cooldown recovery

A minimal direct LongCat-2.5 probe using the existing configured endpoint returned READY in 5.5 seconds. Before reload the Discord gateway completed the owner LinkedIn response at 17:33:07 and delivered the requested tracker at 17:33:22. The LinkedIn turn used approximately 127k input tokens and nine calls; the historical session remains intact.

The native execution middleware now waits once through an existing cooldown of up to 30 seconds before selecting a worker for a new model request. Cancellation and the original operation deadline are preserved. It does not clear health records, bypass provider restrictions, change providers or replay tool actions. Longer cooldowns retain existing refusal behavior. This addresses immediate no_healthy_compatible_worker failures during short cooldowns, not the underlying provider/network outage.

Validation: 22 tests passed covering bounded/no wait, cancellation and preserving real provider exceptions. A first regression invocation failed due to missing career-ops on PYTHONPATH; corrected invocation passed. Commit 90d148170 pushed and verified. Gateway gracefully drained and restarted to PID 18776. Provider remains LongCat-2.5. No automatic message sent by this task.
