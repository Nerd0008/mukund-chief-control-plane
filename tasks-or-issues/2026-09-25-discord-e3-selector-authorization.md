# Local E3 Discord/router integration authorization — 2026-09-25

## LOCAL E3 STAGE 2 ENABLEMENT AUTHORIZED

Mukund explicitly authorized fixing the Discord model surface and the automatic E3 model selector on 2026-09-25.

Scope:
- Make Discord's operator-facing model/worker selection reflect the E3 worker registry rather than presenting the native Hermes provider picker as if it were the E3 pool.
- Wire normal Chief/Discord task execution into the E3 Stage 2 orchestration path by default, while preserving an explicit manual override/fallback path.
- Expand the local Stage 2 execution allowlist only to workers with current successful live execution evidence:
  - codex-cli
  - deepseek-v41-flash
  - google-nano-banana-2
  - mistral-small-4
  - longcat-2.0
  - minimax-m3
  - tencent-hunyuan-hy3
- Keep glm-53-flash, qwen38-27b and step-37-flash non-routable/non-selectable for production dispatch until their provider-side blockers are independently cleared.
- A successful smoke test establishes execution readiness, not QUALIFIED capability. Qualification must remain evidence-driven.
- Replace first-candidate/sticky routing with a deterministic auditable selector that considers allowed/routable state, capability evidence, task fit and observed provider health. UNKNOWN cost/capacity must stay UNKNOWN and must not be invented.
- Preserve E1/E2/E3 verification, audit trails, bounded retries, rollback and secret-handling controls.
- Local operation only. No VPS cutover.
