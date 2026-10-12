# Silent Windows scheduled launchers (2026-10-12)

The five-minute ChiefGatewayWatchdog launched Python directly and spawned PowerShell without CREATE_NO_WINDOW. The poller was already disabled and was not this recurrence.

Existing enabled Chief scheduled actions now use per-task WScript wrappers in LOCALAPPDATA/hermes/gateway-service/hidden-tasks. Wrappers use WScript.Shell.Run(command, 0, True) and WScript.Quit(child_exit_code). Existing executable/arguments are preserved inside the wrapper, including cmd /d /s /c for batch entrypoints. Original working directories, triggers, principals and settings are preserved. The launcher waits for completion, preserving scheduler overlap and exit-status behavior.

ChiefDiscordSync has a protected task definition. Its Python wrapper now hides only its private single-process console (never a shared interactive terminal) and uses CREATE_NO_WINDOW for the child. Watchdog subprocesses also use CREATE_NO_WINDOW. Jobs are not disabled, and Hermes_Gateway remains its existing VBS launcher. HermesRemoteQueuePoller remains disabled.

Private recovery copies and exported pre-change task XML: Documents/Codex/terminal-window-recovery-20261012. Restore an individual task from its original XML only after confirming owner account and schedule; do not replace all tasks blindly.

Controlled watchdog acceptance: exit 0, ALIVE=1, zero new visible ConsoleWindowClass or CASCADIA_HOSTING_WINDOW_CLASS windows across 10 seconds. No Gmail/provider calls or Discord messages were sent by that acceptance.
