# Parse a codebase and render diagrams to SVG in one shot.
#
# Usage:
#   .\scripts\generate.ps1 <source-path> <lang> [-OutDir output] [-Diagrams class,package]
#
# Examples:
#   .\scripts\generate.ps1 tests\fixtures\python_demo python
#   .\scripts\generate.ps1 C:\projects\my-app csharp -OutDir diagrams
#   .\scripts\generate.ps1 .\src python -Diagrams class,package

param(
    [Parameter(Mandatory)] [string]$SourcePath,
    [Parameter(Mandatory)] [ValidateSet("python", "csharp")] [string]$Lang,
    [string]$OutDir = "out",
    [string[]]$Diagrams = @("class", "package")
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "venv not found. Run .\scripts\bootstrap.ps1 first."
}

if (-not (Test-Path $SourcePath)) {
    Write-Error "source path not found: $SourcePath"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$basename = (Get-Item $SourcePath).BaseName
$xmiPath = Join-Path $OutDir "$basename.xmi"

Write-Host "Parsing $SourcePath ($Lang) -> $xmiPath"
& $py -m code_constraints.cli parse $SourcePath --lang $Lang --out $xmiPath

# Project-wide diagrams
foreach ($d in $Diagrams) {
    if ($d -in @("class", "package")) {
        $svg = Join-Path $OutDir "$basename-$d.svg"
        Write-Host "Rendering $d -> $svg"
        & $py -m code_constraints.cli render $xmiPath --diagram $d -o $svg
    }
}

# Per-name diagrams: render every activity / sequence found in the XMI.
if ("activity" -in $Diagrams -or "sequence" -in $Diagrams) {
    $names = & $py -c @"
from code_constraints.core.xmi_reader import read_project
p = read_project(r'$xmiPath')
for a in p.activities: print('activity', a.name)
for s in p.sequences: print('sequence', s.name)
"@
    foreach ($line in $names) {
        $parts = $line -split " ", 2
        if ($parts.Count -ne 2) { continue }
        $kind, $name = $parts
        if ($kind -in $Diagrams) {
            $svg = Join-Path $OutDir "$basename-$kind-$name.svg"
            Write-Host "Rendering $kind '$name' -> $svg"
            & $py -m code_constraints.cli render $xmiPath --diagram $kind --name $name -o $svg
        }
    }
}

Write-Host ""
Write-Host "Done. Outputs in $OutDir\"
