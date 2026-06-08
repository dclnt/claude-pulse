# setup-task.ps1
# Registers a Windows Scheduled Task that runs fetch_overwatch.py every 15 minutes.
# No API key required. Data comes from LLM Overwatch's free public feed.
#
# For on-demand refresh without registering a task, just run:
#   .\refresh.bat
#
# HOW TO REGISTER THE TASK (run as your normal user, no admin needed):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\setup-task.ps1
#
# HOW TO VERIFY:
#   Get-ScheduledTask -TaskName "ClaudePerfPulse"
#
# HOW TO UNREGISTER:
#   Unregister-ScheduledTask -TaskName "ClaudePerfPulse" -Confirm:$false

$TaskName  = "ClaudePerfPulse"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$FetchPath = Join-Path $ScriptDir "fetch_overwatch.py"
$PythonExe = (Get-Command python -ErrorAction Stop).Source

if (-not (Test-Path $FetchPath)) {
    Write-Error "fetch_overwatch.py not found at: $FetchPath"
    exit 1
}

Write-Host "Python:    $PythonExe"
Write-Host "Script:    $FetchPath"
Write-Host "Task name: $TaskName"
Write-Host ""

# Action: python fetch_overwatch.py
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$FetchPath`"" `
    -WorkingDirectory $ScriptDir

# Trigger: every 15 minutes (matches the page's 15-min auto-reload).
# LLM Overwatch updates their feed roughly every 5-10 minutes,
# so 15 minutes keeps the dashboard fresh without hammering their server.
$Trigger = New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 15) -Once -At (Get-Date)

# Settings: wake to run, start when available (catch up after sleep)
$Settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName  $TaskName `
    -Action    $Action `
    -Trigger   $Trigger `
    -Settings  $Settings `
    -Principal $Principal `
    -Description "Claude Performance Pulse — fetches LLM Overwatch feed every 15 min, writes data.js for index.html. No API key needed." `
    | Out-Null

Write-Host "Task registered successfully."
Write-Host ""
Write-Host "NEXT STEPS:"
Write-Host "  1. Run one fetch manually to confirm:  python `"$FetchPath`""
Write-Host "     (or just double-click refresh.bat)"
Write-Host "  2. Open index.html in a browser to see the dashboard."
Write-Host ""
Write-Host "To refresh on demand at any time:  .\refresh.bat"
Write-Host "To unregister:  Unregister-ScheduledTask -TaskName ClaudePerfPulse -Confirm:`$false"
