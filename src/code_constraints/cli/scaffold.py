"""Reusable, non-interactive scaffolding primitives.

Shared by the `cdec init` subcommand and the interactive session
(`code_constraints.cli.interactive`). Everything here is pure file I/O + asset resolution —
no prompting, no `typer.Exit`. Callers decide how to surface results.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from code_constraints.core.model import SUPPORTED_LANGUAGES
from code_constraints.core.rulesdoc import RULES_FILENAME
from code_constraints.lint.config import (
    BASELINE_FILENAME,
    CONFIG_FILENAME,
    LOCKS_FILENAME,
    REFERENCE_FILENAME,
    RULES_DIRNAME,
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
# skill (the propose → review → lock workflow). Each entry is the destination
# path inside the user's project. The source copies live in the package at
# `cli/_assets/{agents,skills}/` — this repo does not track its own `.claude/`.
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

    Shims prefer the repo-relative source-of-truth file (editable installs) and
    fall back to the packaged copy under `code_constraints/cli/_assets/…`, where
    `force-include` maps them in. The `.claude/…` rels have no repo-relative
    original, so they always resolve to the packaged copy. Raises ScaffoldError
    if missing.
    """
    # `.claude/…` rels are destination paths only — never read them back out of
    # a repo root, or an editable install would prefer a developer's own
    # untracked `.claude/` over the packaged source of truth.
    root = None if rel.startswith(".claude/") else _repo_root()
    if root is not None:
        candidate = root / rel
        if candidate.is_file():
            return candidate

    # Packaged copy: assets are flattened under code_constraints/cli/_assets/.
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
    """Scaffold a `.cdec/` folder and snapshot a reference model from `source`.

    One `rules.yaml` carries the settings and the rules; the exceptions granted
    and the lock ledger are appended to its tool-managed tail as they are
    earned. Returns the files written.

    Raises ScaffoldError on an unsupported language, or if a target file exists
    and `force` is False.
    """
    if lang not in SUPPORTED_LANGS:
        raise ScaffoldError(f"unsupported language: {lang}")

    config_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    files = [
        (
            config_dir / RULES_FILENAME,
            _RULES_TEMPLATE.format(lang=lang, source=_posix(source)),
        ),
        (config_dir / "README.md", _README_TEMPLATE),
    ]
    for path, content in files:
        if path.exists() and not force:
            raise ScaffoldError(f"refusing to overwrite {path} (use force)")
        path.write_text(content, encoding="utf-8")
        written.append(path)

    # The folder for the other rule layout. Scaffolded empty, so it changes
    # nothing until a file lands in it: the rules then come from the folder
    # instead of the `rules:` list above, and `--rules-file` can run a subset.
    extra_rules = config_dir / RULES_DIRNAME
    extra_rules.mkdir(exist_ok=True)
    keep = extra_rules / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
        written.append(keep)

    gitignore = config_dir / ".gitignore"
    gitignore.write_text("cache/\n", encoding="utf-8")
    written.append(gitignore)

    # Snapshot a reference model up front. It is the baseline every diff-scope
    # rule needs, and "where does reference.xmi come from" is the first question
    # anybody asks — so scaffolding answers it rather than deferring it.
    reference_path = config_dir / REFERENCE_FILENAME
    if source.exists():
        from code_constraints.core.xmi_writer import write_project

        project = _parse_project(source, lang)
        write_project(project, reference_path)
        written.append(reference_path)

    return written


