"""Load and validate `.cdec/config.yaml` and `.cdec/rules.yaml`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from code_constraints.core.model import SUPPORTED_LANGUAGES
from code_constraints.lint.rules import get_rule_class, known_rule_types
from code_constraints.lint.rules.base import Rule, Severity


CONFIG_FILENAME = "config.yaml"
RULES_FILENAME = "rules.yaml"
BASELINE_FILENAME = "baseline.yaml"
REFERENCE_FILENAME = "reference.xmi"
# Ledger of approved implementation digests, read/written by `cdec lock`.
LOCKS_FILENAME = "locks.yaml"


class ConfigError(ValueError):
    pass


@dataclass
class LockConfig:
    """`lock:` section of config.yaml — settings for `cdec lock` (Engine C).

    `targets` freezes elements by qualified-name glob without needing a tag in
    the source; it's the practical way to lock a whole test package. `enabled`
    only controls whether `cdec check` runs the lock verification automatically —
    `cdec lock check` always runs.
    """

    enabled: bool = True
    include_docstrings: bool = False
    targets: list[str] = field(default_factory=list)
    lockfile: Path | None = None


@dataclass
class ProjectConfig:
    language: str
    source: Path
    reference: Path | None = None
    json_out: Path | None = None
    log_out: Path | None = None
    lock: LockConfig = field(default_factory=LockConfig)


@dataclass
class LoadedRules:
    rules: list[Rule] = field(default_factory=list)


def load_project_config(config_dir: Path) -> ProjectConfig:
    cfg_path = config_dir / CONFIG_FILENAME
    if not cfg_path.is_file():
        raise ConfigError(f"missing {cfg_path}")
    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{cfg_path}: top-level must be a mapping")
    language = raw.get("language")
    if language not in SUPPORTED_LANGUAGES:
        allowed = ", ".join(SUPPORTED_LANGUAGES)
        raise ConfigError(f"{cfg_path}: 'language' must be one of: {allowed}")
    source = raw.get("source")
    if not source:
        raise ConfigError(f"{cfg_path}: 'source' is required")
    baseline = raw.get("baseline") or {}
    reference_value = baseline.get("reference") if isinstance(baseline, dict) else None
    reference = _resolve(reference_value, config_dir.parent) if reference_value else None
    output = raw.get("output") or {}
    json_out = _resolve(output.get("json"), config_dir.parent) if output.get("json") else None
    log_out = _resolve(output.get("log"), config_dir.parent) if output.get("log") else None
    return ProjectConfig(
        language=language,
        source=_resolve(source, config_dir.parent),
        reference=reference,
        json_out=json_out,
        log_out=log_out,
        lock=_load_lock_config(raw.get("lock"), config_dir, cfg_path),
    )


def _load_lock_config(raw: Any, config_dir: Path, cfg_path: Path) -> LockConfig:
    if raw is None:
        return LockConfig()
    if not isinstance(raw, dict):
        raise ConfigError(f"{cfg_path}: 'lock' must be a mapping")
    targets = raw.get("targets") or []
    if not isinstance(targets, list):
        raise ConfigError(f"{cfg_path}: 'lock.targets' must be a list of globs")
    lockfile_value = raw.get("lockfile")
    return LockConfig(
        enabled=bool(raw.get("enabled", True)),
        include_docstrings=bool(raw.get("include_docstrings", False)),
        targets=[str(t) for t in targets],
        lockfile=_resolve(lockfile_value, config_dir.parent) if lockfile_value else None,
    )


def load_rules(config_dir: Path) -> LoadedRules:
    rules_path = config_dir / RULES_FILENAME
    if not rules_path.is_file():
        raise ConfigError(f"missing {rules_path}")
    with rules_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{rules_path}: top-level must be a mapping with a 'rules:' list")
    entries = raw.get("rules") or []
    if not isinstance(entries, list):
        raise ConfigError(f"{rules_path}: 'rules' must be a list")

    out: list[Rule] = []
    seen_ids: set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ConfigError(f"{rules_path}: rules[{i}] must be a mapping")
        rule_id = entry.get("id")
        type_name = entry.get("type")
        if not rule_id:
            raise ConfigError(f"{rules_path}: rules[{i}] missing 'id'")
        if rule_id in seen_ids:
            raise ConfigError(f"{rules_path}: duplicate rule id {rule_id!r}")
        seen_ids.add(rule_id)
        if not type_name:
            raise ConfigError(f"{rules_path}: rules[{i}] (id={rule_id}) missing 'type'")
        rule_cls = get_rule_class(type_name)
        if rule_cls is None:
            raise ConfigError(
                f"{rules_path}: rules[{i}] (id={rule_id}) has unknown type {type_name!r}. "
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
                f"{rules_path}: rules[{i}] (id={rule_id}) has invalid severity {severity_raw!r}"
            ) from exc
        if severity == Severity.OFF:
            continue
        scope = entry.get("scope", _default_scope(type_name))
        if scope not in ("diff", "snapshot"):
            raise ConfigError(
                f"{rules_path}: rules[{i}] (id={rule_id}) has invalid scope {scope!r}"
            )
        message = entry.get("message", "")
        ignore = entry.get("ignore") or []
        if not isinstance(ignore, list):
            raise ConfigError(f"{rules_path}: rules[{i}] (id={rule_id}) 'ignore' must be a list")
        # Everything else on the entry is treated as rule-specific options.
        reserved = {"id", "type", "severity", "scope", "message", "ignore"}
        options: dict[str, Any] = {k: v for k, v in entry.items() if k not in reserved}
        rule = rule_cls(
            rule_id=rule_id,
            severity=severity,
            scope=scope,
            message=message,
            ignore=ignore,
            options=options,
        )
        out.append(rule)
    return LoadedRules(rules=out)


def _default_scope(type_name: str) -> str:
    if type_name in (
        "no-new-classes",
        "no-removed-classes",
        "frozen-members",
        "frozen-rules",
    ):
        return "diff"
    return "snapshot"


def _resolve(path_value: str | None, base: Path) -> Path:
    if path_value is None:
        return base
    p = Path(path_value)
    if p.is_absolute():
        return p
    return (base / p).resolve()
