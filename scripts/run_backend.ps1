param(
  [string]$HostAddress = "127.0.0.1",
  [int]$Port = 8000,
  [switch]$Reload
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
  throw "Python executable not found at $pythonExe"
}

$uvicornProcs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match "uvicorn\s+backend\.main:app" }

foreach ($proc in $uvicornProcs) {
  try {
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
  } catch {
    Write-Warning ("Could not stop process {0}: {1}" -f $proc.ProcessId, $PSItem.Exception.Message)
  }
}

Start-Sleep -Milliseconds 600

for ($attempt = 0; $attempt -lt 8; $attempt += 1) {
  $listenConn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if (-not $listenConn) {
    break
  }

$pidsToStop = @($listenConn | Select-Object -ExpandProperty OwningProcess -Unique)
  foreach ($pidToStop in $pidsToStop) {
    try {
      if (Get-Process -Id $pidToStop -ErrorAction SilentlyContinue) {
        Stop-Process -Id $pidToStop -Force -ErrorAction Stop
      }
    } catch {
      Write-Warning ("Could not stop process {0} on port {1}: {2}" -f $pidToStop, $Port, $PSItem.Exception.Message)
    }
  }

  Start-Sleep -Milliseconds 400
}

$finalListenConn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($finalListenConn) {
  throw "Port $Port is still busy after cleanup. Please close the owning process and retry."
}

$possibleTesseract = "C:\Program Files\Tesseract-OCR\tesseract.exe"
if (Test-Path $possibleTesseract) {
  $env:TESSERACT_CMD = $possibleTesseract
  if ($env:Path -notlike "*C:\Program Files\Tesseract-OCR*") {
    $env:Path = "C:\Program Files\Tesseract-OCR;" + $env:Path
  }
}

Set-Location $repoRoot
$launchParams = @("-m", "uvicorn", "backend.main:app", "--host", $HostAddress, "--port", "$Port")
if ($Reload.IsPresent) {
  $launchParams += "--reload"
}

Write-Host "Starting backend on http://$HostAddress`:$Port"
Write-Host "Single-instance mode: old backend processes terminated"

& $pythonExe @launchParams
