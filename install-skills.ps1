# Install 1C skills for Claude Code (Windows)
# Creates symlinks from ~/.claude/skills/ to the project's skills/ directory
# Usage: powershell -ExecutionPolicy Bypass -File install-skills.ps1
# Note: Requires Administrator privileges for symlinks on Windows

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillsSrc = Join-Path $ScriptDir "skills"
$SkillsDst = Join-Path $env:USERPROFILE ".claude\skills"

if (-not (Test-Path $SkillsSrc)) {
    Write-Error "Skills directory not found: $SkillsSrc"
    exit 1
}

if (-not (Test-Path $SkillsDst)) {
    New-Item -ItemType Directory -Path $SkillsDst -Force | Out-Null
}

$installed = 0
$skipped = 0

foreach ($skillDir in Get-ChildItem -Path $SkillsSrc -Directory) {
    $target = Join-Path $SkillsDst $skillDir.Name

    if (Test-Path $target) {
        if ((Get-Item $target).LinkType -eq "SymbolicLink") {
            Remove-Item $target -Force
            New-Item -ItemType SymbolicLink -Path $target -Target $skillDir.FullName | Out-Null
            $installed++
        } else {
            Write-Host "  SKIP $($skillDir.Name) (directory exists, not a symlink)"
            $skipped++
        }
    } else {
        New-Item -ItemType SymbolicLink -Path $target -Target $skillDir.FullName | Out-Null
        $installed++
    }
}

Write-Host ""
Write-Host "Installed: $installed skills"
Write-Host "Skipped:   $skipped skills"
Write-Host "Location:  $SkillsDst"
Write-Host ""
Write-Host "Skills are now available in Claude Code via /command (e.g. /meta-compile, /epf-init)"
