import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from remote_queue import queue_schema  # noqa: E402

task, errors = queue_schema.load_task_file(
    REPO / "remote-queue" / "pending" /
    "agent-career-scheduled-cutover-final-acceptance-and-status-reconciliation-2026-09-24.json")
print("errors:", errors)
if task:
    print("task_id:", task["task_id"])
    print("status :", task["status"])
    print("authority:", task["authority"],
          "approved:", task["authority"] in queue_schema.APPROVED_AUTHORITIES)
    print("priority:", task["priority"])
print("RESULT:", "VALID" if task and not errors else "INVALID")
