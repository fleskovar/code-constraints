"""Reusable, non-interactive scaffolding primitives.

Shared by the `cdec init` subcommand and the interactive session
(`code_constraints.cli.interactive`). Everything here is pure file I/O + asset resolution —
no prompting, no `typer.Exit`. Callers decide how to surface results.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from code_constraints.core.model import SUPPORTED_LANGUAGES
from code_constraints.lint.config import (
    BASELINE_FILENAME,
    CONFIG_FILENAME,
    REFERENCE_FILENAME,
    RULES_FILENAME,
)

SUPPORTED_LANGS = SUPPORTED_LANGUAGES

# Where a copied shim lands in the target project, by language. The file name
# matches the convention in examples/python_demo/cdec_rules.py — the shim sits at
# the project root so tagged code can `from cdec_rules import …` /
# `using CodeConstraints.Rules;`.
_SHIM_TARGETS = {
    "python": ("shims/python/cdec_rules.py", "cdec_rules.py"),
    "csharp": ("shims/csharp/CodeConstraintsRules.cs", "CodeConstraintsRules.cs"),
    "julia": ("shims/julia/CdecRules.jl", "CdecRules.jl"),
    # Lua and Odin carry tags in `@cdec` annotation comments rather than in a
    # language construct, so their shims are vocabulary references plus runtime
    # no-ops. They are still copied, so the tag list lives in the project.
    "lua": ("shims/lua/cdec_rules.lua", "cdec_rules.lua"),
    "odin": ("shims/odin/cdec_rules.odin", "cdec_rules.odin"),
    # typescript / svelte have no shims yet.
}

# Claude assets deployed into target projects: agents plus the architecture-loop
# skill (the propose → review → lock workflow). Destinations mirror the repo-
# relative paths, so entries here land at the same spot in the user's project.
_AGENT_RELS = [
    ".claude/agents/cdec-architect.md",
    ".claude/agents/oop-refactor-architect.md",
    ".claude/skills/cdec-architecture-loop/SKILL.md",
]


class ScaffoldError(RuntimeError):
    """Raised when an asset can't be located or a target already exists."""


# ---------- asset resolution ----------

