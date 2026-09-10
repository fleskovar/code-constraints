# code-constraints (cdec) — development, build, and packaging entry points.
#
# Recipes run through `sh`. On Windows use Git Bash (or any shell that provides
# `sh` on PATH) so the venv-layout detection and the recipe bodies behave.
#
#   make setup     one-time development environment (venv + deps + frontend)
#   make test      run the test suite
#   make dist      build the wheel + sdist into dist/
#   make help      list every target
#
# Override the interpreter or venv location on the command line:
#   make setup BASE_PYTHON=python3.12 VENV=/tmp/cdec-venv

SHELL := /bin/sh
.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Layout / tool discovery
# ---------------------------------------------------------------------------

VENV ?= .venv

# Windows venvs put executables in Scripts/ and keep the .exe suffix.
ifeq ($(OS),Windows_NT)
  VENV_BIN    := $(VENV)/Scripts
  PY          := $(VENV_BIN)/python.exe
  BASE_PYTHON ?= python
else
  VENV_BIN    := $(VENV)/bin
  PY          := $(VENV_BIN)/python
  BASE_PYTHON ?= python3
endif

PIP  := $(PY) -m pip
CDEC := $(PY) -m code_constraints.cli

FRONTEND := frontend
NPM      ?= npm

# `serve` defaults. Port 8000 is administratively reserved by http.sys on some
# Windows machines, so the project default is 8765 (see CLAUDE.md).
HOST ?= 127.0.0.1
PORT ?= 8765

.PHONY: help venv setup dev install-dev install install-pipx uninstall \
        frontend-deps frontend-build frontend-check frontend clean-frontend \
        build dist package check-dist test test-cov lint format typecheck \
        verify test-cases test-case debug-case update-cases demo serve clean clean-venv distclean

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help: ## Show this help
	@echo "code-constraints (cdec) - make targets"
	@echo
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | sort \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "Variables: VENV=$(VENV) BASE_PYTHON=$(BASE_PYTHON) HOST=$(HOST) PORT=$(PORT)"

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

venv: ## Create the virtualenv if it does not exist
	@if [ ! -x "$(PY)" ]; then \
	  echo ">> creating virtualenv at $(VENV)"; \
	  $(BASE_PYTHON) -m venv "$(VENV)"; \
	else \
	  echo ">> virtualenv already present at $(VENV)"; \
	fi

setup: venv install-dev frontend ## One-time dev environment: venv + editable install + frontend build
	@echo
	@echo "Ready. Next:"
	@echo "  make serve      # http://$(HOST):$(PORT)"
	@echo "  make test"
	@echo "  make demo"

dev: setup ## Alias for `setup`

install-dev: venv ## Editable install with dev extras (the development version)
	@echo ">> installing code-constraints (editable, dev + mcp extras)"
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev,mcp]"
	@echo ">> cdec available as: $(VENV_BIN)/cdec"
	@echo ">> MCP server available as: $(VENV_BIN)/cdec-mcp"

install: venv ## Install from source into the venv (non-editable)
	@echo ">> installing code-constraints from source (non-editable)"
	$(PIP) install --upgrade pip
	$(PIP) install .
	@echo ">> cdec available as: $(VENV_BIN)/cdec"

install-pipx: ## Install the cdec CLI + MCP server globally from this checkout via pipx
	@command -v pipx >/dev/null 2>&1 || { echo "pipx not found — see https://pipx.pypa.io"; exit 1; }
	pipx install --force ".[mcp]"
	@echo ">> cdec installed globally; run: cdec --help"
	@echo ">> cdec-mcp on PATH too, so a harness .mcp.json can just say \"command\": \"cdec-mcp\""

uninstall: ## Remove code-constraints from the venv
	-$(PIP) uninstall -y code-constraints

# ---------------------------------------------------------------------------
# Frontend (Svelte 5 + Vite)
# ---------------------------------------------------------------------------

frontend-deps: ## npm install for the frontend
	@echo ">> installing frontend deps"
	cd $(FRONTEND) && $(NPM) install

