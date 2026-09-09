#!/usr/bin/env bash
# Parse a codebase and render diagrams to SVG in one shot.
#
# Usage:
#   ./scripts/generate.sh <source-path> <lang> [--out-dir DIR] [--diagrams class,package,activity,sequence]
#
# Examples:
#   ./scripts/generate.sh tests/fixtures/python_demo python
#   ./scripts/generate.sh ~/projects/my-app csharp --out-dir diagrams
#   ./scripts/generate.sh ./src python --diagrams class,package,activity

set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

if [[ $# -lt 2 ]]; then
  sed -n '2,12p' "${BASH_SOURCE[0]}" >&2
  exit 1
fi

source_path="$1"
lang="$2"
shift 2

out_dir="out"
diagrams="class,package"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)   out_dir="$2"; shift 2 ;;
    --diagrams)  diagrams="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

case "$lang" in
  python|csharp) ;;
  *) echo "lang must be 'python' or 'csharp', got: $lang" >&2; exit 1 ;;
esac

if [[ ! -e $source_path ]]; then
  echo "source path not found: $source_path" >&2
  exit 1
fi

if [[ -x .venv/Scripts/python.exe ]]; then
  py=".venv/Scripts/python.exe"
elif [[ -x .venv/bin/python ]]; then
  py=".venv/bin/python"
else
  echo "venv not found. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

mkdir -p "$out_dir"
basename="$(basename "$source_path")"
basename="${basename%.*}"
xmi_path="$out_dir/$basename.xmi"

echo "Parsing $source_path ($lang) -> $xmi_path"
"$py" -m code_constraints.cli parse "$source_path" --lang "$lang" --out "$xmi_path"

IFS=',' read -ra wanted <<< "$diagrams"

# Project-wide diagrams
for d in "${wanted[@]}"; do
  if [[ "$d" == "class" || "$d" == "package" ]]; then
    svg="$out_dir/$basename-$d.svg"
    echo "Rendering $d -> $svg"
    "$py" -m code_constraints.cli render "$xmi_path" --diagram "$d" -o "$svg"
  fi
done

# Per-name diagrams: enumerate activities / sequences from the XMI.
want_activity=0; want_sequence=0
for d in "${wanted[@]}"; do
  [[ "$d" == "activity" ]] && want_activity=1
  [[ "$d" == "sequence" ]] && want_sequence=1
done

if [[ $want_activity -eq 1 || $want_sequence -eq 1 ]]; then
  while IFS=' ' read -r kind name; do
    [[ -z "${kind:-}" ]] && continue
    if { [[ "$kind" == "activity" && $want_activity -eq 1 ]]; } || \
       { [[ "$kind" == "sequence" && $want_sequence -eq 1 ]]; }; then
      svg="$out_dir/$basename-$kind-$name.svg"
      echo "Rendering $kind '$name' -> $svg"
      "$py" -m code_constraints.cli render "$xmi_path" --diagram "$kind" --name "$name" -o "$svg"
    fi
  done < <("$py" -c "
from code_constraints.core.xmi_reader import read_project
p = read_project(r'$xmi_path')
for a in p.activities: print('activity', a.name)
for s in p.sequences: print('sequence', s.name)
")
fi

echo
echo "Done. Outputs in $out_dir/"