def migrate_cdec_config(config_dir: Path) -> tuple[list[Path], list[Path]]:
    """Fold `config.yaml` / `baseline.yaml` / `locks.yaml` into `rules.yaml`.

    Returns (files written, files removed). The old files are deleted only once
    their content has been read back out of the new one, so a failed migration
    leaves the project exactly as it was.
    """
    import yaml

    from code_constraints.core.rulesdoc import load_document, write_sections
    from code_constraints.lock.store import load_locks, write_locks
    from code_constraints.waivers.store import load_waivers, save_waivers

    rules_path = config_dir / RULES_FILENAME
    legacy_config = config_dir / CONFIG_FILENAME
    legacy_baseline = config_dir / BASELINE_FILENAME
    legacy_locks = config_dir / LOCKS_FILENAME
    if not any(p.is_file() for p in (legacy_config, legacy_baseline, legacy_locks)):
        return [], []

    # 1. Settings, prepended as plain top-level keys above whatever rules.yaml
    #    already holds, so the rules and their comments are untouched.
    if legacy_config.is_file():
        with legacy_config.open(encoding="utf-8") as fh:
            old = yaml.safe_load(fh) or {}
        if not isinstance(old, dict):
            raise ScaffoldError(f"{legacy_config}: top-level must be a mapping")
        existing = load_document(rules_path) if rules_path.is_file() else {}
        header = _migrated_settings_header(old, existing)
        body = rules_path.read_text(encoding="utf-8") if rules_path.is_file() else _EMPTY_RULES
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        rules_path.write_text(header + body, encoding="utf-8")
        # A `lock:` settings block becomes an `implementation-locks` rule. Only
        # a configured one is carried over: inventing a rule the project never
        # opted into would turn a migration into a new gate.
        lock_cfg = old.get("lock") or {}
        if isinstance(lock_cfg, dict) and lock_cfg.get("targets"):
            targets = ", ".join(f'"{t}"' for t in lock_cfg.get("targets") or [])
            with rules_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    _MIGRATED_LOCK_RULE.format(
                        targets=f"[{targets}]",
                        include_docstrings=str(
                            bool(lock_cfg.get("include_docstrings", False))
                        ).lower(),
                    )
                )

    # 2. Exceptions and locks, read through the loaders that already understand
    #    both the old and the new shape, then written back in the new one.
    store = load_waivers(config_dir)
    entries = load_locks(config_dir)
    if store.waivers:
        save_waivers(config_dir, store)
    if entries:
        write_locks(config_dir, entries.values())

    # 3. Only now that everything demonstrably landed, drop the old files.
    reread = load_document(rules_path)
    if store.waivers and not reread.get("exceptions"):
        raise ScaffoldError(f"migration aborted: exceptions did not land in {rules_path}")
    if entries and not reread.get("locks"):
        raise ScaffoldError(f"migration aborted: locks did not land in {rules_path}")

    removed: list[Path] = []
    for path in (legacy_config, legacy_baseline, legacy_locks):
        if path.is_file():
            path.unlink()
            removed.append(path)
    return [rules_path], removed


def _migrated_settings_header(old: dict, existing: dict) -> str:
    """Render a legacy config.yaml's settings as rules.yaml top-level keys.

    Keys already present in rules.yaml win — that is the file the user has been
    editing, so it is the more current statement of intent.
    """
    lines = ["# Project settings (migrated from config.yaml).\n"]
    lines.append(f"language: {existing.get('language') or old.get('language') or 'python'}\n")
    lines.append(f"source: {existing.get('source') or old.get('source') or '.'}\n")
    reference = existing.get("reference")
    if reference is None:
        legacy_baseline = old.get("baseline")
        if isinstance(legacy_baseline, dict):
            reference = legacy_baseline.get("reference")
    if reference:
        lines.append(f"reference: {reference}\n")
    output = existing.get("output") or old.get("output") or {}
    if isinstance(output, dict) and (output.get("json") or output.get("log")):
        lines.append("output:\n")
        if output.get("json"):
            lines.append(f"  json: {output['json']}\n")
        if output.get("log"):
            lines.append(f"  log: {output['log']}\n")
    lines.append("\n")
    return "".join(lines)


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

    Both are one line of real work: `cdec check` is the whole gate, and its exit
    code is the whole answer."""
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


_EMPTY_RULES = "rules: []\n"

_MIGRATED_LOCK_RULE = """
  # Migrated from the `lock:` section of config.yaml. Locks are a rule now, so
  # they are configured, reported and gated exactly like every other law here.
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    include_docstrings: {include_docstrings}
    targets: {targets}
"""

_RULES_TEMPLATE = """\
# ============================================================================
# .cdec/rules.yaml — everything `cdec check` needs, in one committed file.
#
#   settings     what to check and where           (below)
#   rules:       the laws that are enforced        (below)
#   exceptions:  violations you accepted, and why  (written by the tool)
#   locks:       digests of frozen implementations (written by the tool)
#
# The last two live in a marked section at the end of the file. The tool
# rewrites only that section, so every comment and message you write up here
# survives untouched.
#
# One command runs all of it:
#
#   cdec check                                   verify everything
#   cdec check --automatic-exceptions reference  snapshot .cdec/reference.xmi
#   cdec check --automatic-exceptions rules      grandfather today's violations
#   cdec check --automatic-exceptions locks      record digests for @locked code
#   cdec exceptions allow V-1A2B3C4D --reason .. accept one issue, with a reason
# ============================================================================

