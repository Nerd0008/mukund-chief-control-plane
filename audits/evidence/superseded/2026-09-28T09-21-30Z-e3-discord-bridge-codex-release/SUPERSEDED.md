# Superseded diagnostic release run

This evidence bundle is preserved as the diagnostic run that found one E1
runtime-matrix failure: `chief_routing.py` and `discord_chief_bridge.py` were
already deployed owner-approved Chief bridge modules, but the static deployed
runtime allowlist did not name them.

The failure was not a provider call, credential, gateway restart, or Stage 2
state change. The allowlist was corrected in `exec-brain/tests/test_eb.py` and
the subsequent final release run is the authoritative acceptance record.
