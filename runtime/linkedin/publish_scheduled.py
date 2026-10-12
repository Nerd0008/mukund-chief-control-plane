#!/usr/bin/env python3
"""Publish a pre-approved draft for the current day.

Usage: python publish_scheduled.py <day>
Where day is: tuesday, wednesday, or thursday

Finds the newest approved_<YYYYMMDD>_<day>/ directory for the given weekday, so
the schedule does not have to be re-pointed by hand every week (a hardcoded
date previously made the cron jobs publish a stale draft, or fail as a
duplicate, with nobody watching).
"""
import sys
import json
import subprocess
from pathlib import Path

CONTROL_PLANE = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
DRAFTS_DIR = CONTROL_PLANE / "runtime" / "linkedin" / "drafts"
PYTHON = Path(r"C:\Users\mukun\Desktop\Pythob Bot\chief_of_staff_bot\.venv\Scripts\python.exe")
PUBLISH_SCRIPT = CONTROL_PLANE / "career-ops" / "linkedin_publish.py"

VALID_DAYS = ("tuesday", "wednesday", "thursday")


def find_draft_dir(day: str) -> Path | None:
    """Newest approved_<date>_<day> dir that has a draft JSON."""
    candidates = []
    for d in DRAFTS_DIR.glob(f"approved_*_{day}"):
        if (d / "linkedin_drafts.json").exists():
            candidates.append(d)
    if not candidates:
        return None
    # Directory names are approved_<YYYYMMDD>_<day>, so lexical sort == date sort.
    return sorted(candidates, key=lambda p: p.name)[-1]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print("Usage: python publish_scheduled.py <day> [--dry-run]")
        sys.exit(1)

    day = args[0].lower()
    if day not in VALID_DAYS:
        print(f"Invalid day: {day} (expected one of {VALID_DAYS})")
        sys.exit(1)

    draft_dir = find_draft_dir(day)
    if draft_dir is None:
        print(f"No approved draft found for {day} in {DRAFTS_DIR}")
        sys.exit(1)
    draft_path = draft_dir / "linkedin_drafts.json"
    print(f"Draft for {day}: {draft_dir.name}")

    with open(draft_path, encoding="utf-8") as f:
        draft = json.load(f)

    confirm_token = draft["confirm_token"]

    # Verify the draft matches the frozen approved text BEFORE publishing
    verify_script = CONTROL_PLANE / "runtime" / "linkedin" / "verify_draft.py"
    verify_result = subprocess.run(
        [str(PYTHON), str(verify_script), str(draft_dir)],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if verify_result.returncode != 0:
        print(f"VERIFICATION FAILED: {verify_result.stdout.strip()}")
        print("Refusing to publish - draft text does not match approved text")
        sys.exit(1)
    print(f"Verification passed: {verify_result.stdout.strip()}")

    cmd = [
        str(PYTHON), str(PUBLISH_SCRIPT), "publish",
        "--drafts", str(draft_path),
        "--index", "0",
        "--approve-publish",
        "--confirm-token", confirm_token,
    ]

    image_path = draft_dir / "image.jpg"
    if image_path.exists():
        cmd.extend(["--image", str(image_path)])
        print(f"Image: {image_path} ({image_path.stat().st_size} bytes)")
    else:
        print("Image: none found, publishing text only")

    if "--dry-run" in sys.argv:
        cmd.append("--dry-run")

    print(f"Publishing {day} post...")
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode == 0:
        print(f"SUCCESS: {day} post published")
    else:
        print(f"FAILED: {day} post failed with exit code {result.returncode}")

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
