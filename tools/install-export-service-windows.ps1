#requires -Version 5.1
<#
.SYNOPSIS
    Installs the onec-mcp-universal BSL export service as a Windows Scheduled Task
    that auto-starts at user logon (survives reboots).

.DESCRIPTION
    The BSL export service (tools/export-host-service.py) provides BSL source export
    via 1cv8 DESIGNER on the Windows host. It must run continuously for the gateway
    to call it via http://host.docker.internal:8082.

    This script registers a Scheduled Task that:
    - Runs at user logon (no admin password needed)
    - Restarts on failure
    - Runs hidden (no console window)
    - Logs to %TEMP%\onec-export-service.log

.NOTES
    Run from the repository root as the user who will use Codex or another MCP client.
    Does NOT require administrator privileges (uses user-scope task).
#>

$ErrorActionPreference = "Stop"

$TaskName = "OnecMcpExportService"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$ServiceScript = Join-Path $ScriptDir "export-host-service.py"
$LogFile = Join-Path $env:TEMP "onec-export-service.log"

# Find Python
$Python = $null
$PythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        $Python = $found.Source
        $PythonCmd = $cmd
        break
    }
}

if (-not $Python) {
    Write-Host "ERROR: Python not found. Install Python 3.10+ from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ServiceScript)) {
    Write-Host "ERROR: $ServiceScript not found" -ForegroundColor Red
    exit 1
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key
    )
    if (-not (Test-Path $Path)) { return $null }
    foreach ($line in Get-Content -Path $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -match "^${Key}=(.*)$") {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

$EnvFile = Join-Path $RepoRoot ".env"
$V8Path = Get-EnvValue -Path $EnvFile -Key "V8_PATH"

Write-Host "Python:        $Python"
Write-Host "Service:       $ServiceScript"
Write-Host "Task name:     $TaskName"
Write-Host "Log file:      $LogFile"
Write-Host "Workspace:     dynamic (.env / request-driven)"
if ($V8Path) {
    Write-Host "V8_PATH:       $V8Path"
}
Write-Host ""

# Remove existing task
try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    Write-Host "Removed existing task '$TaskName'"
} catch {
    # Task doesn't exist — fine
}

# Build command args (py launcher needs -3)
$TaskArgs = if ($PythonCmd -eq "py") {
    "-3 `"$ServiceScript`" --port 8082"
} else {
    "`"$ServiceScript`" --port 8082"
}
$CmdPrefix = if ($V8Path) { "set `"V8_PATH=$V8Path`" && " } else { "" }
$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c $CmdPrefix`"$Python`" $TaskArgs >> `"$LogFile`" 2>&1"
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 0) `
    -Hidden
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "BSL export service for onec-mcp-universal MCP gateway" `
        | Out-Null
    Write-Host "[+] Scheduled Task '$TaskName' registered" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Failed to register task: $_" -ForegroundColor Red
    exit 1
}

# Try to start it now
try {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "[+] Task started — BSL export service should now be running on port 8082" -ForegroundColor Green
} catch {
    Write-Host "[!] Task registered but could not start immediately. It will start at next logon." -ForegroundColor Yellow
}

Start-Sleep -Seconds 1
try {
    $health = Invoke-RestMethod -Method GET -Uri "http://localhost:8082/health" -TimeoutSec 3
    if ($health.ok -eq $true) {
        Write-Host "[+] Health check: http://localhost:8082/health OK" -ForegroundColor Green
    } else {
        Write-Host "[!] Health check returned unexpected response" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[!] Health check failed. Task may still start after logon. See log:" -ForegroundColor Yellow
    Write-Host "    $LogFile"
}

Write-Host ""
Write-Host "To uninstall: Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
Write-Host "To check status: Get-ScheduledTask -TaskName $TaskName"
Write-Host "Logs: $LogFile"
