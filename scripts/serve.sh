#!/usr/bin/env bash
# Start the FastAPI web server (serves the built Svelte SPA at the same port).
# Usage: ./scripts/serve.sh [--port 8765] [--host 127.0.0.1]
# Note: default is 8765 — port 8000 is commonly reserved on Windows (Hyper-V /
# http.sys exclusion ranges) and bind fails with WinError 10013.

set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

port=8765
host="127.0.0.1"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) port="$2"; shift 2 ;;
    --host) host="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -x .venv/Scripts/python.exe ]]; then
  py=".venv/Scripts/python.exe"
elif [[ -x .venv/bin/python ]]; then
  py=".venv/bin/python"
else
  echo "venv not found. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

if [[ ! -f frontend/dist/index.html ]]; then
  echo "warning: frontend/dist not built — UI will show a JSON placeholder. Run 'npm run build' in frontend/ to fix." >&2
fi

echo "Serving on http://${host}:${port}"
"$py" -m code_constraints.cli serve --host "$host" --port "$port"
