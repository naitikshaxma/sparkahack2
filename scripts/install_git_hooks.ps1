$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

git config core.hooksPath .githooks
Write-Host "Configured core.hooksPath=.githooks"

if (Test-Path ".githooks\pre-commit") {
  Write-Host "Pre-commit hook is ready."
} else {
  throw "Missing .githooks\pre-commit"
}
