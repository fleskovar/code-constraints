"""The project history: `.cdec/history/`, one entry per recorded decision.

`rules.yaml` and `reference.xmi` say where a project is now. This module records
how it got there. Each entry is a pair of committed files:

    .cdec/history/20261115-143210-goal.yaml   who, when, why, the rules in force
    .cdec/history/20261115-143210-goal.xmi    the model at that moment

Three kinds of entry tell the story of a change:

    start       the state the journey began from (written by `cdec init`)
    goal        a target model the team agreed on  (`cdec reference set`)
    checkpoint  the code as it was at that moment  (`cdec history add`,
                `cdec check --automatic-exceptions reference`)
    rules       a rule that the web app turned on, changed or removed

An entry with `reference: true` is one whose model became `.cdec/reference.xmi`.
The open goal is the latest such entry when its kind is `goal`: a later
re-snapshot of the reference closes it.

Entries are append-only and one entry is two files, so two branches that each
record an entry merge without a conflict. A project turns the history off with
`history: false` in `rules.yaml`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from code_constraints.core.diff import diff_projects
from code_constraints.core.model import DiffStatus, Project, _walk_packages
from code_constraints.core.rulesdoc import RULES_FILENAME, load_document
from code_constraints.core.xmi_reader import read_project
from code_constraints.core.xmi_writer import write_project

HISTORY_DIRNAME = "history"
KINDS = ("start", "goal", "checkpoint", "rules")


@dataclass
class Entry:
    id: str
    kind: str
    title: str
    note: str = ""
    created: str = ""
    author: str = ""
    commit: str = ""
    # `greenfield` or `brownfield`. Only the start entry carries it.
    journey: str = ""
    # True when this model became `.cdec/reference.xmi`.
    reference: bool = False
    stats: dict[str, int] = field(default_factory=dict)
    # The rules in force, as `{id, type, severity}`.
    rules: list[dict[str, str]] = field(default_factory=list)
    # A checkpoint recorded while a goal is open: the goal, and how far the
    # code is from it (class-level differences).
    goal: str = ""
    distance: dict[str, int] = field(default_factory=dict)


def history_dir(config_dir: Path) -> Path:
    return config_dir / HISTORY_DIRNAME


def model_path(config_dir: Path, entry_id: str) -> Path:
    return history_dir(config_dir) / f"{entry_id}.xmi"


def entries(config_dir: Path) -> list[Entry]:
    """Every entry, oldest first. An id starts with its UTC time, so the file
    names sort in the order of the events."""
    folder = history_dir(config_dir)
    if not folder.is_dir():
        return []
    known = set(Entry.__dataclass_fields__)
    out: list[Entry] = []
    for path in sorted(folder.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        # A file a person wrote by hand, or a newer cdec, may carry more keys.
        if isinstance(raw, dict) and raw.get("id") and raw.get("kind") in KINDS:
            out.append(Entry(**{k: v for k, v in raw.items() if k in known}))
    return out


def open_goal(history: list[Entry]) -> Entry | None:
    """The goal the project works towards now, if there is one."""
    current = next((e for e in reversed(history) if e.reference), None)
    return current if current is not None and current.kind == "goal" else None


def distance(actual: Project, target: Project) -> dict[str, int]:
    """Class-level differences between the code and a target model.

    `to_build` classes are in the target only, `unplanned` classes are in the
    code only, and `to_change` classes are in both with different members.
    """
    out = {"to_build": 0, "unplanned": 0, "to_change": 0}
    names = {
        DiffStatus.ADDED: "to_build",
        DiffStatus.REMOVED: "unplanned",
        DiffStatus.CHANGED: "to_change",
    }
    for cls in diff_projects(actual, target).iter_classes():
        if cls.status in names:
            out[names[cls.status]] += 1
    return out


def record(
    config_dir: Path,
    kind: str,
    title: str,
    model: Project,
    *,
    note: str = "",
    journey: str = "",
    reference: bool = False,
) -> Entry | None:
    """Append one entry. Returns None when the project turned the history off."""
    if kind not in KINDS:
        raise ValueError(f"unknown history kind {kind!r}; use one of {', '.join(KINDS)}")
    document = load_document(config_dir / RULES_FILENAME)
    if document.get("history") is False:
        return None

    history = entries(config_dir)
    folder = history_dir(config_dir)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    # The time is the sort key, so two entries never share one second.
    while any(folder.glob(f"{now:%Y%m%d-%H%M%S}-*.yaml")):
        now += timedelta(seconds=1)
    entry_id = f"{now:%Y%m%d-%H%M%S}-{kind}"
    entry = Entry(
        id=entry_id,
        kind=kind,
        title=title.strip() or kind.capitalize(),
        note=note.strip(),
        created=now.isoformat(),
        author=_actor(),
        commit=_head_commit(config_dir),
        journey=journey,
        reference=reference,
        stats=_stats(model, document),
        rules=rules_in_force(config_dir, document),
    )
    goal = open_goal(history)
    if kind == "checkpoint" and goal is not None:
        entry.goal = goal.id
        try:
            entry.distance = distance(model, read_project(model_path(config_dir, goal.id)))
        except (OSError, ValueError):
            # The goal model is gone, or it is in another language. The
            # checkpoint is still worth recording.
            entry.goal = ""

    folder.mkdir(parents=True, exist_ok=True)
    # ponytail: one full XMI per entry. A project that records hundreds of
    # entries of a large model pays for it in the working tree. Upgrade path:
    # store the model once per content hash, or gzip it.
    write_project(model, model_path(config_dir, entry_id))
    (folder / f"{entry_id}.yaml").write_text(
        yaml.safe_dump(
            {k: v for k, v in asdict(entry).items() if v not in ("", {}, [], False)},
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return entry


def record_reference(
    config_dir: Path, kind: str, title: str, reference_path: Path, *, note: str = ""
) -> Entry | None:
    """Record the model that was just written to the reference file."""
    from code_constraints.core.model_io import load_model as load_model_file

    return record(
        config_dir, kind, title, load_model_file(reference_path), note=note, reference=True
    )


def load_model(config_dir: Path, entry_id: str) -> Project:
    return read_project(model_path(config_dir, entry_id))


# ---------- internals ----------

def _stats(model: Project, document: dict[str, Any]) -> dict[str, int]:
    return {
        "classes": sum(1 for _ in model.iter_classes()),
        "packages": sum(1 for _ in _walk_packages(model.packages)),
        "exceptions": len(document.get("exceptions") or []),
        "locks": len(document.get("locks") or []),
    }


def rules_in_force(config_dir: Path, document: dict[str, Any]) -> list[dict[str, str]]:
    """`{id, type, severity}` of every rule, read from whichever layout holds
    them. A broken rule file must not stop a history entry, so this reads the
    raw documents and does not build the rules."""
    raw: list[Any] = list(document.get("rules") or [])
    folder = config_dir / "rules"
    if folder.is_dir():
        for path in sorted(folder.glob("*.y*ml")):
            try:
                raw.extend(load_document(path).get("rules") or [])
            except ValueError:
                continue
    out = []
    for item in raw:
        if isinstance(item, dict) and item.get("id"):
            severity = item.get("severity", "error")
            # YAML reads a bare `off` as False.
            severity = "off" if severity is False else str(severity)
            out.append({"id": str(item["id"]), "type": str(item.get("type", "")), "severity": severity})
    return out


def _actor() -> str:
    from code_constraints.waivers.store import default_actor

    return default_actor()


def _head_commit(config_dir: Path) -> str:
    """Short hash of HEAD, with `+` when the working tree has changes. Empty
    outside a git repository."""
    try:
        from git import Repo

        repo = Repo(str(config_dir.resolve().parent), search_parent_directories=True)
        return repo.head.commit.hexsha[:7] + ("+" if repo.is_dirty() else "")
    except Exception:  # noqa: BLE001 - no repository, no commit, no git binary
        return ""
