"""Extension-dispatched model persistence.

The on-disk source of truth stays XMI 2.1, but a `Project` can equally be
stored as the editor-bridge JSON shape (`editor_io.project_to_json`) under a
`.json` extension. JSON is far easier for humans and AI agents to author and
review than XMI, so every CLI command that reads or writes a model file goes
through `load_model` / `save_model` instead of calling the XMI codec directly.

The JSON document is exactly the wire format the web editor uses — one schema,
three consumers (CLI files, editor drafts, proposal endpoint).
"""

from __future__ import annotations

import json
from pathlib import Path

from code_constraints.core.editor_io import project_from_json, project_to_json
from code_constraints.core.model import Project
from code_constraints.core.xmi_reader import read_project
from code_constraints.core.xmi_writer import write_project

MODEL_SUFFIXES = (".xmi", ".json")


class UnsupportedModelFormat(ValueError):
    pass


def _codec(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in MODEL_SUFFIXES:
        raise UnsupportedModelFormat(
            f"unsupported model file extension {suffix!r} for {path} "
            f"(expected one of: {', '.join(MODEL_SUFFIXES)})"
        )
    return suffix


def load_model(path: Path | str) -> Project:
    """Read a Project from `.xmi` (XMI 2.1) or `.json` (editor JSON)."""
    path = Path(path)
    if _codec(path) == ".json":
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: top-level JSON value must be an object")
        return project_from_json(data)
    return read_project(path)


def save_model(project: Project, path: Path | str) -> None:
    """Write a Project to `.xmi` or `.json`, chosen by the file extension."""
    path = Path(path)
    if _codec(path) == ".json":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(project_to_json(project), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        return
    write_project(project, path)


__all__ = ["load_model", "save_model", "MODEL_SUFFIXES", "UnsupportedModelFormat"]
