"""Gateway watchdog: restart the Hermes gateway process if it dies.

Checks every 60s whether a python process running `hermes_cli.main gateway run`
is alive. If not, relaunches it via the same VBS/Task Scheduler path.

Runs as a Windows scheduled task (ChiefGatewayWatchdog) every 5 minutes.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
GATEWAY_VBS = HERMES_HOME / "gateway-service" / "Hermes_Gateway.vbs"
GATEWAY_LOG = HERMES_HOME / "logs" / "gateway-watchdog.log"
CHECK_INTERVAL = 60  # seconds between checks when running as a loop
TASK_MODE = "--task-mode" in sys.argv  # single check when run from Task Scheduler


def log(msg: str):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        GATEWAY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(GATEWAY_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def gateway_alive() -> bool:
    """Check if a python process running `hermes_cli.main gateway run` exists."""
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -match 'hermes_cli\\.main gateway run' } | "
                "Select-Object -First 1 -ExpandProperty ProcessId",
            ],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            capture_output=True,
            text=True,
            timeout=15,
        )
        pid = result.stdout.strip()
        return bool(pid and pid.isdigit())
    except Exception:
        return False


def restart_gateway():
    """Restart the gateway via the Task Scheduler task."""
    try:
        subprocess.run(
            [
                "schtasks",
                "/run",
                "/tn",
                "Hermes_Gateway",
            ],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            capture_output=True,
            text=True,
            timeout=30,
        )
        log("RESTART: triggered Hermes_Gateway task")
    except Exception as e:
        log(f"RESTART FAILED: {e}")


def main():
    if TASK_MODE:
        # Single check mode (called from Task Scheduler every 5 min)
        if not gateway_alive():
            log("ALIVE=0 — restarting gateway")
            restart_gateway()
        else:
            log("ALIVE=1")
        return

    # Loop mode (run manually or as a persistent background process)
    log("Watchdog started (loop mode)")
    while True:
        if not gateway_alive():
            log("ALIVE=0 — restarting gateway")
            restart_gateway()
            time.sleep(30)  # give it time to come up
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
