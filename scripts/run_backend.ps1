$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
