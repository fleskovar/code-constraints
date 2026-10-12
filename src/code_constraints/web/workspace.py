"""The viewer's local workspace, kept under `.cdec_cache/`.

Two things live here. Both are private to one checkout and are never committed:

- `recent.json` — the paths the user opened, most recently used first.
- `<project_id>/views/<view_id>.json` — the views of one path. A view is a named
  state of the canvas that the viewer saves by itself while the user works, so a
  closed browser tab does not lose the work. A view that the user did not name
  is `Untitled N`.

These are not the shared views in `.cdec/views/`. Those are saved on request,
keyed by qualified name, and committed for the team.

The functions take the cache root as an argument and know nothing about HTTP,
so `web/app.py` stays a thin layer and the tests need no server. `state` is an
opaque JSON object: only the frontend reads it.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

RECENT_FILENAME = "recent.json"
MAX_RECENT = 20
MAX_NAME_LENGTH = 80
UNTITLED = "Untitled"

_VIEW_ID_RE = re.compile(r"^[0-9a-f]{12}$")
_UNTITLED_RE = re.compile(rf"^{UNTITLED} (\d+)$")


class WorkspaceError(ValueError):
    """A request the store refuses: a bad id, a bad name, an unknown view."""


def _now() -> float:
    return time.time()


def ensure_cache(cache_root: Path) -> Path:
    """Create the cache folder. It ignores itself, so a project that does not
    list `.cdec_cache/` in its own `.gitignore` stays clean in `git status`."""
    cache_root.mkdir(parents=True, exist_ok=True)
    ignore = cache_root / ".gitignore"
    if not ignore.exists():
        ignore.write_text("# Local viewer cache. Do not commit.\n*\n", encoding="utf-8")
    return cache_root


def _read_json(path: Path, default: Any) -> Any:
    """A missing or damaged file reads as `default`: the cache must never stop
    the viewer."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write_json(path: Path, data: Any) -> None:
    """Write through a temporary file. The viewer saves a view every few
    hundred milliseconds, and a reader must never see half a document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ---------- recent paths ----------

def list_recent(cache_root: Path) -> list[dict[str, Any]]:
    """Recent paths, most recently used first."""
    data = _read_json(cache_root / RECENT_FILENAME, [])
    if not isinstance(data, list):
        return []
    entries = [
        e for e in data
        if isinstance(e, dict) and all(isinstance(e.get(k), str) for k in ("id", "path", "lang"))
    ]
    return sorted(entries, key=lambda e: e.get("last_used", 0), reverse=True)


def touch_recent(cache_root: Path, project_id: str, path: str, lang: str) -> None:
    """Move a path to the top of the recent list. Adds it when it is new."""
    ensure_cache(cache_root)
    kept = [e for e in list_recent(cache_root) if e["id"] != project_id]
    entry = {"id": project_id, "path": path, "lang": lang, "last_used": _now()}
    _write_json(cache_root / RECENT_FILENAME, [entry, *kept][:MAX_RECENT])


def forget_recent(cache_root: Path, project_id: str) -> None:
    """Remove a path from the recent list. Its views stay on disk, so the path
    shows them again when the user opens it later."""
    kept = [e for e in list_recent(cache_root) if e["id"] != project_id]
    _write_json(cache_root / RECENT_FILENAME, kept)


# ---------- views ----------

def _views_dir(cache_root: Path, project_id: str) -> Path:
    return cache_root / project_id / "views"


def _view_path(cache_root: Path, project_id: str, view_id: str) -> Path:
    # The id becomes a file name. Accept only what `create_view` produces.
    if not _VIEW_ID_RE.match(view_id):
        raise WorkspaceError(f"invalid view id: {view_id!r}")
    return _views_dir(cache_root, project_id) / f"{view_id}.json"


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise WorkspaceError("a view name must not be empty")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise WorkspaceError(f"a view name has at most {MAX_NAME_LENGTH} characters")
    return cleaned


def _meta(view: dict[str, Any]) -> dict[str, Any]:
    return {k: view[k] for k in ("id", "name", "created", "last_used")}


def _all_views(cache_root: Path, project_id: str) -> list[dict[str, Any]]:
    views = []
    for f in _views_dir(cache_root, project_id).glob("*.json"):
        data = _read_json(f, None)
        if isinstance(data, dict) and all(k in data for k in ("id", "name", "created", "last_used")):
            views.append(data)
    return views


def list_views(cache_root: Path, project_id: str) -> list[dict[str, Any]]:
    """The views of one path without their state, most recently used first."""
    views = sorted(_all_views(cache_root, project_id), key=lambda v: v["last_used"], reverse=True)
    return [_meta(v) for v in views]


def next_untitled(names: list[str]) -> str:
    """`Untitled N`, one above the highest number in use. A number is not used
    again after its view is deleted while a higher one exists, so two views
    never look like the same one."""
    used = [int(m.group(1)) for n in names if (m := _UNTITLED_RE.match(n))]
    return f"{UNTITLED} {max(used, default=0) + 1}"


def create_view(cache_root: Path, project_id: str, name: str | None = None) -> dict[str, Any]:
    """Create an empty view. Without a name it is the next `Untitled N`."""
    ensure_cache(cache_root)
    existing = [v["name"] for v in _all_views(cache_root, project_id)]
    now = _now()
    view: dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "name": _clean_name(name) if name is not None else next_untitled(existing),
        "created": now,
        "last_used": now,
        "state": None,
    }
    _write_json(_view_path(cache_root, project_id, view["id"]), view)
    return view


def read_view(cache_root: Path, project_id: str, view_id: str) -> dict[str, Any]:
    data = _read_json(_view_path(cache_root, project_id, view_id), None)
    if not isinstance(data, dict):
        raise WorkspaceError(f"unknown view: {view_id!r}")
    return data


def update_view(
    cache_root: Path,
    project_id: str,
    view_id: str,
    *,
    name: str | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rename a view, replace its state, or only mark it as used (no argument).
    Each call moves the view to the top of its list."""
    view = read_view(cache_root, project_id, view_id)
    if name is not None:
        view["name"] = _clean_name(name)
    if state is not None:
        view["state"] = state
    view["last_used"] = _now()
    _write_json(_view_path(cache_root, project_id, view_id), view)
    return view


def delete_view(cache_root: Path, project_id: str, view_id: str) -> None:
    path = _view_path(cache_root, project_id, view_id)
    if not path.is_file():
        raise WorkspaceError(f"unknown view: {view_id!r}")
    path.unlink()
