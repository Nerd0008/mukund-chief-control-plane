#!/usr/bin/env python3
"""Funnel metrics — every zero must say WHERE the funnel went to zero.

The counters are the ones the owner asked for:

    discovered_raw, after_hard_negative_prefilter, semantically_reviewed,
    deepseek_accept, codex_escalated, codex_accept,
    deterministic_eligibility_pass, duplicates_removed, tracker_candidates

plus ``rejections_by_reason`` and an ``attribution`` block that names the first
stage that emptied the funnel. A stage count of zero is never reported without
the reason attached to it.
"""

from __future__ import annotations

import json
from collections import Counter

COUNT_KEYS = (
    "discovered_raw",
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


class Funnel:
    """Accumulates the funnel counters and rejection reasons for one run."""

    def __init__(self) -> None:
        self.counts = {k: 0 for k in COUNT_KEYS}
        self.rejections = Counter()
        self.notes: list = []
        self.discovered_by_source: Counter[str] = Counter()

    def set(self, key: str, value: int) -> None:
        self.counts[key] = int(value)

    def inc(self, key: str, value: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + int(value)

    def reject(self, reason: str, *, stage: str | None = None) -> None:
        self.rejections[reason] += 1
        if stage:
            self.rejections[f"stage:{stage}"] += 0

    def discover(self, source: str, n: int) -> None:
        self.discovered_by_source[source] += int(n)
        self.inc("discovered_raw", n)

    def note(self, text: str) -> None:
        if text and text not in self.notes:
            self.notes.append(text)

    def document(self) -> dict:
        counts: dict[str, object] = dict(self.counts)
        counts["discovered_raw_by_source"] = dict(sorted(self.discovered_by_source.items()))
        zero_attribution = self.zero_attribution()
        return {
            "counts": counts,
            "rejections_by_reason": dict(sorted(self.rejections.items())),
            "zero_attribution": zero_attribution,
            "notes": list(self.notes),
        }

    def zero_attribution(self) -> dict:
        """Name the first stage that reached zero, and why."""
        for key, reason in STAGE_ORDER:
            if self.counts.get(key, 0) == 0:
                return {"first_zero_stage": key,
                        "reason": reason,
                        "attribution_source": "funnel counters (not an inference about the "
                                              "job market or about real vacancies)"}
        return {"first_zero_stage": None, "reason": None,
                "attribution_source": "funnel counters"}

    def summary_line(self) -> str:
        z = self.zero_attribution()
        if z["first_zero_stage"] is None:
            return "funnel produced tracker candidates"
        return f"funnel went to zero at {z['first_zero_stage']}: {z['reason']}"


def dumps(doc) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False, default=str)