language: {lang}    # python | csharp | typescript | svelte | odin | lua | julia
source: {source}    # the source tree `cdec check` parses

# The baseline every `scope: diff` rule compares against, and the model the
# `reference-architecture` rule gates on. `cdec init` snapshots it for you;
# re-snapshot with `cdec check --automatic-exceptions reference`.
reference: .cdec/reference.xmi

output:
  json: null       # optional default for --json-out
  log: null        # optional default for --log-out

# ---------------------------------------------------------------------------
# Rules. Every entry takes:
#   id        — stable identifier, and the heading violations are grouped under
#   type      — which rule to run (list below)
#   severity  — error | warning | off
#   scope     — diff | snapshot (defaults per rule type)
#   message   — what to print when it fires. Supports {{placeholders}} and YAML
#               block scalars (`message: |`). USE IT: a rule that explains why
#               it exists teaches; one that just says "violation" breeds
#               resentment.
#   ignore    — list of qualified-name globs to exempt
#
# The rules can live here, or in `.cdec/rules/*.yaml` (one `rules:` list per
# file), but not in both — a project with laws in two places fails the run.
# With the folder, `cdec check` runs every file in it and
# `cdec check --rules-file NAME` runs a subset.
#
# `cdec check` is opt-in — an empty list enforces nothing. Add laws one at a
# time, as the team agrees on them.
#
# --- model rules (read the parsed architecture) ---
#   no-new-classes, no-removed-classes ....... structural drift  (scope: diff)
#   frozen-members ........................... a class's public shape (diff)
#   frozen-rules ............................. the constraint tags themselves (diff)
#   forbidden-references ..................... class A may not reference class B
#   forbidden-package-references ............. package A may not reference package B
#   no-cyclic-package-dependencies ........... no dependency cycles
#   layer-dependencies ....................... @layer tags + an allowed-direction matrix
#   subclass-naming .......................... subclasses of X must be named Y
#   dangling-classes ......................... nothing references this class
#   max-class-fanout ......................... a class references too many others
#
# --- source rules (re-read the code itself) ---
#   tag-conformance .......................... the implementation obeys its
#                                              @sealed / @immutable / @factory /
#                                              @no_instantiation tags
#   implementation-locks ..................... an @locked body may not change
#   reference-architecture ................... no structural deviation from
#                                              reference.xmi at all
#
# Placeholders available in `message`, by type:
#   no-new-classes / no-removed-classes / dangling-classes:
#     {{qualified_name}}                (max-class-fanout adds {{fanout}}, {{limit}})
#   frozen-members:            {{qualified_name}}, {{member}}, {{kind}}, {{action}}
#   forbidden-*-references:    {{qualified_name}}, {{source}}, {{target}}
#   subclass-naming:           {{qualified_name}}, {{name}}, {{base}}, {{pattern}}
#   no-cyclic-package-dependencies: {{cycle}}
#   frozen-rules:              {{qualified_name}}, {{rule}}, {{member}}, {{action}}
#   layer-dependencies:        {{qualified_name}}, {{source}}, {{target}},
#                              {{source_layer}}, {{target_layer}}
#   tag-conformance:           {{qualified_name}}, {{rule}}, {{detail}}, {{message}}
#   implementation-locks:      {{qualified_name}}, {{kind}}, {{message}}
#   reference-architecture:    {{qualified_name}}, {{category}}, {{member}}, {{message}}
#
# Every rule and every source tag is documented with options and worked
# pass/fail examples in docs/RULES_CATALOGUE.md.
# ---------------------------------------------------------------------------

rules: []

# Examples — uncomment and adapt:
#
# - id: domain-must-not-depend-on-ui
#   type: forbidden-package-references
#   severity: error
#   from: ["myapp.domain.**"]
#   to:   ["myapp.ui.**"]
#   message: |
#     Layering violation: '{{source}}' must not depend on '{{target}}'.
#     The domain is pure business rules; move the reference to whichever
#     package owns the workflow.
#
# - id: no-new-classes
#   type: no-new-classes
#   severity: error
#   ignore: ["tests.**"]
#
# - id: layering
#   type: layer-dependencies
#   severity: error
#   allow:
#     ui:     [domain]
#     domain: [data]
#     data:   []
#
# - id: tags-must-be-honoured
#   type: tag-conformance
#   severity: error
#
# - id: frozen-implementations
#   type: implementation-locks
#   severity: error
#
# - id: public-shape-is-frozen
#   type: reference-architecture
#   severity: error
"""

_README_TEMPLATE = """\
# `.cdec/` — architectural constraints for this project

