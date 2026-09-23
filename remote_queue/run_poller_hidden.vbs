Option Explicit

Dim shell, fso, scriptDir, repoRoot, pythonExe, poller, cmd, rc
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoRoot = fso.GetParentFolderName(scriptDir)
pythonExe = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\hermes\hermes-agent\venv\Scripts\python.exe"
poller = repoRoot & "\remote_queue\poller.py"

cmd = Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & poller & Chr(34) & " --once"

' 0 = hidden window. Wait for completion so Task Scheduler gets the real exit code.
rc = shell.Run(cmd, 0, True)
WScript.Quit rc
