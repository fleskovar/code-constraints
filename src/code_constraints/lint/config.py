"""Load and validate `.cdec/rules.yaml` — project settings and rules.

One file holds everything: the settings that say *what* to check, the `rules:`
list that says *which laws apply*, and (in the tool-managed tail, see
`code_constraints.core.rulesdoc`) the exceptions granted and the digests of
frozen implementations.

`.cdec/config.yaml` is the legacy home of the settings. It is still read when it
exists, so a project scaffolded by an older `cdec init` keeps working, but
`rules.yaml` wins key by key and `cdec init --migrate` folds the old file in.
"""

from __future__ import annotations

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
    "RULES_FILENAME",
    "legacy_files",
    "load_project_config",
    "load_rules",
    "rules_path",
]

CONFIG_FILENAME = "config.yaml"  # legacy; superseded by rules.yaml
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


def load_rules(config_dir: Path) -> LoadedRules:
    """Build the rule objects from the `rules:` list."""
    path = config_dir / RULES_FILENAME
    if not path.is_file():
        # A project still on the legacy layout may have no rules.yaml at all.
        raise ConfigError(f"missing {path}. Run `cdec init` to scaffold it.")
    try:
        raw = load_document(path)
    except RulesFileError as exc:
        raise ConfigError(str(exc)) from exc

    entries = raw.get("rules") or []
    if not isinstance(entries, list):
        raise ConfigError(f"{path}: 'rules' must be a list")

    out: list[Rule] = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(entries):
        rule = _build_rule(path, i, entry, seen_ids)
        if rule is not None:
            out.append(rule)
    return LoadedRules(rules=out)


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
