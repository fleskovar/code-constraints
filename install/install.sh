#!/usr/bin/env bash
#
# Standalone installer / updater for code-constraints (Linux / macOS).
#
# From a clean machine this script will:
#   1. Clone code-constraints from GitHub (main branch, HTTPS) using the existing git.
#   2. Create and manage a dedicated Python virtualenv with all dependencies.
#   3. Build the Svelte web frontend (Node 20+ required).
#   4. Put the `cdec` CLI on PATH so it works system-wide.
#
# Re-running this script is the update path: it pulls the latest code, re-syncs
# dependencies (picking up any requirement changes), and rebuilds the frontend.
# It is fully idempotent and needs no root.
#
# Configuration (environment variables, all optional):
#   CDEC_HOME    install dir          (default: ~/.code-constraints)
#   CDEC_REPO    git clone URL        (default: public HTTPS URL)
#   CDEC_BRANCH  branch to track      (default: main)
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.sh | bash

set -euo pipefail

INSTALL_DIR="${CDEC_HOME:-$HOME/.code-constraints}"
REPO_URL="${CDEC_REPO:-https://github.com/fleskovar/code_constraints.git}"
BRANCH="${CDEC_BRANCH:-main}"

# --- pretty output ---------------------------------------------------------
if [[ -t 1 ]]; then
  C_INFO=$'\033[36m'; C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_OFF=$'\033[0m'
else
  C_INFO=""; C_OK=""; C_WARN=""; C_ERR=""; C_OFF=""
fi
info() { printf '%s==> %s%s\n' "$C_INFO" "$1" "$C_OFF"; }
ok()   { printf '    %s%s%s\n' "$C_OK" "$1" "$C_OFF"; }
warn() { printf '%sWARNING: %s%s\n' "$C_WARN" "$1" "$C_OFF" >&2; }
die()  { printf '%sERROR: %s%s\n' "$C_ERR" "$1" "$C_OFF" >&2; exit 1; }

# Skip-if-unchanged: a step runs only when its inputs differ from the recorded
# stamp (see src/code_constraints/cli/depstamp.py). CDEC_FORCE_INSTALL=1 reinstalls regardless.
# `dep_changed <python> <stamp> <inputs...>` -> 0 (run) / 1 (skip).
dep_changed() {
  [[ "${CDEC_FORCE_INSTALL:-}" == "1" ]] && return 0
  local py="$1"; local stamp="$2"; shift 2
  "$py" "$REPO_DIR/src/code_constraints/cli/depstamp.py" check --base "$REPO_DIR" --stamp "$stamp" "$@"
}
dep_record() {
  local py="$1"; local stamp="$2"; shift 2
  "$py" "$REPO_DIR/src/code_constraints/cli/depstamp.py" write --base "$REPO_DIR" --stamp "$stamp" "$@"
}

# --- 1. Preflight ----------------------------------------------------------
info "Checking prerequisites"

command -v git >/dev/null 2>&1 || die "git is not installed or not on PATH. Install it via your package manager."
ok "git: $(git --version)"

# Python >= 3.11. Prefer python3, fall back to python.
PYTHON=""
if command -v python3 >/dev/null 2>&1; then PYTHON="python3"
elif command -v python >/dev/null 2>&1; then PYTHON="python"
else die "Python is not installed or not on PATH. Install Python 3.11+."; fi

PY_VER="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VER%%.*}"; PY_MINOR="${PY_VER##*.}"
if (( PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11) )); then
  die "Python 3.11+ required, found $PY_VER. Install a newer Python."
fi
ok "python: $PY_VER"

command -v node >/dev/null 2>&1 || die "Node.js is not installed or not on PATH. Node 20+ is required to build the web frontend: https://nodejs.org/"
NODE_VER="$(node --version)"; NODE_VER="${NODE_VER#v}"
NODE_MAJOR="${NODE_VER%%.*}"
if (( NODE_MAJOR < 20 )); then
  die "Node 20+ required, found $NODE_VER. Upgrade Node: https://nodejs.org/"
fi
ok "node: v$NODE_VER"

command -v npm >/dev/null 2>&1 || die "npm is not installed or not on PATH (it normally ships with Node)."
ok "npm: $(npm --version)"

REPO_DIR="$INSTALL_DIR/repo"

