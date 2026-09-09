<#
.SYNOPSIS
    Standalone installer / updater for code-constraints (Windows).

.DESCRIPTION
    From a clean machine this script will:
      1. Clone code-constraints from GitHub (main branch, HTTPS) using the existing git.
      2. Create and manage a dedicated Python virtualenv with all dependencies.
      3. Build the Svelte web frontend (Node 20+ required).
      4. Put the `cdec` CLI on the user PATH so it works system-wide.

    Re-running this script is the update path: it pulls the latest code, re-syncs
    dependencies (picking up any requirement changes), and rebuilds the frontend.
    It is fully idempotent and needs no administrator rights.

.PARAMETER InstallDir
    Where to clone + build. Default: $env:CDEC_HOME or %LOCALAPPDATA%\code-constraints.

.PARAMETER Repo
    Git clone URL. Default: $env:CDEC_REPO or the public HTTPS URL.

.PARAMETER Branch
    Branch to track. Default: $env:CDEC_BRANCH or "main".

.EXAMPLE
    # One-liner (download + run):
    irm https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.ps1 | iex

.EXAMPLE
    # From a checkout:
    .\install\install.ps1
#>

[CmdletBinding()]
param(
    [string]$InstallDir = $(if ($env:CDEC_HOME) { $env:CDEC_HOME } else { Join-Path $env:LOCALAPPDATA "code-constraints" }),
    [string]$Repo       = $(if ($env:CDEC_REPO) { $env:CDEC_REPO } else { "https://github.com/fleskovar/code_constraints.git" }),
    [string]$Branch     = $(if ($env:CDEC_BRANCH) { $env:CDEC_BRANCH } else { "main" }),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Info($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)    { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg)  { Write-Host "WARNING: $msg" -ForegroundColor Yellow }
function Die($msg)   { Write-Host "ERROR: $msg" -ForegroundColor Red; exit 1 }

# Skip-if-unchanged: a step runs only when its inputs differ from the recorded
# stamp (see src/code_constraints/cli/depstamp.py). -Force reinstalls regardless.
function Dep-Changed($py, $stamp, $inputs) {
    if ($Force) { return $true }
    $stampScript = Join-Path $repoDir "src\code_constraints\cli\depstamp.py"
    & $py $stampScript check --base $repoDir --stamp $stamp @inputs
    return ($LASTEXITCODE -eq 0)
}
function Dep-Record($py, $stamp, $inputs) {
    $stampScript = Join-Path $repoDir "src\code_constraints\cli\depstamp.py"
    & $py $stampScript write --base $repoDir --stamp $stamp @inputs
}

function Get-CommandPath($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source } else { return $null }
}

# --- 1. Preflight ----------------------------------------------------------
Info "Checking prerequisites"

if (-not (Get-CommandPath "git")) {
    Die "git is not installed or not on PATH. Install Git for Windows: https://git-scm.com/download/win"
}
Ok "git: $(git --version)"

# Python >= 3.11. Prefer `py -3` if present, else `python`.
# $pythonExe is the launcher; $pythonPre holds any leading args (splatted, so an
# empty array expands to nothing — avoids the `1..0` reverse-range slicing trap).
$pythonExe = $null
$pythonPre = @()
if (Get-CommandPath "py")         { $pythonExe = "py"; $pythonPre = @("-3") }
elseif (Get-CommandPath "python") { $pythonExe = "python" }
else { Die "Python is not installed or not on PATH. Install Python 3.11+: https://www.python.org/downloads/" }

$pyVer = & $pythonExe @pythonPre -c "import sys; print('%d.%d' % sys.version_info[:2])"
$pyParts = $pyVer.Split('.')
if ([int]$pyParts[0] -lt 3 -or ([int]$pyParts[0] -eq 3 -and [int]$pyParts[1] -lt 11)) {
    Die "Python 3.11+ required, found $pyVer. Install a newer Python: https://www.python.org/downloads/"
}
Ok "python: $pyVer"

if (-not (Get-CommandPath "node")) {
    Die "Node.js is not installed or not on PATH. Node 20+ is required to build the web frontend: https://nodejs.org/"
}
$nodeVer = (node --version).TrimStart('v')
$nodeMajor = [int]($nodeVer.Split('.')[0])
if ($nodeMajor -lt 20) {
    Die "Node 20+ required, found $nodeVer. Upgrade Node: https://nodejs.org/"
}
Ok "node: v$nodeVer"

if (-not (Get-CommandPath "npm")) {
    Die "npm is not installed or not on PATH (it normally ships with Node)."
}
Ok "npm: $(npm --version)"

