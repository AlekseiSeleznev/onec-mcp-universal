#requires -Version 5.1
$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$Passes = 0
$Warns = 0
$Fails = 0
$LocalHealthHost = "127.0.0.1"

function Pass([string]$Msg) { Write-Host "[PASS] $Msg" -ForegroundColor Green; $script:Passes++ }
function Warn([string]$Msg) { Write-Host "[WARN] $Msg" -ForegroundColor Yellow; $script:Warns++ }
function Fail([string]$Msg) { Write-Host "[FAIL] $Msg" -ForegroundColor Red; $script:Fails++ }

function Get-EnvValue([string]$Path, [string]$Key) {
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

function Test-HttpOk([string]$Url) {
    try {
        $null = Invoke-WebRequest -Uri $Url -TimeoutSec 4 -UseBasicParsing
        return $true
    } catch {
        return $false
    }
}

function Get-HttpStatus([string]$Url, [string]$BearerToken = "") {
    try {
        $Headers = @{}
        if ($BearerToken) { $Headers["Authorization"] = "Bearer $BearerToken" }
        $Resp = Invoke-WebRequest -Uri $Url -TimeoutSec 4 -UseBasicParsing -Headers $Headers
        return [string]$Resp.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [string][int]$_.Exception.Response.StatusCode
        }
        return ""
    }
}

Write-Host "== onec-mcp-universal verify =="

$EnvFile = Join-Path $ScriptDir ".env"
if (-not (Test-Path $EnvFile)) {
    Warn ".env not found; using defaults"
}

$GwPort = Get-EnvValue -Path $EnvFile -Key "GW_PORT"
if (-not $GwPort) { $GwPort = "8080" }
$EnabledBackends = Get-EnvValue -Path $EnvFile -Key "ENABLED_BACKENDS"
if (-not $EnabledBackends) { $EnabledBackends = "onec-toolkit,platform-context,bsl-lsp-bridge" }
$DockerControlToken = Get-EnvValue -Path $EnvFile -Key "DOCKER_CONTROL_TOKEN"
$AnonymizerSalt = Get-EnvValue -Path $EnvFile -Key "ANONYMIZER_SALT"

$DockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if ($DockerCmd) {
    Pass "docker command found"
} else {
    Fail "docker command not found"
}

if ($DockerCmd) {
    docker info *> $null
    if ($LASTEXITCODE -eq 0) {
        Pass "docker daemon is running"
    } else {
        Fail "docker daemon is not running"
    }
}

$GatewayHealthUrl = "http://$LocalHealthHost:$GwPort/health"
if (Test-HttpOk $GatewayHealthUrl) {
    try {
        $Body = Invoke-RestMethod -Uri $GatewayHealthUrl -TimeoutSec 4
        if ($Body.status -eq "ok") {
            Pass "gateway health endpoint is OK ($GatewayHealthUrl)"
        } else {
            Warn "gateway health endpoint is reachable but response is unexpected"
        }
    } catch {
        Warn "gateway health endpoint is reachable but JSON parse failed"
    }
} else {
    Fail "gateway health endpoint is unreachable ($GatewayHealthUrl)"
}

if ($DockerCmd) {
    $PsOutput = docker ps --format '{{.Names}} {{.Status}}' 2>$null
    if ($PsOutput -match '^onec-mcp-gw .*healthy') {
        Pass "container onec-mcp-gw is running and healthy"
    } elseif ($PsOutput -match '^onec-mcp-gw ') {
        Warn "container onec-mcp-gw is running but health is not healthy yet"
    } else {
        Fail "container onec-mcp-gw is not running"
    }
}

function Test-DockerControlHealth {
    if (Test-HttpOk "http://$LocalHealthHost:8091/health") {
        return @{ Ok = $true; Via = "host"; Url = "http://$LocalHealthHost:8091/health" }
    }
    docker exec onec-mcp-gw python -c "import http.client, sys; conn=http.client.HTTPConnection('docker-control', 8091, timeout=5); conn.request('GET', '/health'); resp=conn.getresponse(); sys.exit(0 if resp.status == 200 else 1)" *> $null
    if ($LASTEXITCODE -eq 0) {
        return @{ Ok = $true; Via = "gateway"; Url = "http://docker-control:8091/health" }
    }
    return @{ Ok = $false; Via = "gateway"; Url = "http://docker-control:8091/health" }
}

