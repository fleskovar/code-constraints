#!/usr/bin/env bash
# One-time setup: create venv, install Python deps, install + build frontend.
# Re-running is fast — each step is skipped when its inputs are unchanged
# (fingerprint stamps; see src/code_constraints/cli/depstamp.py). CDEC_FORCE_INSTALL=1 reinstalls all.

set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

if [[ ! -d .venv ]]; then
  echo "Creating .venv ..."
  python -m venv .venv 2>/dev/null || python3 -m venv .venv
fi

# venv layout differs between platforms
if [[ -x .venv/Scripts/python.exe ]]; then
  py=".venv/Scripts/python.exe"
else
  py=".venv/bin/python"
fi

stamp_script="$repo/src/code_constraints/cli/depstamp.py"
dep_changed() {  # <stamp> <inputs...> -> 0 (run) / 1 (skip)
  [[ "${CDEC_FORCE_INSTALL:-}" == "1" ]] && return 0
  local stamp="$1"; shift
  "$py" "$stamp_script" check --base "$repo" --stamp "$stamp" "$@"
}
dep_record() {
  local stamp="$1"; shift
  "$py" "$stamp_script" write --base "$repo" --stamp "$stamp" "$@"
}

PY_STAMP=".venv/.cdec-stamp-python"
if dep_changed "$PY_STAMP" "pyproject.toml"; then
  echo "Installing Python deps ..."
  "$py" -m pip install --upgrade pip
  "$py" -m pip install -e ".[dev]"
  dep_record "$PY_STAMP" "pyproject.toml"
else
  echo "Python deps unchanged - skipping."
fi

DEPS_STAMP="frontend/node_modules/.cdec-stamp-deps"
if dep_changed "$DEPS_STAMP" "frontend/package.json" "frontend/package-lock.json"; then
  echo "Installing frontend deps ..."
  (cd frontend && npm install)
  dep_record "$DEPS_STAMP" "frontend/package.json" "frontend/package-lock.json"
else
  echo "Frontend deps unchanged - skipping."
fi

build_inputs=()
for f in frontend/src frontend/package.json frontend/package-lock.json \
         frontend/vite.config.ts frontend/svelte.config.js frontend/tsconfig.json \
         frontend/tsconfig.app.json frontend/tsconfig.node.json frontend/index.html; do
  [[ -e "$f" ]] && build_inputs+=("$f")
done
BUILD_STAMP="frontend/dist/.cdec-stamp-build"
if dep_changed "$BUILD_STAMP" "${build_inputs[@]}"; then
  echo "Building frontend ..."
  (cd frontend && npm run build)
  dep_record "$BUILD_STAMP" "${build_inputs[@]}"
else
  echo "Frontend sources unchanged - skipping build."
fi

cat <<EOF

Done. Next steps:
  ./scripts/serve.sh                    # start the web server
  ./scripts/generate.sh <path> <lang>   # parse + render a codebase
EOF