$repoDir = Join-Path $InstallDir "repo"

# --- 2. Clone or update ----------------------------------------------------
if (Test-Path (Join-Path $repoDir ".git")) {
    Info "Updating existing checkout in $repoDir"
    git -C $repoDir fetch --prune origin $Branch
    git -C $repoDir checkout $Branch
    git -C $repoDir pull --ff-only origin $Branch
} else {
    Info "Cloning $Repo (branch $Branch) into $repoDir"
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    git clone --branch $Branch $Repo $repoDir
}
Ok "source ready"

# --- 3. Python venv + deps -------------------------------------------------
$venv = Join-Path $repoDir ".venv"
$venvPy = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPy)) {
    Info "Creating virtualenv at $venv"
    & $pythonExe @pythonPre -m venv $venv
} else {
    Info "Reusing virtualenv at $venv"
}

$pyStamp = Join-Path $venv ".cdec-stamp-python"
$pyInputs = @((Join-Path $repoDir "pyproject.toml"))
if (Dep-Changed $venvPy $pyStamp $pyInputs) {
    Info "Installing / updating Python dependencies"
    Push-Location $repoDir
    try {
        & $venvPy -m pip install --upgrade pip
        & $venvPy -m pip install -e ".[dev]"
    } finally {
        Pop-Location
    }
    Dep-Record $venvPy $pyStamp $pyInputs
    Ok "Python environment ready"
} else {
    Ok "Python dependencies unchanged - skipping pip install"
}

# --- 4. Frontend build -----------------------------------------------------
$fe = Join-Path $repoDir "frontend"
$depsStamp = Join-Path $fe "node_modules\.cdec-stamp-deps"
$depsInputs = @((Join-Path $fe "package.json"), (Join-Path $fe "package-lock.json"))
if (Dep-Changed $venvPy $depsStamp $depsInputs) {
    Info "Installing frontend dependencies"
    Push-Location $fe
    try { npm install } finally { Pop-Location }
    Dep-Record $venvPy $depsStamp $depsInputs
    Ok "frontend dependencies ready"
} else {
    Ok "frontend dependencies unchanged - skipping npm install"
}

# Build inputs: source tree + build configs (only those that exist).
$buildInputs = @()
foreach ($f in @("src", "package.json", "package-lock.json", "vite.config.ts",
                 "svelte.config.js", "tsconfig.json", "tsconfig.app.json",
                 "tsconfig.node.json", "index.html")) {
    $p = Join-Path $fe $f
    if (Test-Path $p) { $buildInputs += $p }
}
$buildStamp = Join-Path $fe "dist\.cdec-stamp-build"
if (Dep-Changed $venvPy $buildStamp $buildInputs) {
    Info "Building the web UI"
    Push-Location $fe
    try { npm run build } finally { Pop-Location }
    Dep-Record $venvPy $buildStamp $buildInputs
    Ok "frontend built"
} else {
    Ok "frontend sources unchanged - skipping npm run build"
}

# --- 5. Expose CLI on PATH (User scope, idempotent) ------------------------
$scriptsDir = Join-Path $venv "Scripts"
Info "Adding $scriptsDir to your User PATH"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($null -eq $userPath) { $userPath = "" }
$entries = $userPath.Split(';') | Where-Object { $_ -ne "" }
if ($entries -notcontains $scriptsDir) {
    $newPath = (@($scriptsDir) + $entries) -join ';'
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Ok "User PATH updated"
} else {
    Ok "already on User PATH"
}
# Make it work in the current session too.
if (($env:Path.Split(';')) -notcontains $scriptsDir) {
    $env:Path = "$scriptsDir;$env:Path"
}

# --- 6. Graphviz note (no auto-install) ------------------------------------
if (Get-CommandPath "dot") {
    Ok "Graphviz 'dot' found - rendering enabled"
} else {
    Warn "Graphviz 'dot' not found. 'cdec render' and sequence diagrams need it."
    Warn "Install from https://graphviz.org/download/ or set CDEC_DOT_BIN to the binary."
}

# --- 7. Done ---------------------------------------------------------------
Write-Host ""
Info "code-constraints is installed at $repoDir"
Write-Host ""
Write-Host "Open a NEW terminal (so PATH refreshes), then try:" -ForegroundColor White
Write-Host "    uml --help"
Write-Host "    cdec serve        # web viewer at http://127.0.0.1:8765"
Write-Host ""
Write-Host "To update later, just run this installer again." -ForegroundColor White
