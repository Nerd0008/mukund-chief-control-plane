# Router-core acceptance — 25 October 2026

Owner authorized GPT-6.1 Sol through the existing Codex CLI for router reasoning,
and clarified that worker selection must be unbiased and evidence-based.

- Model requested: `gpt-6.1-sol`; reasoning requested: `high`.
- Existing validated native Codex CLI: 0.163.0-alpha.10.2. The older 0.156.1
  command shim rejected this model. There is no silent model substitution.
- Router CLI profile is read-only, ephemeral, with user config/repository rules,
  shell/unified execution, multi-agent and web search disabled for this role.
- Eligible workers are filtered before reasoning. The model receives random
  handles and task/capability/qualification evidence, not provider/model identities.
- Hardcoded LongCat primary and Codex fallback preferences removed. Fallbacks
  follow the same eligible ranking; permission/Stage-2 gates remain unchanged.
- Task risk is used for candidate qualification instead of an assumed R1.
- Fail closed on invalid JSON/schema, changed candidate set, timeout, tool use,
  owner-review requirement or inability to persist the audit receipt.
- Two synthetic live neutrality checks passed: non-OpenAI won when its evidence
  was stronger; OpenAI won when its evidence was stronger (4.172s / 4.500s).
- Installed/configured runtime acceptance passed (6.453s). No downstream worker
  executed. These checks demonstrate the tested cases, not universal fairness.
- Focused release regression: 117 passed. Broader E3 regression: 450 passed,
  one known architecture test deselected after reproducing its existing failure.
  That test identifies discovery's two direct business-adapter imports. It was
  neither removed nor weakened. Legacy E1/E2 tests were not run: governor is an
  installed-only dependency and its tests include live provider probes.
- Five installed module hashes verified against source; backups were verified
  before replacement. Independent native-executable resolver behavior found in
  the installed adapter was preserved in source.
- Local non-secret router policy enabled. Worker Stage-2 allowlist and capability
  qualification records were not expanded or relabelled from synthetic tests.
- Existing source/dirty files preserved in a 112-file private recovery snapshot.
  No reset, cleanup, stash, shared-checkout rebase, main merge, gateway restart,
  application, outreach, Gmail mutation or LinkedIn action.

## Scope still incomplete

E3 application calls and deployed canonical E3 CLI execution consult the reasoner.
Normal native Hermes conversations, CV planning, discovery, LinkedIn generation,
cron and auxiliary helper calls still have the bypasses recorded in the coverage
audit. This is NOT a universal rollout. Setting a router model does not migrate
those execution boundaries or repair the inactive provider integration. No claim
of complete Hermes routing coverage or production-wide PASS is made here.

Private policy, runtime backups, receipts and detailed evidence are outside Git.
Only source, tests, documentation and this aggregate acceptance are committed.