def _repo_root() -> Path | None:
    """Walk up from this file looking for the harness repo root (the dir that
    holds both `pyproject.toml` and `shims/`). Present in editable installs."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "shims").is_dir():
            return parent
    return None


def _asset(rel: str) -> Path:
    """Resolve a bundled asset by its repo-relative path (e.g.
    "shims/python/cdec_rules.py" or ".claude/agents/cdec-architect.md").

    Prefers the repo-relative source-of-truth file (editable installs); falls
    back to the packaged copy under `code_constraints/cli/_assets/…` (installed wheels, where
    `force-include` maps the repo files in). Raises ScaffoldError if missing.
    """
    root = _repo_root()
    if root is not None:
        candidate = root / rel
        if candidate.is_file():
            return candidate

    # Installed wheel: assets are flattened under code_constraints/cli/_assets/.
    #   shims/python/cdec_rules.py        -> _assets/shims/python/cdec_rules.py
    #   .claude/agents/cdec-architect.md  -> _assets/agents/cdec-architect.md
    #   .claude/skills/<name>/SKILL.md   -> _assets/skills/<name>/SKILL.md
    packaged_rel = rel
    if rel.startswith(".claude/agents/"):
        packaged_rel = "agents/" + rel.split("/")[-1]
    elif rel.startswith(".claude/skills/"):
        packaged_rel = rel.removeprefix(".claude/")
    try:
        base = importlib.resources.files("code_constraints.cli") / "_assets"
        candidate = Path(str(base / packaged_rel))
        if candidate.is_file():
            return candidate
    except (ModuleNotFoundError, FileNotFoundError):
        pass

    raise ScaffoldError(f"could not locate bundled asset: {rel}")


# ---------- .cdec/ scaffolding ----------

def init_cdec_config(
    config_dir: Path, lang: str, source: Path, force: bool
) -> list[Path]:
    """Scaffold a `.cdec/` folder (config, rules, baseline, README, .gitignore)
    and snapshot a reference XMI from `source`. Returns the files written.

    Raises ScaffoldError on an unsupported language, or if a target file exists
    and `force` is False.
    """
    if lang not in SUPPORTED_LANGS:
        raise ScaffoldError(f"unsupported language: {lang}")

    config_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files = [
        (config_dir / CONFIG_FILENAME, _CONFIG_TEMPLATE.format(lang=lang, source=_posix(source))),
        (config_dir / RULES_FILENAME, _RULES_TEMPLATE),
        (config_dir / BASELINE_FILENAME, "violations: {}\n"),
        (config_dir / "README.md", _README_TEMPLATE),
    ]
    for path, content in files:
        if path.exists() and not force:
            raise ScaffoldError(f"refusing to overwrite {path} (use force)")
        path.write_text(content, encoding="utf-8")
        written.append(path)

    gitignore = config_dir / ".gitignore"
    gitignore.write_text("cache/\n", encoding="utf-8")
    written.append(gitignore)

    # Snapshot a reference XMI so the first `cdec check` works.
    reference_path = config_dir / REFERENCE_FILENAME
    if source.exists():
        from code_constraints.core.xmi_writer import write_project

        project = _parse_project(source, lang)
        write_project(project, reference_path)
        written.append(reference_path)

    return written


# ---------- copy helpers ----------

def copy_agents(project_root: Path, force: bool = False) -> list[Path]:
    """Copy all code-constraints Claude agents into <project>/.claude/agents/.
    Returns the destination paths written. Raises ScaffoldError if any target
    exists and `force` is False."""
    written: list[Path] = []
    for rel in _AGENT_RELS:
        src = _asset(rel)
        dest = project_root / rel
        if dest.exists() and not force:
            raise ScaffoldError(f"refusing to overwrite {dest} (use --force)")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(dest)
    return written


def copy_architect_agent(project_root: Path, force: bool = False) -> Path:
    """Compatibility shim — copies all agents and returns the first path."""
    return copy_agents(project_root, force=force)[0]


def copy_shims(project_root: Path, lang: str, force: bool = False) -> list[Path]:
    """Copy the language shim into the project root. Returns the destinations
    written (empty list when the language has no shim). Raises ScaffoldError if a
    target exists and `force` is False."""
    entry = _SHIM_TARGETS.get(lang)
    if entry is None:
        return []
    src_rel, dest_name = entry
    src = _asset(src_rel)
    dest = project_root / dest_name
    if dest.exists() and not force:
        raise ScaffoldError(f"refusing to overwrite {dest} (use force)")
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return [dest]


def has_shim(lang: str) -> bool:
    return lang in _SHIM_TARGETS


# ---------- CI/CD script generation ----------

def write_ci_scripts(project_root: Path, lang: str, source: Path) -> list[Path]:
    """Write `cdec-ci.bat` (Windows) and `cdec-ci.sh` (bash) into the project root.
    Both run `cdec check` then `cdec enforce` and propagate non-zero exits."""
    src = _posix(source)
    bat = project_root / "cdec-ci.bat"
    sh = project_root / "cdec-ci.sh"
    bat.write_text(_CI_BAT_TEMPLATE.format(lang=lang, source=src), encoding="utf-8")
    sh.write_text(_CI_SH_TEMPLATE.format(lang=lang, source=src), encoding="utf-8")
    return [bat, sh]


# ---------- shared internals ----------

def _parse_project(path: Path, lang: str):
    if lang == "python":
        from code_constraints.python import parse_project

        return parse_project(path)
    if lang == "csharp":
        from code_constraints.csharp import parse_project

        return parse_project(path)
    if lang == "typescript":
        from code_constraints.typescript import parse_project

        return parse_project(path)
    if lang == "svelte":
        from code_constraints.svelte import parse_project

        return parse_project(path)
    if lang == "odin":
        from code_constraints.odin import parse_project

        return parse_project(path)
    if lang == "lua":
        from code_constraints.lua import parse_project

        return parse_project(path)
    if lang == "julia":
        from code_constraints.julia import parse_project

        return parse_project(path)
    raise ScaffoldError(f"unsupported language: {lang}")


def _posix(p: Path) -> str:
    return str(p).replace("\\", "/")


_CONFIG_TEMPLATE = """\
# Project-level settings for `cdec check`.
language: {lang}                # python | csharp | typescript | svelte | odin | lua | julia
source: {source}                 # parsed by `cdec check` (relative to project root)
baseline:
  reference: .cdec/reference.xmi # default baseline XMI; null to require --base-ref
