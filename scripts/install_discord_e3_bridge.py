#!/usr/bin/env python3
"""Install the small, reversible Discord-Chief E3 gateway interception.

This never changes credentials, queue history, or the watchdog.  It creates a
timestamped byte-for-byte backup of the vendor gateway source before a single
idempotent patch.  Use ``--restore BACKUP`` to roll it back.
"""
from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

CHIEF_CHANNEL_ID = "1551586294382067762"
MARKER = "# CHIEF_E3_DISCORD_BRIDGE"
RUNTIME = Path.home() / "AppData" / "Local" / "hermes" / "exec-brain"
GATEWAY = Path.home() / "AppData" / "Local" / "hermes" / "hermes-agent" / "gateway" / "run_turn.py"

HELPER = '''    async def _hmwa_try_chief_e3_dispatch(self, message_text, source):
        """Route normal Chief-channel Discord text through E3, never native DeepSeek."""
        # CHIEF_E3_DISCORD_BRIDGE
        platform = source.platform.value if hasattr(source.platform, "value") else str(source.platform)
        if platform != "discord" or str(source.chat_id or "") != "1551586294382067762":
            return None
        if not (message_text or "").strip() or (message_text or "").lstrip().startswith("/"):
            return None
        import asyncio
        import sys
        runtime = r"C:\\Users\\mukun\\AppData\\Local\\hermes\\exec-brain"
        if runtime not in sys.path:
            sys.path.insert(0, runtime)
        try:
            from discord_chief_bridge import dispatch_chief_message
            result = await asyncio.to_thread(dispatch_chief_message, message_text)
        except Exception as exc:
            logger.exception("Chief E3 bridge failed before dispatch: %s", exc)
            return {"final_response": "Chief routing is unavailable; no native provider was used.",
                    "failed": True, "model": "e3-routing", "provider": "e3", "messages": [], "api_calls": 0}
        if result.get("status") == "COMPLETED":
            return {"final_response": result.get("content") or "",
                    "model": result.get("model") or "unknown",
                    "provider": result.get("provider") or "unknown",
                    "messages": [], "api_calls": 1,
                    "chief_e3_worker": result.get("worker_id")}
        logger.error("Chief E3 route exhausted: %s", result.get("attempts"))
        return {"final_response": "Chief routing could not reach an eligible provider.",
                "failed": True, "model": "e3-routing", "provider": "e3", "messages": [], "api_calls": 0}

'''

CALL_OLD = "            agent_result = await self._run_agent(\n"
CALL_NEW = """            bridge_result = await self._hmwa_try_chief_e3_dispatch(message_text, source)
            if bridge_result is not None:
                agent_result = bridge_result
            else:
                agent_result = await self._run_agent(
"""


def install(gateway: Path, dry_run: bool) -> dict:
    text = gateway.read_text(encoding="utf-8")
    if MARKER in text:
        return {"action": "already-installed", "gateway": str(gateway)}
    helper_anchor = "    async def _handle_message_with_agent(self, event, source, _quick_key: str, run_generation: int):\n"
    if helper_anchor not in text or CALL_OLD not in text:
        raise RuntimeError("gateway source shape changed; refusing an unsafe patch")
    patched = text.replace(helper_anchor, HELPER + helper_anchor, 1).replace(CALL_OLD, CALL_NEW, 1)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = gateway.parent / "backups" / f"chief-e3-bridge-{stamp}" / gateway.name
    if not dry_run:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gateway, backup)
        gateway.write_text(patched, encoding="utf-8")
    return {"action": "would-install" if dry_run else "installed", "gateway": str(gateway), "backup": str(backup)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", type=Path, default=GATEWAY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--restore", type=Path)
    args = ap.parse_args()
    if args.restore:
        shutil.copy2(args.restore, args.gateway)
        print({"action": "restored", "gateway": str(args.gateway), "backup": str(args.restore)})
        return 0
    print(install(args.gateway, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