# --- 2. Clone or update ----------------------------------------------------
if [[ -d "$REPO_DIR/.git" ]]; then
  info "Updating existing checkout in $REPO_DIR"
  git -C "$REPO_DIR" fetch --prune origin "$BRANCH"
  git -C "$REPO_DIR" checkout "$BRANCH"
  git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
else
  info "Cloning $REPO_URL (branch $BRANCH) into $REPO_DIR"
  mkdir -p "$INSTALL_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi
ok "source ready"

# --- 3. Python venv + deps -------------------------------------------------
VENV="$REPO_DIR/.venv"
VENV_PY="$VENV/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  info "Creating virtualenv at $VENV"
  "$PYTHON" -m venv "$VENV"
else
  info "Reusing virtualenv at $VENV"
fi

PY_STAMP="$VENV/.cdec-stamp-python"
if dep_changed "$VENV_PY" "$PY_STAMP" "$REPO_DIR/pyproject.toml"; then
  info "Installing / updating Python dependencies"
  (
    cd "$REPO_DIR"
    "$VENV_PY" -m pip install --upgrade pip
    "$VENV_PY" -m pip install -e ".[dev]"
  )
  dep_record "$VENV_PY" "$PY_STAMP" "$REPO_DIR/pyproject.toml"
  ok "Python environment ready"
else
  ok "Python dependencies unchanged - skipping pip install"
fi

# --- 4. Frontend build -----------------------------------------------------
FE="$REPO_DIR/frontend"
DEPS_STAMP="$FE/node_modules/.cdec-stamp-deps"
if dep_changed "$VENV_PY" "$DEPS_STAMP" "$FE/package.json" "$FE/package-lock.json"; then
  info "Installing frontend dependencies"
  (cd "$FE" && npm install)
  dep_record "$VENV_PY" "$DEPS_STAMP" "$FE/package.json" "$FE/package-lock.json"
  ok "frontend dependencies ready"
else
  ok "frontend dependencies unchanged - skipping npm install"
fi

# Build inputs: source tree + build configs (only those that exist).
BUILD_INPUTS=()
for f in src package.json package-lock.json vite.config.ts svelte.config.js \
         tsconfig.json tsconfig.app.json tsconfig.node.json index.html; do
  [[ -e "$FE/$f" ]] && BUILD_INPUTS+=("$FE/$f")
done
BUILD_STAMP="$FE/dist/.cdec-stamp-build"
if dep_changed "$VENV_PY" "$BUILD_STAMP" "${BUILD_INPUTS[@]}"; then
  info "Building the web UI"
  (cd "$FE" && npm run build)
  dep_record "$VENV_PY" "$BUILD_STAMP" "${BUILD_INPUTS[@]}"
  ok "frontend built"
else
  ok "frontend sources unchanged - skipping npm run build"
fi

# --- 5. Expose CLI on PATH (idempotent) ------------------------------------
# Symlink the entry point into ~/.local/bin (XDG user-bin convention).
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$VENV/bin/cdec" "$BIN_DIR/cdec"
ok "linked $BIN_DIR/cdec -> $VENV/bin/cdec"

# Ensure ~/.local/bin is on PATH; if not, append to the user's shell rc files.
case ":$PATH:" in
  *":$BIN_DIR:"*)
    ok "$BIN_DIR already on PATH"
    ;;
  *)
    info "Adding $BIN_DIR to PATH in your shell startup files"
    MARKER="# added by code-constraints installer"
    LINE="export PATH=\"\$HOME/.local/bin:\$PATH\"  $MARKER"
    for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
      if [[ -f "$rc" ]] || [[ "$rc" == "$HOME/.profile" ]]; then
        if ! grep -qF "$MARKER" "$rc" 2>/dev/null; then
          printf '\n%s\n' "$LINE" >> "$rc"
          ok "updated $rc"
        fi
      fi
    done
    warn "Open a new shell or run:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

# --- 6. Graphviz note (no auto-install) ------------------------------------
if command -v dot >/dev/null 2>&1; then
  ok "Graphviz 'dot' found — rendering enabled"
else
  warn "Graphviz 'dot' not found. 'cdec render' and sequence diagrams need it."
  warn "Install via your package manager (e.g. 'apt install graphviz' / 'brew install graphviz') or set CDEC_DOT_BIN."
fi

# --- 7. Done ---------------------------------------------------------------
echo
info "code-constraints is installed at $REPO_DIR"
echo
echo "Try:"
echo "    uml --help"
echo "    cdec serve        # web viewer at http://127.0.0.1:8765"
echo
echo "To update later, just run this installer again."