output:
  json: null                     # optional default for --json-out
  log: null                      # optional default for --log-out

# Implementation locks (`cdec lock`, Engine C). A locked class/function may not
# change at all: its normalised AST is digested into .cdec/locks.yaml, so moving
# or reformatting code never trips a lock but any semantic edit does.
lock:
  enabled: true                  # run lock verification as part of `cdec check`
  include_docstrings: false      # count docstrings / /// comments as implementation
  targets: []                    # qualified-name globs locked WITHOUT a tag,
                                 # e.g. ["tests.**"] to freeze all test logic
"""

_RULES_TEMPLATE = """\
# Architectural-lint rules. Each entry has:
#   id        — stable identifier, referenced in baseline.yaml
#   type      — rule implementation (see list below)
#   scope     — diff | snapshot (default depends on rule)
#   severity  — error | warning | off
#   message   — optional explanation printed when the rule fires; supports
#               {placeholders} and YAML block scalars (`message: |` for
#               multi-line). Use this to tell developers WHY the rule exists
#               and HOW to fix it, not just that it failed.
#   ignore    — list of qualified-name globs to exempt
#
# Available placeholders by rule type:
#   no-new-classes / no-removed-classes / dangling-classes / max-class-fanout:
#     {qualified_name}              (max-class-fanout adds {fanout}, {limit})
#   frozen-members:
#     {qualified_name}, {member}, {kind}, {action}
#   forbidden-references / forbidden-package-references:
#     {qualified_name}, {source}, {target}
#   subclass-naming:
#     {qualified_name}, {name}, {base}, {pattern}
#   no-cyclic-package-dependencies:
#     {cycle}
#   frozen-rules:
#     {qualified_name}, {rule}, {member}, {action}
#   layer-dependencies:
#     {qualified_name}, {source}, {target}, {source_layer}, {target_layer}
#
# Known types:
#   no-new-classes, no-removed-classes, dangling-classes, frozen-members,
#   frozen-rules, forbidden-references, forbidden-package-references,
#   layer-dependencies, subclass-naming, no-cyclic-package-dependencies,
#   max-class-fanout
#
# frozen-rules (scope: diff) freezes the architectural-rule tags
# (@no_instantiation, @sealed, @layer, …) recorded in the baseline: removing or
# weakening a tag fails the check. It never inspects method bodies — that's the
# job of the separate `cdec enforce` command.
#
# layer-dependencies (scope: snapshot) reads @layer("name") tags and an
# allowed-direction matrix and flags forbidden cross-layer references.

rules: []

# Examples (uncomment and adapt):
#
# - id: no-new-classes
#   type: no-new-classes
#   severity: error
#   ignore:
#     - "tests.**"
#
# - id: factories-must-end-in-Factory
#   type: subclass-naming
#   severity: error
#   base: "IFactory"
#   name_pattern: ".*Factory$"
#
# - id: domain-must-not-depend-on-ui
#   type: forbidden-package-references
#   severity: error
#   from: ["myapp.domain.**"]
#   to:   ["myapp.ui.**"]
#
# - id: lock-public-api
#   type: frozen-members
#   severity: error
#   classes: ["myapp.api.**"]
#
# - id: no-cycles
#   type: no-cyclic-package-dependencies
#   severity: warning
#
# - id: freeze-architectural-tags
#   type: frozen-rules
#   severity: error
#   classes: ["myapp.**"]
#
# - id: layering
#   type: layer-dependencies
#   severity: error
#   allow:
#     ui:     [domain]
#     domain: [data]
#     data:   []
"""

_README_TEMPLATE = """\
# `.cdec/` — architectural-lint configuration