Two files, and one command that reads them.

| File | What it is |
|---|---|
| `rules.yaml` | Settings, the rules enforced, the exceptions granted, and the digests of frozen implementations. Commit it. |
| `rules/` | The other way to hold the rules: one or more `*.yaml` files, each with a `rules:` list and nothing else. Use this **or** the `rules:` list in `rules.yaml`, never both. Commit them. |
| `reference.xmi` | A snapshot of the architecture, used as the baseline for `scope: diff` rules and by the `reference-architecture` rule. Commit it. |
| `cache/` | Transient parse artefacts. Gitignored. |

```
cdec check
```

That is the whole gate.

## Two ways to hold the rules

Keep every law in the `rules:` list in `rules.yaml`. That is the default and it
stays valid forever.

Or split them across `rules/*.yaml`, one `rules:` list per file and nothing else
in it — useful when some checks are cheap enough for every commit and others
belong before a release:

```
.cdec/rules/fast.yaml      # cheap checks, run on every commit
.cdec/rules/release.yaml   # the slow ones, run before a release
```

```
cdec check                 # every file in rules/
cdec check --rules-file fast
cdec check -R fast -R release
```

**Pick one.** If `rules.yaml` has a `rules:` list and `rules/` has files, the run
fails and tells you so — running one set and ignoring the other would silently
drop laws you committed. Settings, `exceptions:` and `locks:` stay in
`rules.yaml` either way, because that is the only file the tool writes. Rule ids
stay unique across all the files. Architectural rules, source-tag conformance,
implementation locks and the reference gate are all rule types in `rules.yaml`,
so there is one command to run in CI and one exit code to read.

## Accepting things

Every issue prints a stable key (`V-` a configured rule, `F-` tag conformance,
`L-` a lock, `R-` a reference deviation). The key is derived from what the issue
*is*, never from where it sits, so reformatting or moving code never invalidates
a decision you recorded.

```
cdec exceptions allow V-1A2B3C4D --reason "agreed in ARCH-42"
```

For a batch, save the report, mark the lines you accept with `[ALLOW]` (or
`[ALLOW: reason]`), and apply the file:

```
cdec check --log-out check.log
cdec exceptions patch --file check.log
```

`cdec exceptions list` shows what is accepted and why; `remove KEY` withdraws
it; `prune` drops exceptions whose issue no longer occurs — worth running
periodically, since a stale one pre-approves the next violation just the same.

To grandfather everything at once when adopting a rule on an existing codebase:

```
cdec check --automatic-exceptions rules
```

## Locks are the exception to exceptions

`L-` issues cannot be accepted through `cdec exceptions`. Tag a class or
function `@locked` (Python) / `[Locked]` (C#), add an `implementation-locks`
rule, and record the digest:

```
cdec check --automatic-exceptions locks
```

That is safe for anyone to run: without `--force` it can only *add* locks, never
erase the evidence that a frozen body changed. Accepting a change to locked code
is the privileged step:

```
cdec check --automatic-exceptions locks --force
```

It rewrites the `locks:` section, which is a reviewable diff. Put `rules.yaml`
behind a CODEOWNERS entry and re-baselining becomes a lead-only action that
always leaves a trail. To ship without re-baselining,
`cdec check --bypass-locks --bypass-reason "..."` prints an audit banner and
passes; reject bypassed runs in CI by checking `summary.bypassed` in
`--json-out`.

## CI recipes

Pre-merge, against the target branch:

```
cdec check --base-ref origin/main --json-out lint.json
```

Against the committed reference:

```
cdec check
```

Either exits 1 on any violation at or above `--fail-on` severity (default:
`error`).
"""

_CI_BAT_TEMPLATE = """\
@echo off
REM Architectural CI check. Generated by `cdec`.
REM One command: every rule in .cdec/rules.yaml, one exit code.
setlocal

python -m code_constraints.cli check --config .cdec --source {source}
if errorlevel 1 exit /b 1

echo code-constraints checks passed.
"""

_CI_SH_TEMPLATE = """\
#!/usr/bin/env bash
# Architectural CI check. Generated by `cdec`.
# One command: every rule in .cdec/rules.yaml, one exit code.
set -euo pipefail

python -m code_constraints.cli check --config .cdec --source {source}

echo "code-constraints checks passed."
"""