frontend-build: ## Build the Svelte SPA into frontend/dist
	@echo ">> building frontend"
	cd $(FRONTEND) && $(NPM) run build

frontend-check: ## Run svelte-check
	cd $(FRONTEND) && $(NPM) run check

frontend: frontend-deps frontend-build ## Install frontend deps and build the SPA

clean-frontend: ## Remove frontend build output
	rm -rf $(FRONTEND)/dist

# ---------------------------------------------------------------------------
# Build / package
# ---------------------------------------------------------------------------

build: dist ## Alias for `dist`

dist: clean-dist frontend-build ## Build the wheel + sdist into dist/
	@echo ">> building distributable"
	$(PY) -m build
	@echo
	@ls -l dist
	@echo
	@echo "NOTE: the wheel ships the Python packages, the rule shims, and the"
	@echo "      Claude assets — but NOT frontend/dist. An installed wheel serves"
	@echo "      the API and a JSON placeholder at /, not the SPA."

package: dist ## Alias for `dist`

check-dist: dist ## Build, then validate the artifacts with twine
	@$(PIP) install --quiet twine
	$(PY) -m twine check dist/*

clean-dist:
	rm -rf dist build *.egg-info src/*.egg-info

# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

test: ## Run the test suite
	$(PY) -m pytest

test-cov: ## Run the test suite with a coverage report
	$(PY) -m pytest --cov=code_constraints --cov-report=term-missing

lint: ## Lint with ruff
	$(PY) -m ruff check src tests

format: ## Auto-fix lint findings with ruff
	$(PY) -m ruff check --fix src tests

typecheck: ## Type-check with mypy
	$(PY) -m mypy src

verify: lint typecheck test ## Run lint + typecheck + tests

test-cases: ## Run every human-readable case folder under tests/cases/
	$(PY) -m pytest tests/test_case_folders.py

test-case: ## Run one case folder: make test-case CASE=check/subclass-naming/python
	$(PY) -m pytest "tests/test_case_folders.py::test_case[$(CASE)]"

debug-case: ## Debug one case folder under pdb: make debug-case CASE=...
	$(PY) -m pytest "tests/test_case_folders.py::test_case[$(CASE)]" --pdb -s

update-cases: ## Regenerate every case baseline from current behaviour (REVIEW THE DIFF)
	UPDATE_BASELINES=1 $(PY) -m pytest tests/test_case_folders.py

# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------

serve: ## Start the web server (HOST/PORT overridable)
	@if [ ! -f "$(FRONTEND)/dist/index.html" ]; then \
	  echo "warning: $(FRONTEND)/dist not built — run 'make frontend-build'"; \
	fi
	$(CDEC) serve --host $(HOST) --port $(PORT)

# Every language with rule-tag support ships a demo with the same shape: a
# tagged billing slice, a committed lock, and one seeded conformance violation.
# See docs/languages/ for a guide per language.
DEMO_LANGS := python csharp odin lua julia

demo: ## Run `cdec check` against the bundled example projects
	@echo "Every rule in .cdec/rules.yaml runs in one command, so this is the"
	@echo "whole gate: architectural rules, tag conformance, locks and the"
	@echo "reference check together."
	@echo "(each demo carries one seeded violation - non-zero exit is expected)"
	@echo
	@for lang in $(DEMO_LANGS); do \
	  echo "--- $$lang"; \
	  $(CDEC) check --config examples/$${lang}_demo/.cdec --source examples/$${lang}_demo || true; \
	  echo; \
	done

# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------

clean: clean-dist ## Remove build artifacts and caches (keeps the venv)
	rm -rf .pytest_cache .ruff_cache .mypy_cache .cdec_cache htmlcov .coverage
	find . -type d -name __pycache__ -not -path "./$(VENV)/*" -not -path "./$(FRONTEND)/node_modules/*" -exec rm -rf {} + 2>/dev/null || true

clean-venv: ## Delete the virtualenv
	rm -rf $(VENV)

distclean: clean clean-frontend clean-venv ## Remove everything generated, including node_modules
	rm -rf $(FRONTEND)/node_modules
