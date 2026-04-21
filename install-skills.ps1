# Install 1C skills for Codex and compatible local skill runners (Windows).
# Creates links or directory copies from %USERPROFILE%\.codex\skills\
# to the project's skills\ directory.
# Usage: powershell -ExecutionPolicy Bypass -File install-skills.ps1
# Symlinks require Developer Mode or Administrator privileges.
# Falls back to directory copies if symlinks are unavailable.

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillsSrc = Join-Path $ScriptDir "skills"

if (-not (Test-Path $SkillsSrc)) {
    Write-Error "Skills directory not found: $SkillsSrc"
    exit 1
}

$CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE ".codex" }

$Targets = @()
# Codex — install unconditionally.
$Targets += @{ Path = (Join-Path $CodexHome "skills"); Label = "Codex" }

# Check if symlinks are available (Developer Mode or admin)
$canSymlink = $false
$testLink = Join-Path $env:TEMP "skill_symlink_test_$PID"
try {
    New-Item -ItemType SymbolicLink -Path $testLink -Target $SkillsSrc -ErrorAction Stop | Out-Null
    Remove-Item $testLink -Force -ErrorAction SilentlyContinue
    $canSymlink = $true
} catch {
    $canSymlink = $false
}

foreach ($target in $Targets) {
    $dst = $target.Path
    $label = $target.Label
    if (-not (Test-Path $dst)) {
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
    }
    $installed = 0
    $skipped = 0
    foreach ($skillDir in Get-ChildItem -Path $SkillsSrc -Directory) {
        $t = Join-Path $dst $skillDir.Name
        if (Test-Path $t) {
            $item = Get-Item $t
            if ($item.LinkType -eq "SymbolicLink") {
                Remove-Item $t -Force
            } else {
                Write-Host "  [$label] SKIP $($skillDir.Name) (directory exists, not a symlink)"
                $skipped++
                continue
            }
        }
        if ($canSymlink) {
            New-Item -ItemType SymbolicLink -Path $t -Target $skillDir.FullName | Out-Null
        } else {
            Copy-Item -Path $skillDir.FullName -Destination $t -Recurse -Force
        }
        $installed++
    }
    Write-Host "[$label] Installed: $installed | Skipped: $skipped | Location: $dst"
}

Write-Host ""
Write-Host "Skills installed for Codex."
