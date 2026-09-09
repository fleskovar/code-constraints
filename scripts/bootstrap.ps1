# One-time setup: create venv, install Python deps, install + build frontend.
# Re-running is fast — each step is skipped when its inputs are unchanged
# (fingerprint stamps; see src/code_constraints/cli/depstamp.py). Pass -Force to reinstall all.

param([switch]$Force)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path ".venv")) {
    Write-Host "Creating .venv ..."
    python -m venv .venv
}

$py = Join-Path $repo ".venv\Scripts\python.exe"
$stampScript = Join-Path $repo "src\code_constraints\cli\depstamp.py"
function Dep-Changed($stamp, $inputs) {
    if ($Force) { return $true }
    & $py $stampScript check --base $repo --stamp $stamp @inputs
    return ($LASTEXITCODE -eq 0)
}
function Dep-Record($stamp, $inputs) {
    & $py $stampScript write --base $repo --stamp $stamp @inputs
}

$pyStamp = Join-Path $repo ".venv\.cdec-stamp-python"
$pyInputs = @((Join-Path $repo "pyproject.toml"))
if (Dep-Changed $pyStamp $pyInputs) {
    Write-Host "Installing Python deps ..."
    & $py -m pip install --upgrade pip
    & $py -m pip install -e ".[dev]"
    Dep-Record $pyStamp $pyInputs
} else {
    Write-Host "Python deps unchanged - skipping."
}

$fe = Join-Path $repo "frontend"
$depsStamp = Join-Path $fe "node_modules\.cdec-stamp-deps"
$depsInputs = @((Join-Path $fe "package.json"), (Join-Path $fe "package-lock.json"))
if (Dep-Changed $depsStamp $depsInputs) {
    Write-Host "Installing frontend deps ..."
    Push-Location frontend
    try { npm install } finally { Pop-Location }
    Dep-Record $depsStamp $depsInputs
} else {
    Write-Host "Frontend deps unchanged - skipping."
}

$buildInputs = @()
foreach ($f in @("src", "package.json", "package-lock.json", "vite.config.ts",
                 "svelte.config.js", "tsconfig.json", "tsconfig.app.json",
                 "tsconfig.node.json", "index.html")) {
    $p = Join-Path $fe $f
    if (Test-Path $p) { $buildInputs += $p }
}
$buildStamp = Join-Path $fe "dist\.cdec-stamp-build"
if (Dep-Changed $buildStamp $buildInputs) {
    Write-Host "Building frontend ..."
    Push-Location frontend
    try { npm run build } finally { Pop-Location }
    Dep-Record $buildStamp $buildInputs
} else {
    Write-Host "Frontend sources unchanged - skipping build."
}

Write-Host ""
Write-Host "Done. Next steps:"
Write-Host "  .\scripts\serve.ps1                    # start the web server"
Write-Host "  .\scripts\generate.ps1 <path> <lang>   # parse + render a codebase"
