[CmdletBinding()]
param([switch]$Enable)
$ErrorActionPreference = 'Stop'
$taskName = 'ChiefCareerGmailMonitor'
$repoRoot = Split-Path $PSScriptRoot -Parent
$careerPython = Join-Path $env:LOCALAPPDATA 'hermes\hermes-agent\venv\Scripts\python.exe'
$entrypoint = Join-Path $PSScriptRoot 'career_mail_monitor.py'
$principalName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
if ($principalName -ne 'MISTY\mukun') { throw 'Must install under the approved owner Windows account.' }
$arguments = '"' + $entrypoint + '" scan --apply'
if (-not $Enable) {
    [pscustomobject]@{TaskName=$taskName;Executable=$careerPython;Arguments=$arguments;Principal=$principalName;IntervalMinutes=60;InstallEnabled=$false} | ConvertTo-Json
    return
}
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'hermes\runtime\career-ops\gmail-monitor'
$approval = Get-Content -LiteralPath (Join-Path $runtimeRoot 'write-approval.json') -Raw | ConvertFrom-Json
if (-not $approval.approved_report_id) { throw 'An approved production dry-run report is required.' }
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Principal.UserId -notin @($principalName,[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value)) { throw 'Existing task belongs to another principal.' }
    Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $runtimeRoot 'scheduled-task-before.xml') -Encoding utf8
}
$action = New-ScheduledTaskAction -Execute $careerPython -Argument $arguments -WorkingDirectory $repoRoot
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).AddHours(1) -RepetitionInterval (New-TimeSpan -Hours 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $principalName
$principal = New-ScheduledTaskPrincipal -UserId $principalName -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$task = New-ScheduledTask -Action $action -Trigger @($hourly,$logon) -Principal $principal -Settings $settings -Description 'Owner-approved Career Ops Gmail read-only ingestion; guarded tracker and owned-calendar updates. No outreach.'
Register-ScheduledTask -TaskName $taskName -InputObject $task -Force | Out-Null
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $runtimeRoot 'scheduled-task-active.xml') -Encoding utf8
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State,@{n='Principal';e={$_.Principal.UserId}},@{n='Executable';e={$_.Actions.Execute}},@{n='Arguments';e={$_.Actions.Arguments}} | ConvertTo-Json
