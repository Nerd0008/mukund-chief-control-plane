#!/usr/bin/env python3
"""Funnel metrics — every zero must say WHERE the funnel went to zero.

The counters are the ones the owner asked for:

    discovered_raw, after_hard_negative_prefilter, semantically_reviewed,
    deepseek_accept, codex_escalated, codex_accept,
    deterministic_eligibility_pass, duplicates_removed, tracker_candidates

plus ``rejections_by_reason`` and an ``attribution`` block that names the first
stage that emptied the funnel. A stage count of zero is never reported without
the reason attached to it.

Per-source attribution
----------------------
Every discovery surface (regional scan, Company Watch, recruiter/intermediary
watch, LinkedIn export, …) feeds the same funnel, so every counter is also kept
**per source**: ``by_source[source]`` carries the source's own stage counts, its
own ``rejections_by_reason`` and its own ``zero_attribution``. A canonical
candidate that several sources discovered is counted once in each of those
sources (so the per-source numbers sum to more than the global total by design)
and the ``shared_candidates`` block records that overlap explicitly. A source
that produced zero tracker candidates therefore says *where* it went to zero
without borrowing another source's counters.
"""

from __future__ import annotations

import json
from collections import Counter

COUNT_KEYS = (
    "discovered_raw",
    "canonical_candidates",
    "cross_source_duplicates_removed",
    "after_hard_negative_prefilter",
    "semantically_reviewed",
    "deepseek_accept",
    "codex_escalated",
    "codex_accept",
    "deterministic_eligibility_pass",
    "duplicates_removed",
    "tracker_candidates",
)

STAGE_ORDER = (
    ("discovered_raw", "collection returned no candidate records at all"),
    ("after_hard_negative_prefilter", "every discovered candidate was removed by Tier B "
                                      "hard-negative / non-cyber / no-signal hints"),
    ("semantically_reviewed", "no candidate reached the semantic stage"),
    ("deepseek_accept", "the semantic stage accepted nothing"),
    ("deterministic_eligibility_pass", "every semantically accepted candidate failed a "
                                       "deterministic gate (location, work authorisation, "
                                       "clearance, experience or URL)"),
    ("duplicates_removed", "all eligible candidates were already canonical/known (dedupe)"),
    ("tracker_candidates", "nothing remained for tracker handoff"),
)

#: per-source stage order. ``discovered`` is the source's own raw count; the rest
#: count the canonical candidates attributable to that source at each stage.
SOURCE_STAGE_ORDER = (
    ("discovered", "this source returned no candidate records"),
    ("after_hard_negative_prefilter", "every candidate from this source was removed by the "
                                      "Tier B hard-negative / non-cyber / no-signal prefilter"),
    ("semantically_reviewed", "no candidate from this source reached the semantic stage"),
    ("semantic_accept", "the semantic stage accepted nothing from this source"),
    ("deterministic_eligibility_pass", "every semantically accepted candidate from this source "
                                       "failed a deterministic gate (location, work "
                                       "authorisation, clearance, experience or URL)"),
    ("tracker_candidates", "nothing from this source remained for tracker handoff (dedupe or "
                           "an upstream stage)"),
)