function Get-DockerControlGuardStatus {
    $HostStatus = Get-HttpStatus -Url "http://$LocalHealthHost:8091/api/docker/system"
    if ($HostStatus) { return $HostStatus }
    $Status = docker exec onec-mcp-gw python -c "import http.client; conn=http.client.HTTPConnection('docker-control', 8091, timeout=5); conn.request('GET', '/api/docker/system'); resp=conn.getresponse(); print(resp.status)" 2>$null
    return ($Status | Out-String).Trim()
}

$DockerControlHealth = Test-DockerControlHealth
if ($DockerControlHealth.Ok) {
    if ($DockerControlHealth.Via -eq "host") {
        Pass "docker-control is reachable ($($DockerControlHealth.Url))"
    } else {
        Pass "docker-control is reachable via onec-mcp-gw ($($DockerControlHealth.Url))"
    }
} else {
    if ($DockerControlHealth.Via -eq "host") {
        Fail "docker-control is unreachable (http://$LocalHealthHost:8091/health)"
    } else {
        Fail "docker-control is unreachable via onec-mcp-gw (http://docker-control:8091/health)"
    }
}

if ($DockerControlToken) {
    Pass "DOCKER_CONTROL_TOKEN is configured"
} else {
    Fail "DOCKER_CONTROL_TOKEN is missing in .env"
}

if ($AnonymizerSalt) {
    Pass "ANONYMIZER_SALT is configured"
} else {
    Fail "ANONYMIZER_SALT is missing in .env"
}

$DockerControlGuardStatus = Get-DockerControlGuardStatus
if ($DockerControlGuardStatus -eq "401") {
    Pass "docker-control protected API rejects unauthenticated requests with 401"
} else {
    Fail "docker-control protected API expected 401 without token, got '$DockerControlGuardStatus'"
}

if (Test-HttpOk "http://$LocalHealthHost:8082/health") {
    Pass "export-host-service is reachable (http://$LocalHealthHost:8082/health)"
} else {
    Fail "export-host-service is unreachable (http://$LocalHealthHost:8082/health)"
}

if ($DockerCmd) {
    $ContainerNames = docker ps --format '{{.Names}}' 2>$null
    if ($ContainerNames -contains "onec-bsl-graph") {
        if (Test-HttpOk "http://$LocalHealthHost:8888/health") {
            Pass "bsl-graph is reachable (http://$LocalHealthHost:8888/health)"
        } else {
            Fail "bsl-graph container is running but health endpoint is unreachable"
        }
    } else {
        Warn "bsl-graph profile is not running (optional)"
    }
}

if ($DockerCmd) {
    $ContainerNames = docker ps --format '{{.Names}}' 2>$null
    if ($EnabledBackends.Split(",") -contains "onec-toolkit") {
        if ($ContainerNames -contains "onec-mcp-toolkit") {
            Pass "onec-toolkit backend container is running"
        } else {
            Fail "onec-toolkit backend is enabled but onec-mcp-toolkit container is not running"
        }
    }
    if ($EnabledBackends.Split(",") -contains "platform-context") {
        if ($ContainerNames -contains "onec-mcp-platform") {
            Pass "platform-context backend container is running"
        } else {
            Fail "platform-context backend is enabled but onec-mcp-platform container is not running"
        }
    }
    if ($EnabledBackends.Split(",") -contains "bsl-lsp-bridge") {
        $Images = docker images --format '{{.Repository}}:{{.Tag}}' 2>$null
        if ($Images -match '^mcp-lsp-bridge-bsl:') {
            Pass "bsl-lsp-bridge image is present"
        } else {
            Warn "bsl-lsp-bridge is enabled, but image mcp-lsp-bridge-bsl is missing"
        }
    }
}

$CodexCmd = Get-Command codex -ErrorAction SilentlyContinue
if ($CodexCmd) {
    $McpList = codex mcp list 2>$null
    if ($McpList -match "onec-universal") {
        Pass "Codex MCP registration 'onec-universal' found"
    } else {
        Warn "Codex CLI found, but MCP registration 'onec-universal' not found"
    }
} else {
    Warn "Codex CLI is not installed; MCP registration check skipped"
}

Write-Host ""
Write-Host ("Summary: PASS={0}, WARN={1}, FAIL={2}" -f $Passes, $Warns, $Fails)
if ($Fails -gt 0) { exit 1 }
exit 0
