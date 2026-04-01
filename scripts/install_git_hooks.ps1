Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$hookPath = Join-Path $repoRoot ".githooks/pre-commit"

if (-not (Test-Path $hookPath)) {
    throw "Missing hook file: $hookPath"
}

Push-Location $repoRoot
try {
    $gitCmd = Get-Command git -ErrorAction Stop
    & $gitCmd.Source config core.hooksPath ".githooks"

    try {
        & $gitCmd.Source update-index --chmod=+x .githooks/pre-commit | Out-Null
    }
    catch {
        # This is best-effort on Windows filesystems.
    }

    Write-Host "Git hooks installed. core.hooksPath=.githooks"
    Write-Host "Pre-commit will now block commits when lint or tests fail."
}
finally {
    Pop-Location
}
