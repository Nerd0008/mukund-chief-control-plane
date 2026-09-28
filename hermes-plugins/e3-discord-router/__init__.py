"""E3 Discord plugin is diagnostics-only.

Normal Discord messages are deliberately left untouched so Hermes completes
authorization, session/transcript handling, and the source-controlled Chief
bridge.  This prevents a gateway plugin from becoming a competing model router.
"""
from __future__ import annotations


async def _observe_only(event, **_kwargs):
    # Never consume or rewrite ordinary text.  Explicit slash commands are
    # handled by Hermes' command system, not this plugin.
    return None


def register(ctx):
    ctx.register_hook("pre_gateway_dispatch", _observe_only)
