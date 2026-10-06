#!/usr/bin/env python3
"""Publish a pre-approved draft for the current day.

Usage: python publish_scheduled.py <day>
Where day is: tuesday, wednesday, or thursday
"""
import sys
import json
import subprocess
from pathlib import Path

CONTROL_PLANE = Path(r"C:\Users\mukun\Documents\mukund-chief-control-plane")
DRAFTS_DIR = CONTROL_PLANE / "runtime" / "linkedin" / "drafts"
PYTHON = Path(r"C:\Users\mukun\Desktop\Pythob Bot\chief_of_staff_bot\.venv\Scripts\python.exe")
PUBLISH_SCRIPT = CONTROL_PLANE / "career-ops" / "linkedin_publish.py"

def main():
    if len(sys.argv) != 2:
        print("Usage: python publish_scheduled.py <day>")
        sys.exit(1)
    
    day = sys.argv[1].lower()
    if day not in ('tuesday', 'wednesday', 'thursday'):
        print(f"Invalid day: {day}")
        sys.exit(1)
    
    # Map day to date suffix
    date_suffix = {'tuesday': '06', 'wednesday': '07', 'thursday': '08'}[day]
    draft_dir = DRAFTS_DIR / f"approved_202610{date_suffix}_{day}"
    draft_path = draft_dir / "linkedin_drafts.json"
    
    if not draft_path.exists():
        print(f"Draft not found: {draft_path}")
        sys.exit(1)
    
    with open(draft_path) as f:
        draft = json.load(f)
    
    confirm_token = draft['confirm_token']
    image_path = draft.get('image_path')
    
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

    # Build command
    cmd = [
        str(PYTHON), str(PUBLISH_SCRIPT), "publish",
        "--drafts", str(draft_path),
        "--index", "0",
        "--approve-publish",
        "--confirm-token", confirm_token,
    ]
    
    if image_path and Path(image_path).exists():
        cmd.extend(["--image", image_path])
    
    print(f"Publishing {day} post...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
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
