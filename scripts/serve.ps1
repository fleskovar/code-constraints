# Start the FastAPI web server (serves the built Svelte SPA at the same port).
# Usage: .\scripts\serve.ps1 [-Port 8765] [-ServerHost 127.0.0.1]
# Note: default is 8765 — port 8000 is commonly reserved on Windows (Hyper-V /
# http.sys exclusion ranges) and bind fails with WinError 10013.

param(
    [int]$Port = 8765,
    [string]$ServerHost = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "venv not found. Run .\scripts\bootstrap.ps1 first."
}

if (-not (Test-Path "frontend\dist\index.html")) {
    Write-Warning "frontend\dist not built — the UI will show a JSON placeholder. Run 'npm run build' in frontend/ to fix."
}

Write-Host "Serving on http://${ServerHost}:${Port}"
& $py -m code_constraints.cli serve --host $ServerHost --port $Port
