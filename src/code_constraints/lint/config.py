"""Load and validate `.cdec/rules.yaml` — project settings and rules.

One file holds everything: the settings that say *what* to check, the `rules:`
list that says *which laws apply*, and (in the tool-managed tail, see
`code_constraints.core.rulesdoc`) the exceptions granted and the digests of
frozen implementations.

A project can instead split its laws across `.cdec/rules/*.yaml`. Those files
carry `rules:` and nothing else — settings, exceptions and locks stay in
`rules.yaml`, which is the only file the tool writes. The two layouts are
alternatives: rules come from the folder, or from the `rules:` list in
`rules.yaml`, never from both. `cdec check --rules-file NAME` then loads only
the documents you name, so a cheap subset can gate every commit and the full set
can gate the release.

`.cdec/config.yaml` is the legacy home of the settings. It is still read when it
exists, so a project scaffolded by an older `cdec init` keeps working, but
`rules.yaml` wins key by key and `cdec init --migrate` folds the old file in.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from code_constraints.core.model import SUPPORTED_LANGUAGES
from code_constraints.core.rulesdoc import RULES_FILENAME, RulesFileError, load_document
from code_constraints.lint.rules import get_rule_class, known_rule_types
from code_constraints.lint.rules.base import Rule, Severity

# `RULES_FILENAME` is re-exported: every consumer already imports the rest of the
# `.cdec/` vocabulary from here, and splitting the filename off would make them
# import two modules to name one folder.
__all__ = [
    "BASELINE_FILENAME",
    "CONFIG_FILENAME",
    "ConfigError",
    "LOCKS_FILENAME",
    "LoadedRules",
    "ProjectConfig",
    "REFERENCE_FILENAME",
    "RULES_DIRNAME",
    "RULES_FILENAME",
    "available_rule_files",
    "legacy_files",
    "load_project_config",
    "load_rules",
    "rule_files",
    "rules_dir",
    "rules_path",
]

CONFIG_FILENAME = "config.yaml"  # legacy; superseded by rules.yaml
#: The alternative to a `rules:` list in rules.yaml: a folder of rule
#: documents, each holding a `rules:` list and nothing else.
RULES_DIRNAME = "rules"
_RULE_SUFFIXES = (".yaml", ".yml")
REFERENCE_FILENAME = "reference.xmi"
# Legacy ledgers, folded into rules.yaml by `cdec init --migrate`. Still read
# when present so an existing project doesn't break on upgrade.
BASELINE_FILENAME = "baseline.yaml"
LOCKS_FILENAME = "locks.yaml"


class ConfigError(ValueError):
    pass


@dataclass
class ProjectConfig:
    """The `what and where` half of `.cdec/rules.yaml`."""

    language: str
    source: Path
    config_dir: Path = Path(".cdec")
    reference: Path | None = None
    json_out: Path | None = None
    log_out: Path | None = None

    @property
    def rules_path(self) -> Path:
        return self.config_dir / RULES_FILENAME

    @property
    def reference_path(self) -> Path:
        return self.reference or (self.config_dir / REFERENCE_FILENAME)


@dataclass
class LoadedRules:
    rules: list[Rule] = field(default_factory=list)

    def of_type(self, type_name: str) -> list[Rule]:
        return [r for r in self.rules if r.type_name == type_name]


def rules_path(config_dir: Path) -> Path:
    return config_dir / RULES_FILENAME


def rules_dir(config_dir: Path) -> Path:
    return config_dir / RULES_DIRNAME


def rule_files(config_dir: Path, only: Sequence[str] | None = None) -> list[Path]:
    """Every rule document to load, in load order.

    A project declares its laws in **one** of two layouts, never both:

    * the `rules:` list inside `rules.yaml` — the original layout, and still the
      right one for a project with a handful of laws;
    * one or more `rules/*.yaml` files, each holding a `rules:` list and nothing
      else, loaded in name order.

    With a selection, only the named documents load, in the order given. A name
    matches a file name or its stem, so `-R quick` finds `rules/quick.yaml`.
    """
    available = available_rule_files(config_dir)
    if only:
        return [_resolve_rule_file(config_dir, name, available) for name in only]
    return available


def available_rule_files(config_dir: Path) -> list[Path]:
    """The documents this project's layout says hold the rules.

    Raises when both layouts are populated. The two are alternatives, so a
    project with rules in both places has no answer to "which ones apply" — and
    guessing one would silently drop the other set of laws.
    """
    folder = rules_dir(config_dir)
    folder_files = (
        sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in _RULE_SUFFIXES)
        if folder.is_dir()
        else []
    )
    root = config_dir / RULES_FILENAME
    if not folder_files:
        return [root] if root.is_file() else []

    if _declares_rules(root):
        names = ", ".join(p.name for p in folder_files)
        raise ConfigError(
            f"{config_dir}: rules are declared in two places. Remove the 'rules:' "
            f"list from {RULES_FILENAME} (move it into {RULES_DIRNAME}/), or delete "
            f"{RULES_DIRNAME}/ ({names}). Settings, exceptions and locks stay in "
            f"{RULES_FILENAME} either way."
        )
    return folder_files


def _declares_rules(path: Path) -> bool:
    """True when `rules.yaml` carries laws of its own. An empty or absent
    `rules:` list is not a second layout — it is a file that defers."""
    try:
        return bool(load_document(path).get("rules"))
    except RulesFileError as exc:
        raise ConfigError(str(exc)) from exc


def _resolve_rule_file(config_dir: Path, name: str, available: list[Path]) -> Path:
    """One `--rules-file` name, resolved against the documents that apply."""
    wanted = Path(name).name
    for path in available:
        if wanted in (path.name, path.stem):
            return path
    listed = ", ".join(p.name for p in available) or "none"
    raise ConfigError(
        f"no rule file named {name!r} in {config_dir}. Available: {listed}"
    )


def legacy_files(config_dir: Path) -> list[Path]:
    """Legacy per-concern files present in `config_dir`, in migration order."""
    return [
        path
        for path in (
            config_dir / CONFIG_FILENAME,
            config_dir / BASELINE_FILENAME,
            config_dir / LOCKS_FILENAME,
        )
        if path.is_file()
    ]


def load_project_config(config_dir: Path) -> ProjectConfig:
    """Read the project settings. `rules.yaml` wins; `config.yaml` fills gaps."""
    rules_file = config_dir / RULES_FILENAME
    legacy_file = config_dir / CONFIG_FILENAME
    if not rules_file.is_file() and not legacy_file.is_file():
        raise ConfigError(
            f"missing {rules_file}. Run `cdec init` to scaffold it."
        )

    try:
        raw = load_document(rules_file)
    except RulesFileError as exc:
        raise ConfigError(str(exc)) from exc
    merged: dict[str, Any] = {**_load_legacy_settings(legacy_file), **raw}
    where = rules_file if rules_file.is_file() else legacy_file

    language = merged.get("language")
    if language not in SUPPORTED_LANGUAGES:
        allowed = ", ".join(SUPPORTED_LANGUAGES)
        raise ConfigError(f"{where}: 'language' must be one of: {allowed}")
    source = merged.get("source")
    if not source:
        raise ConfigError(f"{where}: 'source' is required")

    # `reference:` is a plain top-level path now. The legacy nesting
    # (`baseline: {reference: ...}`) still resolves.
    reference_value = merged.get("reference")
    if reference_value is None:
        legacy_baseline = merged.get("baseline")
        if isinstance(legacy_baseline, dict):
            reference_value = legacy_baseline.get("reference")

    output = merged.get("output") or {}
    if not isinstance(output, dict):
        raise ConfigError(f"{where}: 'output' must be a mapping")

    return ProjectConfig(
        language=language,
        source=_resolve(source, config_dir.parent),
        config_dir=config_dir,
        reference=_resolve(reference_value, config_dir.parent) if reference_value else None,
        json_out=_resolve(output.get("json"), config_dir.parent) if output.get("json") else None,
        log_out=_resolve(output.get("log"), config_dir.parent) if output.get("log") else None,
    )


def _load_legacy_settings(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top-level must be a mapping")
    # `lock:` used to be a settings section; it is now the options of an
    # `implementation-locks` rule, so it is not carried over here.
    return {k: v for k, v in raw.items() if k != "lock"}


def load_rules(config_dir: Path, only: Sequence[str] | None = None) -> LoadedRules:
    """Build the rule objects from every selected document's `rules:` list.

    `only` names the documents to read (see `rule_files`); without it every rule
    document the project's layout declares is read. Rule ids stay unique across
    files: a duplicate is an error, because two entries of one id would report
    under one heading and share every exception key.
    """
    files = rule_files(config_dir, only)
    if not files:
        # Neither layout is present: no rules.yaml and no populated rules/.
        raise ConfigError(
            f"missing {config_dir / RULES_FILENAME}. Run `cdec init` to scaffold it."
        )

    out: list[Rule] = []
    seen_ids: set[str] = set()
    for path in files:
        for i, entry in enumerate(_rule_entries(config_dir, path)):
            rule = _build_rule(path, i, entry, seen_ids)
            if rule is not None:
                out.append(rule)
    return LoadedRules(rules=out)


def _rule_entries(config_dir: Path, path: Path) -> list[Any]:
    """The `rules:` list of one document, after the format check."""
    try:
        raw = load_document(path)
    except RulesFileError as exc:
        raise ConfigError(str(exc)) from exc
    if path != config_dir / RULES_FILENAME:
        _validate_folder_document(path, raw)
    entries = raw.get("rules") or []
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: 'rules' must be a list")
    return entries


def _validate_folder_document(path: Path, raw: dict[str, Any]) -> None:
    """A file under `.cdec/rules/` carries laws and nothing else.

    Settings, `exceptions:` and `locks:` belong to `rules.yaml` — the tool
    writes only that file, so honouring them here would be a promise the writer
    does not keep. Say so instead of ignoring them.
    """
    if "rules" not in raw:
        raise ConfigError(
            f"{path}: not a rule file. It needs a top-level 'rules:' list."
        )
    extra = sorted(set(raw) - {"rules"})
    if extra:
        raise ConfigError(
            f"{path}: only 'rules:' is allowed in {RULES_DIRNAME}/; found "
            f"{', '.join(extra)}. Settings, exceptions and locks stay in "
            f"{RULES_FILENAME}."
        )


def _build_rule(
    path: Path, i: int, entry: Any, seen_ids: set[str]
) -> Rule | None:
    if not isinstance(entry, dict):
        raise ConfigError(f"{path}: rules[{i}] must be a mapping")
    rule_id = entry.get("id")
    type_name = entry.get("type")
    if not rule_id:
        raise ConfigError(f"{path}: rules[{i}] missing 'id'")
    if rule_id in seen_ids:
        raise ConfigError(f"{path}: duplicate rule id {rule_id!r}")
    seen_ids.add(rule_id)
    if not type_name:
        raise ConfigError(f"{path}: rules[{i}] (id={rule_id}) missing 'type'")
    rule_cls = get_rule_class(type_name)
    if rule_cls is None:
        raise ConfigError(
            f"{path}: rules[{i}] (id={rule_id}) has unknown type {type_name!r}. "
            f"Known types: {', '.join(known_rule_types())}"
        )
    severity_raw = entry.get("severity", "error")
    # YAML 1.1 parses bare `off` / `on` as booleans; coerce back to strings.
    if isinstance(severity_raw, bool):
        severity_raw = "off" if severity_raw is False else "on"
    try:
        severity = Severity(severity_raw)
    except ValueError as exc:
        raise ConfigError(
            f"{path}: rules[{i}] (id={rule_id}) has invalid severity {severity_raw!r}"
        ) from exc
    if severity == Severity.OFF:
        return None
    scope = entry.get("scope", rule_cls.default_scope)
    if scope not in ("diff", "snapshot"):
        raise ConfigError(f"{path}: rules[{i}] (id={rule_id}) has invalid scope {scope!r}")
    ignore = entry.get("ignore") or []
    if not isinstance(ignore, list):
        raise ConfigError(f"{path}: rules[{i}] (id={rule_id}) 'ignore' must be a list")
    reserved = {"id", "type", "severity", "scope", "message", "ignore"}
    options: dict[str, Any] = {k: v for k, v in entry.items() if k not in reserved}
    return rule_cls(
        rule_id=rule_id,
        severity=severity,
        scope=scope,
        message=entry.get("message", ""),
        ignore=ignore,
        options=options,
    )


def _resolve(path_value: str | None, base: Path) -> Path:
    if path_value is None:
        return base
    p = Path(path_value)
    if p.is_absolute():
        return p
    return (base / p).resolve()