class Funnel:
    """Accumulates the funnel counters and rejection reasons for one run."""

    def __init__(self) -> None:
        self.counts = {k: 0 for k in COUNT_KEYS}
        self.rejections = Counter()
        self.notes: list = []
        self.discovered_by_source: Counter[str] = Counter()
        self.not_applicable: dict[str, str] = {}
        self.reasons_override: dict[str, str] = {}
        # per-source stage counters and rejection reasons
        self.source_counts: dict[str, Counter] = {}
        self.source_rejections: dict[str, Counter] = {}
        self.source_not_applicable: dict[str, dict] = {}
        self.shared_candidates: dict = {}

    def set(self, key: str, value: int) -> None:
        self.counts[key] = int(value)

    def inc(self, key: str, value: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + int(value)

    def reject(self, reason: str, *, stage: str | None = None,
               sources: list | None = None) -> None:
        self.rejections[reason] += 1
        if stage:
            self.rejections[f"stage:{stage}"] += 0
        for source in sources or []:
            self.source_rejections.setdefault(source, Counter())[reason] += 1

    def discover(self, source: str, n: int) -> None:
        self.discovered_by_source[source] += int(n)
        self.inc("discovered_raw", n)
        self.source_counts.setdefault(source, Counter())["discovered"] += int(n)

    def source_stage(self, source: str, key: str, n: int = 1) -> None:
        """Increment one stage of one source's own funnel counters."""
        self.source_counts.setdefault(source, Counter())[key] += int(n)

    def source_stages(self, sources: list | None, key: str, n: int = 1) -> None:
        """Increment one stage for every source that discovered the candidate."""
        for source in sources or []:
            self.source_stage(source, key, n)

    def source_skip(self, key: str, reason: str) -> None:
        """Mark one per-source stage as structurally not applicable in this run.

        Mirrors :meth:`skip` for the per-source counters, so a stage that was
        disabled by configuration is never reported as a source's funnel zero.
        """
        for source in self.source_counts:
            self.source_not_applicable.setdefault(source, {})[key] = reason

    def note(self, text: str) -> None:
        if text and text not in self.notes:
            self.notes.append(text)

    def skip(self, key: str, reason: str) -> None:
        """Mark a counter as structurally not applicable in this run.

        A stage that was *disabled by configuration* is not a funnel zero, and
        must not be reported as the place the funnel died.
        """
        self.not_applicable[key] = reason

    def explain(self, key: str, reason: str) -> None:
        """Override the generic stage text with this run's actual cause."""
        self.reasons_override[key] = reason

    def document(self) -> dict:
        counts: dict[str, object] = dict(self.counts)
        counts["discovered_raw_by_source"] = dict(sorted(self.discovered_by_source.items()))
        zero_attribution = self.zero_attribution()
        return {
            "counts": counts,
            "rejections_by_reason": dict(sorted(self.rejections.items())),
            "zero_attribution": zero_attribution,
            "not_applicable_stages": dict(sorted(self.not_applicable.items())),
            "by_source": self.by_source(),
            "shared_candidates": dict(self.shared_candidates),
            "notes": list(self.notes),
        }

    def by_source(self) -> dict:
        """Every source's own stage counts, rejections and first zero."""
        out: dict = {}
        for source in sorted(self.source_counts):
            counts = {k: int(v) for k, v in sorted(self.source_counts[source].items())}
            rejections = dict(sorted(self.source_rejections.get(source, Counter()).items()))
            entry = {
                "counts": counts,
                "rejections_by_reason": rejections,
                "not_applicable_stages": dict(sorted(
                    (self.source_not_applicable.get(source) or {}).items())),
                "zero_attribution": self.source_zero_attribution(source),
            }
            shared = (self.shared_candidates.get("by_source") or {}).get(source)
            if shared:
                entry["shared_candidate_ids"] = sorted(shared.get("candidate_ids") or [])
                entry["shared_with"] = sorted(shared.get("shared_with") or {})
            out[source] = entry
        return out

    def source_zero_attribution(self, source: str) -> dict:
        """Name the first stage THIS source reached zero at, and why."""
        counts = self.source_counts.get(source) or {}
        not_applicable = self.source_not_applicable.get(source) or {}
        if not counts.get("discovered"):
            return {"first_zero_stage": "discovered",
                    "reason": "this source returned no candidate records",
                    "not_applicable_stages": dict(sorted(not_applicable.items())),
                    "attribution_source": "per-source funnel counters (not an inference "
                                          "about the job market or about real vacancies)"}
        for key, reason in SOURCE_STAGE_ORDER[1:]:
            if key in not_applicable:
                continue
            if counts.get(key, 0) == 0:
                return {"first_zero_stage": key, "reason": reason,
                        "not_applicable_stages": dict(sorted(not_applicable.items())),
                        "attribution_source": "per-source funnel counters (not an inference "
                                              "about the job market or about real vacancies)"}
        return {"first_zero_stage": None, "reason": None,
                "not_applicable_stages": dict(sorted(not_applicable.items())),
                "attribution_source": "per-source funnel counters"}

    def zero_attribution(self) -> dict:
        """Name the first stage that reached zero, and why."""
        for key, reason in STAGE_ORDER:
            if key in self.not_applicable:
                continue
            if self.counts.get(key, 0) == 0:
                return {"first_zero_stage": key,
                        "reason": self.reasons_override.get(key, reason),
                        "skipped_not_applicable": dict(sorted(self.not_applicable.items())),
                        "attribution_source": "funnel counters (not an inference about the "
                                              "job market or about real vacancies)"}
        return {"first_zero_stage": None, "reason": None,
                "skipped_not_applicable": dict(sorted(self.not_applicable.items())),
                "attribution_source": "funnel counters"}

    def summary_line(self) -> str:
        z = self.zero_attribution()
        if z["first_zero_stage"] is None:
            return "funnel produced tracker candidates"
        return f"funnel went to zero at {z['first_zero_stage']}: {z['reason']}"


def dumps(doc) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False, default=str)
