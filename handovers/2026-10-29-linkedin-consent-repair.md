# LinkedIn consent repair — 29 October 2026

Separate factual override receipts from ordinary text approval. Preserve authenticated override provenance across date/image changes and validate it consistently in state and publisher. Invalid self-written overrides still fail. Added an injectable clock and removed wall-clock dependence from two regression tests.

Validation: 247 LinkedIn regression tests passed. Separate local replay using the actual blocked post body passed through isolated approval/override, planning, publisher verification, simulated publication and duplicate prevention. No real publication or production consent was fabricated. Sunday job 7db108b00189 is enabled, last status ok, next run 2026-11-01T08:00:00Z, no_agent weekly script and Discord delivery. Weekly tests cover three-category mix, checkpoint/resume, review failures, quota stops and no unapproved images/publication. Live provider generation/account publication were not exercised.

The active local linkedin-weekly-posts skill now removes the stale mandatory hash fallback. Its updated source is versioned at career-ops/skill-overrides/linkedin-weekly-posts/SKILL.md; pre-edit local backup retained beside the deployed skill. Long-running gateway imports may require reload before code changes take effect. No gateway restart performed by this task.

Standing owner instruction, 29 October 2026: always commit updates to this project. Commit only intended changes; preserve other agents' in-flight work. Owner explicitly authorised pushing this repair to Nerd0008/mukund-chief-control-plane.