`cdec check` reads this folder. Files:

- `config.yaml` — project settings (language, source path, default baseline)
- `rules.yaml` — rule definitions
- `reference.xmi` — committed reference snapshot; regenerated with
  `cdec check --update-reference`
- `baseline.yaml` — accepted violations, each with the reason it was accepted;
  written by `cdec baseline allow` / `cdec baseline patch`, or wholesale with
  `cdec check --update-baseline`
- `locks.yaml` — approved implementation digests for `@locked` elements;
  written by `cdec lock set`
- `cache/` — transient parse artefacts (gitignored)

Every rule type usable in `rules.yaml`, and every source tag (`@sealed`,
`@immutable`, `@factory`, `@layer`, `@locked`, …), is documented with options and
worked pass/fail examples in `docs/RULES_CATALOGUE.md` in the code-constraints
repository.

## Accepting a violation

Every issue prints a stable key (`V-` drift, `F-` conformance, `L-` lock). Quote
it to accept the issue as known-and-allowed, with a reason:

```
cdec baseline allow V-1A2B3C4D --reason "agreed in ARCH-42"
```

For a batch, save the report, mark the lines you accept with `[ALLOW]` (or
`[ALLOW: reason]`), and apply the file:

```
cdec check --log-out check.log
cdec baseline patch --file check.log
```

`cdec baseline list` shows what is accepted and why; `cdec baseline remove KEY`
withdraws it; `cdec baseline prune` drops waivers whose issue no longer occurs —
worth running periodically, since a stale waiver pre-approves the next violation
just like it. Keys are derived from what an issue *is*, not where it sits, so
reformatting or moving code never invalidates a waiver.

Lock violations (`L-`) are deliberately outside this loop — see below.

## Implementation locks

Tag a class or function `@locked` (Python) / `[Locked]` (C#) and run
`cdec lock set` to freeze its implementation. From then on `cdec check` fails if
the body changes, if the element is deleted, or if the tag is removed. Identity
is AST-based, so adding code above a locked function never trips it.

Accepting a change is the privileged step:

```
cdec lock set --target myapp.Billing.settle --force --reason "why"
```

Put `.cdec/locks.yaml` behind a CODEOWNERS entry so only leads can approve that
diff. To ship without re-baselining, `cdec check --bypass-locks --bypass-reason
"..."` prints an audit banner and passes; reject bypassed runs in CI by
checking `summary.bypassed` in `--json-out`.

## CI recipes

Pre-merge check against `main`:

```
cdec check --base-ref origin/main --json-out lint.json
```

Drift check against the committed reference:

```
cdec check
```

Either fails with exit code 1 on any violation at or above `--fail-on`
severity (default: `error`).
"""

_CI_BAT_TEMPLATE = """\
@echo off
REM Architectural CI checks. Generated by `cdec`.
REM Runs drift detection (`cdec check`) then conformance (`cdec enforce`).
setlocal

python -m code_constraints.cli check --config .cdec --source {source}
if errorlevel 1 exit /b 1

python -m code_constraints.cli enforce {source} --lang {lang}
if errorlevel 1 exit /b 1

echo code-constraints checks passed.
"""

_CI_SH_TEMPLATE = """\
#!/usr/bin/env bash
# Architectural CI checks. Generated by `cdec`.
# Runs drift detection (`cdec check`) then conformance (`cdec enforce`).
set -euo pipefail

python -m code_constraints.cli check --config .cdec --source {source}
python -m code_constraints.cli enforce {source} --lang {lang}

echo "code-constraints checks passed."
"""
