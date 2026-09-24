"""High-recall, multi-stage Career discovery pipeline (control-plane overlay).

Nothing in this package edits the owner's Career Ops installation. It is a
control-plane layer that *reuses* the existing collection, eligibility, dedupe
and tracker-writer code and adds the missing middle of the funnel:

    broad collection
      -> light deterministic prefilter (two-tier title policy)
      -> DeepSeek bulk semantic triage (structured contract)
      -> bounded Codex second pass for ambiguous/high-value candidates only
      -> deterministic eligibility/visa/clearance/URL gates (authoritative)
      -> shared dedupe (career-ops/tracker_writer.py primitives)
      -> tracker manifest / Chief brief handoff (dry-run unless applied)

Modules
-------
``title_policy``       the two-tier title policy (Tier A recall, Tier B negatives)
``semantic_contract``  the classification contract + no-invented-facts guard
``classifiers``        DeepSeek bulk classifier + bounded Codex escalation
``funnel``             funnel metrics that make a zero explainable
``pipeline``           orchestration + CLI (run / compare-modes / selftest)
"""

SCHEMA_VERSION = 1
