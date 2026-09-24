#!/usr/bin/env python3
"""Verify the *deployed* runtime module carries the new content-stop behaviour.

Runs against %LOCALAPPDATA%/hermes/exec-brain (the live runtime root), not the
repository checkout, and prints only observed values. No provider call.
"""
import json
import os
import sys
from pathlib import Path

runtime_root = Path(os.environ["LOCALAPPDATA"]) / "hermes" / "exec-brain"
sys.path.insert(0, str(runtime_root))

import e3_execution as m  # noqa: E402

out = {
    "imported_from": str(Path(m.__file__).resolve()),
    "default_max_content_stop_retries": m.DEFAULT_MAX_CONTENT_STOP_RETRIES,
    "content_side_finish_reasons": sorted(m.CONTENT_SIDE_STOP_FINISH_REASONS),
    "content_stop_class": m.classify_dispatch_failure({
        "status": "FAILED", "error": "no_image_part_in_response",
        "finish_reason": "IMAGE_RECITATION",
        "candidate_finish_reasons": ["IMAGE_RECITATION"],
        "prompt_feedback": None}),
    "transport_error_class": m.classify_dispatch_failure({
        "status": "FAILED", "error": "http_503",
        "finish_reason": None, "candidate_finish_reasons": [],
        "prompt_feedback": None}),
    "contract_class": m.classify_dispatch_failure({
        "status": "COMPLETED", "error": None, "finish_reason": "STOP",
        "candidate_finish_reasons": ["STOP"], "prompt_feedback": None}),
}
print(json.dumps(out, indent=2))
