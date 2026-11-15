"""FastAPI backend for the code-constraints web viewer.

Endpoints are intentionally thin orchestrators over `code_constraints.core` + parsers. All
expensive artifacts (parsed XMIs) live on disk under `.cdec_cache/<project_id>/` so the
UI can reload freely. Every diagram is a JSON graph the client lays out; the server
renders no images. No auth — local use only.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from git import Commit, GitCommandError, InvalidGitRepositoryError, Repo
from git.exc import ODBError
from pydantic import BaseModel

from code_constraints.lint.config import REFERENCE_FILENAME, RULES_FILENAME

from code_constraints.core.diff import diff_projects
from code_constraints.core.editor_io import project_from_json, project_to_json
from code_constraints.core.model import SUPPORTED_LANGUAGES
from code_constraints.core.graph_model import (
    build_activity_change_list,
    build_activity_graph,
    build_change_list,
    build_class_graph,
    build_package_graph,
    build_sequence_change_list,
    build_sequence_graph,
)
from code_constraints.core.xmi_reader import read_project
from code_constraints.core.xmi_writer import build_tree as build_xmi_tree
from code_constraints.core.xmi_writer import write_project
from code_constraints.web import desktop, workspace

from lxml import etree

CACHE_ROOT = Path(".cdec_cache").resolve()

app = FastAPI(title="code-constraints", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- models ----------

class ProjectRegistration(BaseModel):
    path: str
    lang: str  # python | csharp | typescript | svelte


class DiffRequest(BaseModel):
    old_ref: str
    new_ref: str
    subpath: str = ""


class ProjectInfo(BaseModel):
    id: str
    path: str
    lang: str


class XmiInfo(BaseModel):
    id: str
    project_id: str


class ProposalInfo(BaseModel):
    """Latest architecture proposal pushed for a project.

    `seq` increments on every push so an open browser tab can poll
    `GET /api/projects/{id}/proposal` and hot-swap the diagram when it grows.
    """
    id: str  # xmi id of the annotated (proposal vs. baseline) diff
    project_id: str
    seq: int
    focus: list[str] = []


class DiagramListing(BaseModel):
    classes: bool
    packages: bool
    activities: list[str]
    sequences: list[str]


class GitInfo(BaseModel):
    """Git-tracking metadata about a project's path.

    `is_git=False` (with everything else None) means the path is not inside a
    git repo — the homepage hides the quick-diff card in that case.

    `repo_root` is the absolute path of the git working tree root and
    `subpath` is the project path expressed relative to it. If the project
    path IS the repo root, `subpath` is the empty string. Used by the
    quick-diff flow so the diff is scoped to just the registered project
    rather than the whole repo.
    """
    is_git: bool
    branch: Optional[str] = None
    head_sha: Optional[str] = None
    head_short: Optional[str] = None
    head_subject: Optional[str] = None
    parent_sha: Optional[str] = None
    parent_short: Optional[str] = None
    parent_subject: Optional[str] = None
    is_dirty: Optional[bool] = None
    repo_root: Optional[str] = None
    subpath: Optional[str] = None


# ---------- registry (in-memory; backed by per-project cache dirs on disk) ----------

class _Registry:
    def __init__(self) -> None:
        self._projects: dict[str, ProjectInfo] = {}
        self._xmis: dict[str, XmiInfo] = {}
        self._proposals: dict[str, ProposalInfo] = {}

    def register(self, info: ProjectInfo) -> None:
        self._projects[info.id] = info

    def project(self, project_id: str) -> ProjectInfo:
        if project_id not in self._projects:
            raise HTTPException(status_code=404, detail=f"unknown project {project_id}")
        return self._projects[project_id]

    def register_xmi(self, info: XmiInfo) -> None:
        self._xmis[info.id] = info

    def xmi(self, xmi_id: str) -> XmiInfo:
        if xmi_id not in self._xmis:
            raise HTTPException(status_code=404, detail=f"unknown xmi {xmi_id}")
        return self._xmis[xmi_id]

    def record_proposal(
        self, project_id: str, xmi_id: str, focus: list[str]
    ) -> ProposalInfo:
        prev = self._proposals.get(project_id)
        info = ProposalInfo(
            id=xmi_id,
            project_id=project_id,
            seq=(prev.seq + 1) if prev else 1,
            focus=focus,
        )
        self._proposals[project_id] = info
        return info

    def proposal(self, project_id: str) -> Optional[ProposalInfo]:
        return self._proposals.get(project_id)


_registry = _Registry()


def _project_cache(project_id: str) -> Path:
    p = CACHE_ROOT / project_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _xmi_path(xmi_id: str) -> Path:
    info = _registry.xmi(xmi_id)
    return _project_cache(info.project_id) / f"{xmi_id}.xmi"


_SUPPORTED_LANGS = SUPPORTED_LANGUAGES


def _parse(lang: str, path: Path):
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
    raise HTTPException(status_code=400, detail=f"unsupported language: {lang}")


# ---------- endpoints ----------

@app.post("/api/projects", response_model=ProjectInfo)
def register_project(body: ProjectRegistration) -> ProjectInfo:
    p = Path(body.path).expanduser().resolve()
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {p}")
    if body.lang not in _SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"unsupported language: {body.lang}")
    project_id = hashlib.sha1(f"{p}|{body.lang}".encode("utf-8")).hexdigest()[:12]
    info = ProjectInfo(id=project_id, path=str(p), lang=body.lang)
    _registry.register(info)
    return info


@app.get("/api/projects", response_model=list[ProjectInfo])
def list_projects() -> list[ProjectInfo]:
    return list(_registry._projects.values())


# ---------- workspace: recent paths and auto-saved views (.cdec_cache) ----------

# The home page detects while the user types, so the walk has a file budget.
_DETECT_MAX_FILES = 20_000


class DetectedLanguage(BaseModel):
    lang: Optional[str] = None
    is_dir: bool


class WorkspaceViewMeta(BaseModel):
    id: str
    name: str
    created: float
    last_used: float


class WorkspaceView(WorkspaceViewMeta):
    """`state` is the canvas state. Only the frontend reads it."""

    state: Optional[dict[str, Any]] = None


class WorkspaceViewUpdate(BaseModel):
    name: Optional[str] = None
    state: Optional[dict[str, Any]] = None


class RecentPath(BaseModel):
    id: str
    path: str
    lang: str
    last_used: float
    exists: bool
    views: list[WorkspaceViewMeta]


def _workspace_call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a store call. A request the store refuses is a client error."""
    try:
        return fn(CACHE_ROOT, *args, **kwargs)
    except workspace.WorkspaceError as exc:
        status = 404 if str(exc).startswith("unknown view") else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


def _touch_recent(info: ProjectInfo) -> None:
    workspace.touch_recent(CACHE_ROOT, info.id, info.path, info.lang)


@app.get("/api/detect-language", response_model=DetectedLanguage)
def detect_project_language(path: str) -> DetectedLanguage:
    """Suggest the language of the source tree at `path` for the home page.
    A path that is not a directory is not an error: the user is still typing."""
    from code_constraints.cli.detect import detect_language

    p = Path(path).expanduser()
    if not path.strip() or not p.is_dir():
        return DetectedLanguage(lang=None, is_dir=False)
    return DetectedLanguage(lang=detect_language(p, max_files=_DETECT_MAX_FILES), is_dir=True)


@app.get("/api/workspace", response_model=list[RecentPath])
def workspace_recent() -> list[RecentPath]:
    """Recently opened paths with their views, both most recently used first."""
    return [
        RecentPath(
            id=e["id"],
            path=e["path"],
            lang=e["lang"],
            last_used=e.get("last_used", 0),
            exists=Path(e["path"]).is_dir(),
            views=[WorkspaceViewMeta(**v) for v in workspace.list_views(CACHE_ROOT, e["id"])],
        )
        for e in workspace.list_recent(CACHE_ROOT)
    ]


@app.post("/api/workspace/recent/{project_id}", status_code=204)
def workspace_touch_recent(project_id: str) -> Response:
    """Mark a registered path as used now (a diff does not open a view)."""
    _touch_recent(_registry.project(project_id))
    return Response(status_code=204)


@app.delete("/api/workspace/recent/{project_id}", status_code=204)
def workspace_forget_recent(project_id: str) -> Response:
    workspace.forget_recent(CACHE_ROOT, project_id)
    return Response(status_code=204)


@app.get("/api/projects/{project_id}/workspace/views", response_model=list[WorkspaceViewMeta])
def workspace_list_views(project_id: str) -> list[WorkspaceViewMeta]:
    info = _registry.project(project_id)
    return [WorkspaceViewMeta(**v) for v in workspace.list_views(CACHE_ROOT, info.id)]


@app.post("/api/projects/{project_id}/workspace/views", response_model=WorkspaceView)
def workspace_create_view(project_id: str, body: Optional[WorkspaceViewUpdate] = None) -> WorkspaceView:
    """Create a view. Without a name it is the next `Untitled N`."""
    info = _registry.project(project_id)
    view = _workspace_call(workspace.create_view, info.id, body.name if body else None)
    _touch_recent(info)
    return WorkspaceView(**view)


@app.post("/api/projects/{project_id}/workspace/views/{view_id}/open", response_model=WorkspaceView)
def workspace_open_view(project_id: str, view_id: str) -> WorkspaceView:
    """Return a view with its state and mark it, and its path, as used now."""
    info = _registry.project(project_id)
    view = _workspace_call(workspace.update_view, info.id, view_id)
    _touch_recent(info)
    return WorkspaceView(**view)


@app.put("/api/projects/{project_id}/workspace/views/{view_id}", response_model=WorkspaceViewMeta)
def workspace_update_view(project_id: str, view_id: str, body: WorkspaceViewUpdate) -> WorkspaceViewMeta:
    """Rename a view and/or replace its state. The viewer calls this by itself
    while the user works."""
    info = _registry.project(project_id)
    view = _workspace_call(workspace.update_view, info.id, view_id, name=body.name, state=body.state)
    return WorkspaceViewMeta(**view)


@app.delete("/api/projects/{project_id}/workspace/views/{view_id}", status_code=204)
def workspace_delete_view(project_id: str, view_id: str) -> Response:
    info = _registry.project(project_id)
    _workspace_call(workspace.delete_view, info.id, view_id)
    return Response(status_code=204)


class LayerDependencies(BaseModel):
    """The `layer-dependencies` allow-matrix declared in the project's
    `.cdec/rules.yaml` (layer -> layers it may reference). Empty + source=None
    when no such rule (or no `.cdec/`) is found."""

    allow: dict[str, list[str]]
    source: Optional[str] = None


class ViewListing(BaseModel):
    name: str
    filename: str


_SAFE_VIEW_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,57}\.json$")


def _safe_view_filename(filename: str) -> bool:
    """Return True only for safe, single-component filenames (no path traversal)."""
    return (
        bool(_SAFE_VIEW_RE.match(filename))
        and "/" not in filename
        and "\\" not in filename
    )


def _find_cdec_dir(root: Path) -> Path:
    """Walk from `root` up to the first .git boundary looking for a `.cdec/` directory.
    If none is found, returns `root / '.cdec'` as the default (created on first write).
    Raises 400 when `root` is not a real directory (e.g. synthetic diff projects).
    """
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="project has no filesystem path")
    current = root.resolve()
    while True:
        candidate = current / ".cdec"
        if candidate.is_dir():
            return candidate
        if (current / ".git").exists():
            break
        if current.parent == current:
            break
        current = current.parent
    return root.resolve() / ".cdec"


def _find_rules_yaml(root: Path) -> Optional[Path]:
    """Locate `.cdec/rules.yaml` at `root` or walk up to an ancestor that has it
    (stopping at a `.git` boundary or the filesystem root)."""
    if not root.is_dir():
        return None
    current = root.resolve()
    while True:
        candidate = current / ".cdec" / RULES_FILENAME
        if candidate.is_file():
            return candidate
        if (current / ".git").exists():
            break
        if current.parent == current:
            break
        current = current.parent
    return None


@app.get("/api/projects/{project_id}/layers", response_model=LayerDependencies)
def layer_dependencies(project_id: str) -> LayerDependencies:
    """Expose the layer-dependency allow-matrix from the project's rules.yaml so
    the class diagram can show it when a `@layer` badge is clicked."""
    info = _registry.project(project_id)
    rules_path = _find_rules_yaml(Path(info.path))
    if rules_path is None:
        return LayerDependencies(allow={}, source=None)
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
    allow: dict[str, list[str]] = {}
    for entry in data.get("rules") or []:
        if isinstance(entry, dict) and entry.get("type") == "layer-dependencies":
            for key, vals in (entry.get("allow") or {}).items():
                allow[str(key)] = [str(v) for v in (vals or [])]
    return LayerDependencies(allow=allow, source=str(rules_path))


@app.get("/api/projects/{project_id}/views", response_model=list[ViewListing])
def list_views(project_id: str) -> list[ViewListing]:
    """List view files saved to the project's .cdec/views/ directory."""
    info = _registry.project(project_id)
    cdec_dir = _find_cdec_dir(Path(info.path))
    views_dir = cdec_dir / "views"
    if not views_dir.is_dir():
        return []
    results: list[ViewListing] = []
    for f in sorted(views_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name") or f.stem
        except Exception:
            name = f.stem
        results.append(ViewListing(name=name, filename=f.name))
    return results


@app.get("/api/projects/{project_id}/views/{filename}")
def get_view(project_id: str, filename: str) -> dict:
    """Return the raw JSON of a named view file."""
    if not _safe_view_filename(filename):
        raise HTTPException(status_code=400, detail=f"invalid filename: {filename!r}")
    info = _registry.project(project_id)
    cdec_dir = _find_cdec_dir(Path(info.path))
    path = cdec_dir / "views" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"view not found: {filename!r}")
    return json.loads(path.read_text(encoding="utf-8"))


@app.put("/api/projects/{project_id}/views/{filename}", status_code=204)
async def save_view(project_id: str, filename: str, request: Request) -> Response:
    """Write a view JSON to the project's .cdec/views/ directory."""
    if not _safe_view_filename(filename):
        raise HTTPException(status_code=400, detail=f"invalid filename: {filename!r}")
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    if body.get("schema") != "code-constraints/view@2":
        raise HTTPException(
            status_code=400,
            detail=(
                f"unrecognised schema {body.get('schema')!r}; "
                "expected 'code-constraints/view@2'"
            ),
        )
    if not isinstance(body.get("visible"), list):
        raise HTTPException(status_code=400, detail="'visible' must be a list")
    info = _registry.project(project_id)
    cdec_dir = _find_cdec_dir(Path(info.path))
    views_dir = cdec_dir / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    (views_dir / filename).write_text(
        json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return Response(status_code=204)


@app.delete("/api/projects/{project_id}/views/{filename}", status_code=204)
def delete_view(project_id: str, filename: str) -> Response:
    """Delete a view file from the project's .cdec/views/ directory."""
    if not _safe_view_filename(filename):
        raise HTTPException(status_code=400, detail=f"invalid filename: {filename!r}")
    info = _registry.project(project_id)
    cdec_dir = _find_cdec_dir(Path(info.path))
    path = cdec_dir / "views" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"view not found: {filename!r}")
    path.unlink()
    return Response(status_code=204)


class ReferenceResult(BaseModel):
    path: str


@app.put("/api/projects/{project_id}/reference", response_model=ReferenceResult)
async def set_reference(
    project_id: str,
    request: Request,
    kind: str = "goal",
    title: str = "",
    note: str = "",
) -> ReferenceResult:
    """Write raw XMI bytes (the current/edited diagram) to the project's
    `.cdec/reference.xmi`, after validating they parse as a Project. Used by the
    'Set as reference' button to seed or update the architecture baseline.

    A configured project also records the model in its history: as a `goal`
    (a target the code must reach) or as a `checkpoint` (the code as it is).
    """
    if kind not in ("goal", "checkpoint"):
        raise HTTPException(status_code=400, detail="kind must be goal or checkpoint")
    info = _registry.project(project_id)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty request body")
    # Validate the bytes parse as a real Project before overwriting the baseline.
    with tempfile.NamedTemporaryFile(suffix=".xmi", delete=False) as tmp:
        tmp.write(body)
        tmp_path = Path(tmp.name)
    try:
        model = read_project(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"not a valid XMI: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    # A comparison holds the classes of two models, the removed ones included.
    if any(c.status.value != "unchanged" for c in model.iter_classes()):
        raise HTTPException(
            status_code=400,
            detail="this diagram is a comparison of two models. Show one model with "
            "nothing to compare, then set it as the reference.",
        )
    cdec_dir = _find_cdec_dir(Path(info.path))
    cdec_dir.mkdir(parents=True, exist_ok=True)
    ref_path = cdec_dir / REFERENCE_FILENAME
    ref_path.write_bytes(body)
    if (cdec_dir / RULES_FILENAME).is_file():
        from code_constraints import journal

        default_title = "New goal" if kind == "goal" else "Reference re-snapshotted"
        journal.record_reference(cdec_dir, kind, title or default_title, ref_path, note=note)
    return ReferenceResult(path=str(ref_path))


@app.post("/api/projects/{project_id}/proposal", response_model=ProposalInfo)
async def push_proposal(
    project_id: str,
    request: Request,
    against: str = "source",
    focus: str = "",
) -> ProposalInfo:
    """Push a proposed target architecture (editor-JSON model) for review.

    Diffs the proposal (NEW side) against a baseline (OLD side) and registers
    the annotated result, so the viewer shows green = "the code still needs to
    grow this", red = "the proposal drops this" — the same orientation as
    `cdec reference show`. `against` picks the baseline:

    - `source` (default): the project's current parsed source tree
    - `reference`: the project's `.cdec/reference.xmi`
    - `none`: no diff; the proposal renders standalone

    Every push bumps a sequence number; an open viewer polls
    `GET /api/projects/{id}/proposal` and refreshes in place, which is what
    makes the agent → human review loop fluent (no new tabs per iteration).
    `focus` is an optional comma-separated list of qualified class names the
    viewer should pre-filter to.
    """
    info = _registry.project(project_id)
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    try:
        proposal_proj = project_from_json(data)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"could not build Project: {exc}"
        ) from exc

    if against == "source":
        source_dir = Path(info.path)
        if not source_dir.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"project path is not a directory: {info.path} "
                "(use against=none for synthetic projects)",
            )
        baseline = _parse(info.lang, source_dir)
    elif against == "reference":
        ref_path = _find_cdec_dir(Path(info.path)) / REFERENCE_FILENAME
        if not ref_path.is_file():
            raise HTTPException(status_code=400, detail=f"no reference XMI at {ref_path}")
        baseline = read_project(ref_path)
    elif against == "none":
        baseline = None
    else:
        raise HTTPException(
            status_code=400, detail=f"against must be source|reference|none, got {against!r}"
        )

    if baseline is not None:
        try:
            annotated = diff_projects(baseline, proposal_proj)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        annotated = proposal_proj

    xmi_id = uuid.uuid4().hex[:12]
    write_project(annotated, _project_cache(project_id) / f"{xmi_id}.xmi")
    _registry.register_xmi(XmiInfo(id=xmi_id, project_id=project_id))
    focus_list = [f.strip() for f in focus.split(",") if f.strip()]
    return _registry.record_proposal(project_id, xmi_id, focus_list)


@app.get("/api/projects/{project_id}/proposal", response_model=ProposalInfo)
def latest_proposal(project_id: str) -> ProposalInfo:
    """Latest proposal pushed for this project (404 if none yet). Viewers poll
    this and hot-swap the diagram when `seq` changes."""
    _registry.project(project_id)
    info = _registry.proposal(project_id)
    if info is None:
        raise HTTPException(status_code=404, detail="no proposal pushed yet")
    return info


@app.get("/api/projects/{project_id}/reference-model")
def reference_model(project_id: str) -> dict:
    """The project's `.cdec/reference.xmi` as editor-JSON. Used by the editor's
    "Compare vs reference" mode to load a baseline without a file upload."""
    info = _registry.project(project_id)
    ref_path = _find_cdec_dir(Path(info.path)) / REFERENCE_FILENAME
    if not ref_path.is_file():
        raise HTTPException(status_code=404, detail=f"no reference XMI at {ref_path}")
    try:
        proj = read_project(ref_path)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"could not parse reference XMI: {exc}"
        ) from exc
    return project_to_json(proj)


@app.post("/api/projects/{project_id}/parse", response_model=XmiInfo)
def parse_project_endpoint(project_id: str) -> XmiInfo:
    info = _registry.project(project_id)
    proj = _parse(info.lang, Path(info.path))
    xmi_id = uuid.uuid4().hex[:12]
    write_project(proj, _project_cache(project_id) / f"{xmi_id}.xmi")
    xmi_info = XmiInfo(id=xmi_id, project_id=project_id)
    _registry.register_xmi(xmi_info)
    return xmi_info


def _commit_subject(commit: Optional[Commit]) -> Optional[str]:
    """First line of a commit message, or None when the object is unavailable.

    A shallow clone knows HEAD's parent *hash* but does not have its object —
    `git clone --depth 1`, and every default `actions/checkout`, produce one.
    Reading `.message` triggers a lazy load that raises there, so the whole
    endpoint used to 500. The hash is still worth reporting, so only the
    subject degrades to None.
    """
    if commit is None:
        return None
    try:
        message = commit.message
    except (ValueError, ODBError):
        return None
    return message.splitlines()[0] if message else None


@app.get("/api/projects/{project_id}/git-info", response_model=GitInfo)
def git_info(project_id: str) -> GitInfo:
    """Summary of the project path's git state.

    Returns `is_git=False` if the path isn't inside a git repo — the homepage
    quick-diff card uses this to decide whether to offer "diff vs previous
    commit". Otherwise returns HEAD + parent metadata for the quick-diff and
    a `is_dirty` flag so the UI can warn the user that uncommitted changes
    won't appear in the diff.
    """
    info = _registry.project(project_id)
    try:
        repo = Repo(info.path, search_parent_directories=True)
    except InvalidGitRepositoryError:
        return GitInfo(is_git=False)

    branch: Optional[str] = None
    try:
        branch = repo.active_branch.name
    except TypeError:
        # Detached HEAD — not on a branch.
        branch = None

    head = repo.head.commit
    parent = head.parents[0] if head.parents else None
    repo_root = Path(repo.working_tree_dir).resolve() if repo.working_tree_dir else None
    project_path = Path(info.path).resolve()
    subpath = ""
    if repo_root is not None:
        try:
            rel = project_path.relative_to(repo_root)
            subpath = "" if str(rel) == "." else rel.as_posix()
        except ValueError:
            subpath = ""
    return GitInfo(
        is_git=True,
        branch=branch,
        head_sha=head.hexsha,
        head_short=head.hexsha[:10],
        head_subject=_commit_subject(head) or "",
        parent_sha=parent.hexsha if parent else None,
        parent_short=parent.hexsha[:10] if parent else None,
        parent_subject=_commit_subject(parent),
        is_dirty=repo.is_dirty(untracked_files=False),
        repo_root=str(repo_root) if repo_root else None,
        subpath=subpath,
    )


@app.get("/api/projects/{project_id}/refs", response_model=list[str])
def list_refs(project_id: str) -> list[str]:
    info = _registry.project(project_id)
    try:
        repo = Repo(info.path, search_parent_directories=True)
    except InvalidGitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=f"not a git repo: {info.path}") from exc
    refs: list[str] = []
    refs.extend(b.name for b in repo.branches)
    refs.extend(t.name for t in repo.tags)
    # also the last 10 commit hashes for convenience
    try:
        refs.extend(c.hexsha[:10] for c in list(repo.iter_commits(max_count=10)))
    except GitCommandError:
        pass
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for r in refs:
        if r not in seen:
            out.append(r)
            seen.add(r)
    return out


@app.post("/api/projects/{project_id}/diff", response_model=XmiInfo)
def diff_endpoint(project_id: str, body: DiffRequest) -> XmiInfo:
    """Diff two git refs and write an annotated XMI.

    Handles the common quick-diff case where the project sits in a subpath
    that didn't exist on one side of the diff (e.g. a newly-added directory):
    the missing side is treated as an empty Project of the same language,
    so the result shows everything as ADDED rather than 500-ing.
    """
    info = _registry.project(project_id)
    repo = Repo(info.path, search_parent_directories=True)
    with tempfile.TemporaryDirectory(prefix="cdec-diff-") as tmp:
        old_dir = _checkout(repo, body.old_ref, Path(tmp) / "old")
        new_dir = _checkout(repo, body.new_ref, Path(tmp) / "new")
        old_t = old_dir / body.subpath if body.subpath else old_dir
        new_t = new_dir / body.subpath if body.subpath else new_dir
        old_proj = _parse_or_empty(info.lang, old_t)
        new_proj = _parse_or_empty(info.lang, new_t)
        annotated = diff_projects(old_proj, new_proj)
        xmi_id = uuid.uuid4().hex[:12]
        write_project(annotated, _project_cache(project_id) / f"{xmi_id}.xmi")
    xmi_info = XmiInfo(id=xmi_id, project_id=project_id)
    _registry.register_xmi(xmi_info)
    return xmi_info


@app.post("/api/projects/diff-vs-xmi", response_model=XmiInfo)
async def diff_source_vs_xmi(
    reference_xmi: UploadFile = File(...),
    path: str = Form(...),
    lang: str = Form(...),
) -> XmiInfo:
    """Parse a source tree and diff it against an uploaded reference XMI.

    Treats the uploaded XMI as the OLD side and the live source as the NEW
    side. The reference XMI's `source_language` must match `lang`. Useful
    when you've checkpointed an earlier model snapshot and want to see how
    the current code has evolved against it.
    """
    if lang not in _SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"unsupported language: {lang}")
    source_dir = Path(path).expanduser().resolve()
    if not source_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {source_dir}")

    cache_root = CACHE_ROOT / "_uploaded"
    cache_root.mkdir(parents=True, exist_ok=True)
    ref_bytes = await reference_xmi.read()
    if not ref_bytes:
        raise HTTPException(status_code=400, detail="reference XMI must be non-empty")
    with tempfile.NamedTemporaryFile(
        suffix=".xmi", delete=False, dir=str(cache_root)
    ) as fh:
        fh.write(ref_bytes)
        ref_tmp = Path(fh.name)
    try:
        try:
            old_proj = read_project(ref_tmp)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"could not parse reference XMI: {exc}"
            ) from exc
        new_proj = _parse(lang, source_dir)
        try:
            annotated = diff_projects(old_proj, new_proj)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        ref_tmp.unlink(missing_ok=True)

    project_id = "u" + uuid.uuid4().hex[:11]
    ref_label = reference_xmi.filename or "reference.xmi"
    _registry.register(
        ProjectInfo(
            id=project_id,
            path=f"uploaded: {ref_label} → {source_dir}",
            lang=annotated.source_language,
        )
    )
    xmi_id = uuid.uuid4().hex[:12]
    write_project(annotated, _project_cache(project_id) / f"{xmi_id}.xmi")
    xmi_info = XmiInfo(id=xmi_id, project_id=project_id)
    _registry.register_xmi(xmi_info)
    return xmi_info


@app.post("/api/xmi/diff", response_model=XmiInfo)
async def diff_xmi_files(
    old_xmi: UploadFile = File(...),
    new_xmi: UploadFile = File(...),
) -> XmiInfo:
    """Diff two uploaded XMI files and write an annotated result.

    Useful when you have two XMIs produced separately (e.g. by `cdec parse`
    runs in CI) and don't have a single git repo to diff against. Both XMIs
    must declare the same `source_language`.

    The result is registered under a synthetic project so the existing
    diagram viewer endpoints (`/api/xmi/{id}/model`, `/changes`, …) work
    transparently. The synthetic project has a placeholder path and is NOT
    re-parseable (no source tree behind it).
    """
    # The extension chooses the codec, so a `.json` model file works too.
    old_tmp = await _save_upload(old_xmi, CACHE_ROOT / "_uploaded")
    new_tmp = await _save_upload(new_xmi, CACHE_ROOT / "_uploaded")
    try:
        old_proj = _load_model_file(old_tmp)
        new_proj = _load_model_file(new_tmp)
        try:
            annotated = diff_projects(old_proj, new_proj)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        old_tmp.unlink(missing_ok=True)
        new_tmp.unlink(missing_ok=True)

    # Register a synthetic project so the registry can later resolve the
    # XMI's project_id. We use a fresh id per upload so concurrent diffs
    # don't trample each other's state.
    project_id = "u" + uuid.uuid4().hex[:11]
    label_old = old_xmi.filename or "old.xmi"
    label_new = new_xmi.filename or "new.xmi"
    _registry.register(
        ProjectInfo(
            id=project_id,
            path=f"uploaded: {label_old} → {label_new}",
            lang=annotated.source_language,
        )
    )
    xmi_id = uuid.uuid4().hex[:12]
    write_project(annotated, _project_cache(project_id) / f"{xmi_id}.xmi")
    xmi_info = XmiInfo(id=xmi_id, project_id=project_id)
    _registry.register_xmi(xmi_info)
    return xmi_info


def _parse_or_empty(lang: str, path: Path):
    """Parse `path` if it exists; otherwise return an empty Project.

    Used for git diffs where one side may not contain the requested subpath
    (e.g. the directory was just added at HEAD and didn't exist at HEAD~1).
    """
    if not path.exists():
        from code_constraints.core.model import Project

        return Project(source_language=lang)  # type: ignore[arg-type]
    return _parse(lang, path)


def _require_local(request: Request) -> None:
    """Refuse a desktop action that does not come from this machine.

    The server has no login and answers any origin, so a web page the user has
    open in another tab can call it. Opening a window on the desktop is not
    something a remote page, or a remote client of `--host 0.0.0.0`, may ask
    for. A browser always sends `Origin` on a cross-site POST.
    """
    from urllib.parse import urlparse

    client = request.client.host if request.client else None
    origin = request.headers.get("origin")
    if not desktop.is_loopback(client) or (
        origin is not None and not desktop.is_loopback(urlparse(origin).hostname)
    ):
        raise HTTPException(
            status_code=403,
            detail="this action is available only from the machine that runs the viewer",
        )


@app.post("/api/xmi/{xmi_id}/nodes/{node_id}/{action}", status_code=204)
def node_desktop_action(
    xmi_id: str, node_id: str, action: str, request: Request, line: int = 0
) -> Response:
    """Show the source file of a class in the file manager (`reveal`) or open
    it in an editor (`open`). The client names a node of a parsed model, never
    a path: the file comes from the model and must be inside the project.
    `line` opens the file at that line in place of the line of the class: an
    issue of the check names a line in the body."""
    if action not in ("reveal", "open"):
        raise HTTPException(status_code=404, detail=f"unknown action: {action}")
    _require_local(request)
    info = _registry.project(_registry.xmi(xmi_id).project_id)
    proj = read_project(_xmi_path(xmi_id))
    cls = next((c for c in proj.iter_classes() if c.stable_id() == node_id), None)
    if cls is None:
        raise HTTPException(status_code=404, detail=f"unknown class: {node_id}")
    if cls.location is None:
        raise HTTPException(status_code=400, detail=f"no source file is recorded for {cls.name}")
    try:
        path = desktop.resolve_source_file(Path(info.path), cls.location.file)
        if action == "reveal":
            desktop.reveal(path)
        else:
            desktop.open_in_editor(path, line if line > 0 else cls.location.start_line)
    except desktop.DesktopError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(status_code=204)


@app.get("/api/xmi/{xmi_id}/diagrams", response_model=DiagramListing)
def list_diagrams(xmi_id: str) -> DiagramListing:
    proj = read_project(_xmi_path(xmi_id))
    return DiagramListing(
        classes=bool(list(proj.iter_classes())),
        packages=bool(proj.packages),
        activities=[a.name for a in proj.activities],
        sequences=[s.name for s in proj.sequences],
    )


@app.get("/api/xmi/{xmi_id}/model")
def xmi_model(xmi_id: str, diagram: str = "class", name: Optional[str] = None) -> dict:
    """JSON graph payload (nodes + edges) for an interactive canvas.

    Supported diagrams: class, package, activity, sequence.
    """
    proj = read_project(_xmi_path(xmi_id))
    if diagram == "class":
        return build_class_graph(proj)
    if diagram == "package":
        return build_package_graph(proj)
    if diagram == "activity":
        if not name:
            raise HTTPException(status_code=400, detail="activity diagram requires ?name=")
        try:
            return build_activity_graph(proj, name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if diagram == "sequence":
        if not name:
            raise HTTPException(status_code=400, detail="sequence diagram requires ?name=")
        try:
            return build_sequence_graph(proj, name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(
        status_code=400,
        detail=f"unknown diagram type: {diagram}",
    )


@app.get("/api/xmi/{xmi_id}/changes")
def xmi_changes(xmi_id: str, kind: str = "class") -> list[dict]:
    """Ordered change list for the diff walkthrough.

    `kind=class` (default) → one entry per affected class.
    `kind=activity` → one entry per affected activity (added/removed/changed),
    with member bullets for added/removed nodes and edges.
    `kind=sequence` → one entry per affected sequence, with bullets for
    added/removed lifelines and messages.
    Returns an empty list for parse-only XMIs.
    """
    proj = read_project(_xmi_path(xmi_id))
    if kind == "class":
        return build_change_list(proj)
    if kind == "activity":
        return build_activity_change_list(proj)
    if kind == "sequence":
        return build_sequence_change_list(proj)
    raise HTTPException(status_code=400, detail=f"unknown changes kind: {kind}")


@app.get("/api/xmi/{xmi_id}/source")
def xmi_source(xmi_id: str) -> FileResponse:
    return FileResponse(
        _xmi_path(xmi_id), media_type="application/xml", filename=f"{xmi_id}.xmi"
    )


# ---------- editor bridge: pure XMI <-> JSON converters, no on-disk state ----------

@app.post("/api/edit/from-xmi")
async def edit_from_xmi(file: UploadFile = File(...)) -> dict:
    """Parse an uploaded XMI file and return its Project as JSON.

    Stateless: the file isn't stored, no registry entry. The editor uses this
    both to open a downloaded .xmi and to bootstrap "Edit this parsed diagram"
    by re-uploading the XMI it just fetched from /api/xmi/{id}/source.
    """
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="XMI file must be non-empty")
    cache_root = CACHE_ROOT / "_uploaded"
    cache_root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        suffix=".xmi", delete=False, dir=str(cache_root)
    ) as fh:
        fh.write(body)
        tmp = Path(fh.name)
    try:
        try:
            proj = read_project(tmp)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"could not parse XMI: {exc}"
            ) from exc
        return project_to_json(proj)
    finally:
        tmp.unlink(missing_ok=True)


@app.post("/api/edit/model")
async def edit_model(request: Request, diagram: str = "class") -> dict:
    """Build the SvelteFlow graph for an in-progress editor draft.

    Takes the same JSON Project payload as `/api/edit/to-xmi`, runs it through
    `project_from_json`, then returns the result of `build_class_graph` (or
    package/activity/sequence depending on `diagram`). This is the same code
    path used by `/api/xmi/{id}/model` so view mode and edit mode produce
    identical graphs for equivalent models — no parallel TS implementation
    can drift from the canonical Python one.
    """
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    try:
        proj = project_from_json(data)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"could not build Project: {exc}"
        ) from exc
    if diagram == "class":
        return build_class_graph(proj)
    if diagram == "package":
        return build_package_graph(proj)
    raise HTTPException(
        status_code=400,
        detail=f"unsupported editor diagram type: {diagram}",
    )


@app.post("/api/edit/diff-model")
async def edit_diff_model(request: Request, diagram: str = "class") -> dict:
    """Build the SvelteFlow graph for an editor draft diffed against a baseline.

    Body: `{"old": <ProjectJSON>, "new": <ProjectJSON>}`. The result is the
    same graph shape as `/api/edit/model` but with diff statuses annotated, so
    the editor can show live added/removed/changed styling while the user (or
    an agent) reshapes the draft — simultaneous edit + diff preview.
    """
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict) or "old" not in data or "new" not in data:
        raise HTTPException(
            status_code=400, detail='payload must be {"old": {...}, "new": {...}}'
        )
    try:
        old_proj = project_from_json(data["old"])
        new_proj = project_from_json(data["new"])
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"could not build Project: {exc}"
        ) from exc
    try:
        annotated = diff_projects(old_proj, new_proj)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if diagram == "class":
        return build_class_graph(annotated)
    if diagram == "package":
        return build_package_graph(annotated)
    raise HTTPException(
        status_code=400,
        detail=f"unsupported editor diagram type: {diagram}",
    )


@app.post("/api/edit/to-xmi")
async def edit_to_xmi(request: Request) -> Response:
    """Serialise an editor-model JSON payload back to XMI 2.1 text.

    Returns the XMI as an attachment so the browser triggers a download.
    """
    try:
        data = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    try:
        proj = project_from_json(data)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"could not build Project: {exc}"
        ) from exc
    tree = build_xmi_tree(proj)
    xml_bytes = etree.tostring(
        tree, pretty_print=True, xml_declaration=True, encoding="UTF-8"
    )
    filename = data.get("download_name") or "diagram.xmi"
    if not isinstance(filename, str) or not filename.endswith(".xmi"):
        filename = "diagram.xmi"
    return Response(
        content=xml_bytes,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- helpers ----------

def _checkout(repo: Repo, ref: str, dest: Path) -> Path:
    """Extract the tree at `ref` into `dest`, without touching the working tree.

    A shallow clone resolves refs whose objects it does not actually have, so
    both the lookup and the archive can fail on history that was never
    fetched. That is the caller asking for something absent, not a server
    fault, so it answers 400 with the command that fixes it.
    """
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest.with_suffix(".tar")
    try:
        commit = repo.commit(ref)
        with archive.open("wb") as fh:
            repo.archive(fh, treeish=commit.hexsha, format="tar")
    except (GitCommandError, ODBError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                f"cannot read git ref {ref!r}: {exc}. If this is a shallow clone, "
                f"the older commits were never fetched — run `git fetch --unshallow`."
            ),
        ) from exc
    shutil.unpack_archive(str(archive), str(dest), format="tar")
    archive.unlink()
    return dest


# ---------- the journey: set up, rules, history ----------
#
# The guide, the rules page and the history page of the web app. Every endpoint
# here calls the same library code as `cdec check` and `cdec exceptions`, so a
# key or a count that the page shows is the one the CLI prints. The endpoints
# that write into `.cdec/` are local-only, like the desktop actions: a page in
# another browser tab must not be able to turn a rule off.

_GRANDFATHER_REASON = "Accepted when the rule was turned on."
_PREVIEW_LIMIT = 200


class HistoryEntry(BaseModel):
    id: str
    kind: str
    title: str
    note: str = ""
    created: str = ""
    author: str = ""
    commit: str = ""
    journey: str = ""
    reference: bool = False
    stats: dict[str, int] = {}
    rules: list[dict[str, str]] = []
    goal: str = ""
    distance: dict[str, int] = {}


class JourneyStatus(BaseModel):
    """What the guide needs to decide which step is next. Read from the files
    only: no parse and no check, so the page opens at once."""

    configured: bool
    config_dir: str
    language: Optional[str] = None
    source: Optional[str] = None
    journey: str = ""
    reference: bool = False
    rules: int = 0
    rules_editable: bool = True
    exceptions: int = 0
    locks: int = 0
    history: int = 0
    goals: int = 0
    checkpoints: int = 0
    goal: Optional[HistoryEntry] = None
    # The types of the rules that are on, e.g. `tag-conformance`.
    rule_types: list[str] = []
    # The shim file of the language, and True when the project has it.
    shim: str = ""
    shim_present: bool = False
    # Old per-concern files that `cdec init --migrate` folds into rules.yaml.
    legacy: list[str] = []
    error: str = ""


class JourneyInit(BaseModel):
    journey: str  # greenfield | brownfield


class RuleDraft(BaseModel):
    """A rule entry as YAML text (`yaml`) or as a mapping (`entry`)."""

    yaml: Optional[str] = None
    entry: Optional[dict[str, Any]] = None
    accept_existing: bool = False
    # A preview of a changed rule: the id of the rule that the draft replaces,
    # so its own id is not "taken".
    replaces: str = ""


class SeverityChange(BaseModel):
    severity: str


class AcceptRequest(BaseModel):
    keys: list[str]
    reason: str = ""


class CheckpointRequest(BaseModel):
    title: str
    note: str = ""


class FrameRequest(BaseModel):
    entry: str
    against: str = ""


def _configured_dir(info: ProjectInfo) -> Path:
    """The `.cdec/` folder of a project that has a `rules.yaml`, or 409."""
    rules_file = _find_rules_yaml(Path(info.path))
    if rules_file is None:
        raise HTTPException(
            status_code=409,
            detail="this project has no .cdec/rules.yaml. Create the project config first.",
        )
    return rules_file.parent


def _rules_editable(cfg_dir: Path) -> bool:
    """True when the rules are in `rules.yaml`. The tool never writes into
    `.cdec/rules/`."""
    from code_constraints.lint.config import ConfigError, available_rule_files

    try:
        return available_rule_files(cfg_dir) in ([], [cfg_dir / RULES_FILENAME])
    except ConfigError:
        return False


def _draft_entry(draft: Any) -> dict[str, Any]:
    """The rule entry of a draft. In YAML text it is one mapping, or a list with
    one mapping."""
    if not isinstance(draft, str):
        if draft.entry is not None:
            return draft.entry
        draft = draft.yaml or ""
    text = draft
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"not valid YAML: {exc}") from exc
    if isinstance(raw, list) and len(raw) == 1:
        raw = raw[0]
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="write one rule entry: `id:`, `type:`, …")
    return raw


def _raw_rule_entries(cfg_dir: Path) -> list[dict[str, Any]]:
    from code_constraints.core.rulesdoc import load_document
    from code_constraints.lint.config import rule_files

    out: list[dict[str, Any]] = []
    for path in rule_files(cfg_dir):
        out.extend(e for e in load_document(path).get("rules") or [] if isinstance(e, dict))
    return out


def _issue_json(issue: Any) -> dict[str, Any]:
    from dataclasses import asdict

    return {**asdict(issue), "key": issue.key}


def _journey_call(fn: Callable[[], Any]) -> Any:
    """Run library code. A problem in the project files is a client error."""
    from code_constraints.core.rulesdoc import RulesFileError
    from code_constraints.lint.config import ConfigError
    from code_constraints.lint.pipeline import PipelineError
    from code_constraints.waivers.store import WaiverFileError

    try:
        return fn()
    except (ConfigError, PipelineError, WaiverFileError, RulesFileError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}/journey", response_model=JourneyStatus)
def journey_status(project_id: str) -> JourneyStatus:
    from code_constraints import journal
    from code_constraints.core.rulesdoc import RulesFileError, load_document

    info = _registry.project(project_id)
    rules_file = _find_rules_yaml(Path(info.path)) if Path(info.path).is_dir() else None
    if rules_file is None:
        return JourneyStatus(configured=False, config_dir="")
    cfg_dir = rules_file.parent
    out = JourneyStatus(configured=True, config_dir=str(cfg_dir))
    try:
        document = load_document(rules_file)
    except RulesFileError as exc:
        out.error = str(exc)
        return out
    history = journal.entries(cfg_dir)
    goal = journal.open_goal(history)
    out.language = document.get("language")
    out.source = str(document.get("source") or "")
    out.journey = next((e.journey for e in history if e.journey), "")
    out.reference = (cfg_dir / REFERENCE_FILENAME).is_file()
    active = [r for r in journal.rules_in_force(cfg_dir, document) if r["severity"] != "off"]
    out.rules = len(active)
    out.rule_types = sorted({r["type"] for r in active})
    from code_constraints.cli.scaffold import _SHIM_TARGETS
    from code_constraints.lint.config import legacy_files

    out.shim = _SHIM_TARGETS.get(str(out.language), ("", ""))[1]
    out.shim_present = bool(out.shim) and any(
        (folder / out.shim).is_file() for folder in (cfg_dir.parent, Path(info.path))
    )
    out.legacy = [p.name for p in legacy_files(cfg_dir)]
    out.rules_editable = _rules_editable(cfg_dir)
    out.exceptions = len(document.get("exceptions") or [])
    out.locks = len(document.get("locks") or [])
    out.history = len(history)
    out.goals = sum(1 for e in history if e.kind == "goal")
    out.checkpoints = sum(1 for e in history if e.kind == "checkpoint")
    out.goal = HistoryEntry(**vars(goal)) if goal else None
    return out


@app.post("/api/projects/{project_id}/journey/init", response_model=JourneyStatus)
def journey_init(project_id: str, body: JourneyInit, request: Request) -> JourneyStatus:
    """`cdec init` for the open project: `.cdec/rules.yaml`, the reference
    snapshot and the first history entry. The folder goes to the root of the
    git repository when there is one, where `cdec check` looks for it."""
    import os

    from code_constraints.cli.scaffold import ScaffoldError, init_cdec_config

    _require_local(request)
    info = _registry.project(project_id)
    if body.journey not in ("greenfield", "brownfield"):
        raise HTTPException(status_code=400, detail="journey must be greenfield or brownfield")
    source = Path(info.path)
    if not source.is_dir():
        raise HTTPException(status_code=400, detail="project has no filesystem path")
    if _find_rules_yaml(source) is not None:
        raise HTTPException(status_code=409, detail="this project has a .cdec/rules.yaml already")
    root = next((p for p in (source, *source.parents) if (p / ".git").exists()), source)
    try:
        init_cdec_config(
            root / ".cdec",
            info.lang,
            Path(os.path.relpath(source, root)),
            force=False,
            parse_from=source,
            journey=body.journey,
        )
    except ScaffoldError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return journey_status(project_id)


@app.get("/api/rule-starters")
def rule_starters() -> dict[str, Any]:
    """The rule gallery: a starter entry for every rule type, as YAML text."""
    from code_constraints.core.rulesdoc import render_rule
    from code_constraints.lint.starters import GROUPS, starters

    return {
        "groups": [{"id": g, "title": t, "summary": s} for g, t, s in GROUPS],
        "starters": [
            {**s, "yaml": render_rule(s["entry"], "")}
            for s in starters()
        ],
    }


@app.get("/api/projects/{project_id}/rules")
def rules_overview(
    project_id: str, base_ref: str = "", subject: str = "code", baseline: str = "reference"
) -> dict[str, Any]:
    """Every rule entry with its open and accepted issues: one run of the
    check, with the same keys that `cdec check` prints.

    `subject` is the model that the rules read: the code, or a model reference
    (a target model, a history entry, a file). `baseline` is the model that the
    diff rules compare with: the reference, a history entry, a file
    (`cdec check --reference`) or `git:<ref>` (`cdec check --base-ref`).
    `base_ref` is the older spelling of `baseline=git:<ref>`."""
    from code_constraints.core.rulesdoc import render_rule
    from code_constraints.waivers import CollectOptions, collect_issues

    info = _registry.project(project_id)
    cfg_dir = _configured_dir(info)
    if baseline.startswith("git:"):
        base_ref = baseline[4:]
    options = CollectOptions(base_ref=base_ref or None, repo=cfg_dir.parent)
    if not base_ref and baseline != "reference":
        options.reference = _model_file(info, baseline)
    if subject != "code":
        options.model = _model_of(info, subject)
    # The exceptions are accepted for the code against the reference.
    default_inputs = subject == "code" and baseline == "reference" and not base_ref
    try:
        collected = _journey_call(lambda: collect_issues(cfg_dir, options))
    except (InvalidGitRepositoryError, GitCommandError, ODBError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"cannot read git ref {base_ref!r}: {exc}") from exc
    # An exception is stale when its rule ran and did not report the issue.
    # Against another baseline the issues differ, so nothing is called stale.
    live = {i.key for i in collected.issues}
    exceptions = [
        {
            "key": w.key,
            "rule": w.rule,
            "qualified_name": w.qualified_name,
            "detail": w.detail,
            "reason": w.reason,
            "added": w.added,
            "added_by": w.added_by,
            "stale": default_inputs and w.engine in collected.engines_ran and w.key not in live,
        }
        for w in collected.store.waivers
    ]
    skipped = dict(collected.skipped)
    rules = []
    for entry in _journey_call(lambda: _raw_rule_entries(cfg_dir)):
        rule_id = str(entry.get("id", ""))
        severity = entry.get("severity", "error")
        mine = [i for i in collected.issues if i.rule_id == rule_id]
        rules.append(
            {
                "id": rule_id,
                "type": str(entry.get("type", "")),
                # YAML reads a bare `off` as False.
                "severity": "off" if severity is False else str(severity),
                "open": sum(1 for i in mine if not i.waived),
                "accepted": sum(1 for i in mine if i.waived),
                "skipped": skipped.get(rule_id, ""),
                "yaml": render_rule(entry, ""),
                "entry": entry,
            }
        )
    return {
        "rules_file": str(cfg_dir / RULES_FILENAME),
        "editable": _rules_editable(cfg_dir),
        "default_inputs": default_inputs,
        "rules": rules,
        "issues": [_issue_json(i) for i in collected.issues],
        "exceptions": exceptions,
    }


def _build_draft(cfg_dir: Path, draft: Any) -> tuple[dict[str, Any], Any]:
    from code_constraints.lint.config import build_rule

    entry = _draft_entry(draft)
    taken = {str(e.get("id")) for e in _raw_rule_entries(cfg_dir)}
    taken.discard(getattr(draft, "replaces", ""))
    return entry, build_rule(entry, taken)


@app.post("/api/projects/{project_id}/rules/preview")
def rule_preview(project_id: str, body: RuleDraft) -> dict[str, Any]:
    """Run one draft rule against the code of today and write nothing. The
    page shows the result before the rule is turned on."""
    from code_constraints.waivers import CollectOptions, collect_issues

    cfg_dir = _configured_dir(_registry.project(project_id))
    _entry, rule = _journey_call(lambda: _build_draft(cfg_dir, body))
    if rule is None:
        raise HTTPException(status_code=400, detail="the entry has `severity: off`; it reports nothing")
    collected = _journey_call(lambda: collect_issues(cfg_dir, CollectOptions(rules=[rule])))
    open_issues = collected.open_issues()
    return {
        "open": len(open_issues),
        "accepted": len(collected.issues) - len(open_issues),
        "skipped": next((reason for _, reason in collected.skipped), ""),
        "issues": [_issue_json(i) for i in open_issues[:_PREVIEW_LIMIT]],
    }


@app.post("/api/projects/{project_id}/rules")
def rule_add(project_id: str, body: RuleDraft, request: Request) -> dict[str, Any]:
    """Add a rule to `rules.yaml`. With `accept_existing`, the issues that the
    rule reports today become exceptions, so only new ones fail."""
    from code_constraints.core.rulesdoc import append_rule
    from code_constraints.waivers import collect_issues
    from code_constraints.waivers.ops import allow_keys
    from code_constraints.waivers.store import save_waivers

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    if not _rules_editable(cfg_dir):
        raise HTTPException(
            status_code=409,
            detail="the rules of this project are in .cdec/rules/, and cdec does not "
            "write there. Copy the entry into one of those files.",
        )
    entry, _rule = _journey_call(lambda: _build_draft(cfg_dir, body))
    _journey_call(lambda: append_rule(cfg_dir / RULES_FILENAME, entry))
    accepted = 0
    if body.accept_existing:
        collected = _journey_call(lambda: collect_issues(cfg_dir))
        keys = [
            i.key
            for i in collected.issues
            if i.rule_id == entry["id"] and i.waivable and not i.waived
        ]
        result = allow_keys(collected.store, collected, keys, reason=_GRANDFATHER_REASON)
        if result.changed:
            save_waivers(cfg_dir, collected.store)
        accepted = len(result.allowed)
    _record_rule_change(cfg_dir, f"Rule {entry['id']} turned on")
    return {"id": entry["id"], "accepted": accepted}


@app.put("/api/projects/{project_id}/rules/{rule_id}", status_code=204)
def rule_set_severity(
    project_id: str, rule_id: str, body: SeverityChange, request: Request
) -> Response:
    from code_constraints.core.rulesdoc import set_rule_severity

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    if not _rules_editable(cfg_dir):
        raise HTTPException(
            status_code=409, detail="the rules are in .cdec/rules/; change the file by hand"
        )
    _journey_call(lambda: set_rule_severity(cfg_dir / RULES_FILENAME, rule_id, body.severity))
    _record_rule_change(cfg_dir, f"Rule {rule_id}: severity {body.severity}")
    return Response(status_code=204)


@app.post("/api/projects/{project_id}/exceptions")
def exceptions_allow(project_id: str, body: AcceptRequest, request: Request) -> dict[str, Any]:
    """`cdec exceptions allow` for the keys the page names."""
    from code_constraints.waivers import collect_issues
    from code_constraints.waivers.ops import allow_keys
    from code_constraints.waivers.store import save_waivers

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    collected = _journey_call(lambda: collect_issues(cfg_dir))
    result = allow_keys(collected.store, collected, body.keys, reason=body.reason.strip())
    if result.changed:
        save_waivers(cfg_dir, collected.store)
    return {
        "allowed": len(result.allowed),
        "refused": [{"key": k, "reason": why} for k, why in result.refused],
        "unknown": list(result.unknown),
    }


@app.get("/api/projects/{project_id}/history", response_model=list[HistoryEntry])
def history_list(project_id: str) -> list[HistoryEntry]:
    from code_constraints import journal

    info = _registry.project(project_id)
    rules_file = _find_rules_yaml(Path(info.path)) if Path(info.path).is_dir() else None
    if rules_file is None:
        return []
    return [HistoryEntry(**vars(e)) for e in journal.entries(rules_file.parent)]


@app.post("/api/projects/{project_id}/history", response_model=HistoryEntry)
def history_checkpoint(project_id: str, body: CheckpointRequest, request: Request) -> HistoryEntry:
    """Record a checkpoint: the model of the code as it is now."""
    from code_constraints import journal
    from code_constraints.lint.config import load_project_config

    _require_local(request)
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="give the checkpoint a title")
    cfg_dir = _configured_dir(_registry.project(project_id))
    cfg = _journey_call(lambda: load_project_config(cfg_dir))
    entry = journal.record(
        cfg_dir, "checkpoint", body.title, _parse(cfg.language, cfg.source), note=body.note
    )
    if entry is None:
        raise HTTPException(
            status_code=409, detail="the history is off (`history: false` in rules.yaml)"
        )
    return HistoryEntry(**vars(entry))


# (project id, entry, against) -> xmi id. An entry never changes, so a frame
# that was built once is valid until the server stops.
_history_frames: dict[tuple[str, str, str], str] = {}


@app.post("/api/projects/{project_id}/history/frame", response_model=XmiInfo)
def history_frame(project_id: str, body: FrameRequest) -> XmiInfo:
    """One frame of the history as a diagram: the model of `entry`, with the
    diff colours of the change from `against` when that is given."""
    from code_constraints import journal

    cfg_dir = _configured_dir(_registry.project(project_id))
    cache_key = (project_id, body.entry, body.against)
    if cache_key in _history_frames:
        return _registry.xmi(_history_frames[cache_key])
    # The ids come from the folder listing, so a request cannot name a path.
    known = {e.id for e in journal.entries(cfg_dir)}
    for entry_id in filter(None, (body.entry, body.against)):
        if entry_id not in known:
            raise HTTPException(status_code=404, detail=f"unknown history entry: {entry_id}")
    model = journal.load_model(cfg_dir, body.entry)
    if body.against:
        try:
            model = diff_projects(journal.load_model(cfg_dir, body.against), model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    xmi_id = uuid.uuid4().hex[:12]
    write_project(model, _project_cache(project_id) / f"{xmi_id}.xmi")
    xmi_info = XmiInfo(id=xmi_id, project_id=project_id)
    _registry.register_xmi(xmi_info)
    _history_frames[cache_key] = xmi_id
    return xmi_info


# ---------- the journey: every other task of the CLI ----------
#
# The web app is the one place for a `cdec` task. Each endpoint below is one
# CLI action with the same library call behind it: edit and remove a rule,
# withdraw and prune exceptions, compare the code with the reference, close a
# goal, record and re-baseline locks, write a tag, copy the shim, write the CI
# scripts, fold the legacy files in.


class RuleEntryText(BaseModel):
    """A rule entry as YAML text or as a mapping. The form of the page works
    on the mapping; its YAML view works on the text."""

    yaml: Optional[str] = None
    entry: Optional[dict[str, Any]] = None


class KeysRequest(BaseModel):
    keys: list[str]


class SnapshotRequest(BaseModel):
    title: str = ""
    note: str = ""


class LockUpdate(BaseModel):
    force: bool = False
    targets: list[str] = []


class TagSnippetRequest(BaseModel):
    lang: str
    tag: str
    values: dict[str, str] = {}


def _editable_dir(project_id: str, request: Request) -> Path:
    """The `.cdec/` folder for an edit of the `rules:` list, or 403/409."""
    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    if not _rules_editable(cfg_dir):
        raise HTTPException(
            status_code=409,
            detail="the rules of this project are in .cdec/rules/, and cdec does not "
            "write there. Change the file by hand.",
        )
    return cfg_dir


def _project_config(cfg_dir: Path) -> Any:
    from code_constraints.lint.config import load_project_config

    return _journey_call(lambda: load_project_config(cfg_dir))


@app.post("/api/rule-entry")
def rule_entry_convert(body: RuleEntryText) -> dict[str, Any]:
    """Give a rule entry back in both forms: the mapping and the YAML text."""
    from code_constraints.core.rulesdoc import render_rule

    entry = body.entry if body.entry is not None else _draft_entry(body.yaml or "")
    return {"entry": entry, "yaml": render_rule(entry, "")}


@app.put("/api/projects/{project_id}/rules/{rule_id}/entry", status_code=204)
def rule_replace(project_id: str, rule_id: str, body: RuleDraft, request: Request) -> Response:
    """Write a changed entry in place of the rule `rule_id`."""
    from code_constraints.core.rulesdoc import replace_rule
    from code_constraints.lint.config import build_rule

    cfg_dir = _editable_dir(project_id, request)
    entry = _draft_entry(body)
    taken = {str(e.get("id")) for e in _raw_rule_entries(cfg_dir)} - {rule_id}
    _journey_call(lambda: build_rule(entry, taken))
    _journey_call(lambda: replace_rule(cfg_dir / RULES_FILENAME, rule_id, entry))
    _record_rule_change(cfg_dir, f"Rule {rule_id} changed")
    return Response(status_code=204)


@app.delete("/api/projects/{project_id}/rules/{rule_id}", status_code=204)
def rule_remove(project_id: str, rule_id: str, request: Request) -> Response:
    from code_constraints.core.rulesdoc import remove_rule

    cfg_dir = _editable_dir(project_id, request)
    _journey_call(lambda: remove_rule(cfg_dir / RULES_FILENAME, rule_id))
    _record_rule_change(cfg_dir, f"Rule {rule_id} removed")
    return Response(status_code=204)


@app.delete("/api/projects/{project_id}/exceptions")
def exceptions_remove(project_id: str, body: KeysRequest, request: Request) -> dict[str, Any]:
    """`cdec exceptions remove`: the issues fail the check again."""
    from code_constraints.waivers import load_waivers
    from code_constraints.waivers.ops import remove_keys
    from code_constraints.waivers.store import save_waivers

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    store = _journey_call(lambda: load_waivers(cfg_dir))
    result = remove_keys(store, body.keys)
    if result.changed:
        save_waivers(cfg_dir, store)
    return {"removed": len(result.removed)}


@app.post("/api/projects/{project_id}/exceptions/prune")
def exceptions_prune(project_id: str, request: Request) -> dict[str, Any]:
    """`cdec exceptions prune`: drop the exceptions whose issue is gone."""
    from code_constraints.waivers import collect_issues
    from code_constraints.waivers.ops import prune
    from code_constraints.waivers.store import save_waivers

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    collected = _journey_call(lambda: collect_issues(cfg_dir))
    stale = prune(collected.store, collected)
    if stale:
        save_waivers(cfg_dir, collected.store)
    return {"removed": len(stale)}


@app.post("/api/projects/{project_id}/reference/compare", response_model=XmiInfo)
def reference_compare(project_id: str) -> XmiInfo:
    """`cdec reference show`: the code against the reference, as a diagram.
    The code is the old side, so green is what the code must still build."""
    cfg_dir = _configured_dir(_registry.project(project_id))
    cfg = _project_config(cfg_dir)
    if not cfg.reference_path.is_file():
        raise HTTPException(status_code=409, detail=f"no reference model at {cfg.reference_path}")
    from code_constraints.core.model_io import load_model

    try:
        annotated = diff_projects(_parse(cfg.language, cfg.source), load_model(cfg.reference_path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    xmi_id = uuid.uuid4().hex[:12]
    write_project(annotated, _project_cache(project_id) / f"{xmi_id}.xmi")
    xmi_info = XmiInfo(id=xmi_id, project_id=project_id)
    _registry.register_xmi(xmi_info)
    return xmi_info


@app.post("/api/projects/{project_id}/reference/snapshot")
def reference_snapshot(project_id: str, body: SnapshotRequest, request: Request) -> dict[str, Any]:
    """`cdec check --automatic-exceptions reference`: the code as it is becomes
    the reference, and the history records a checkpoint. An open goal closes."""
    from code_constraints import journal
    from code_constraints.lint.pipeline import snapshot_reference

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    cfg = _project_config(cfg_dir)
    project = snapshot_reference(cfg.source, cfg.language, cfg.reference_path)
    entry = journal.record_reference(
        cfg_dir,
        "checkpoint",
        body.title.strip() or "Reference re-snapshotted",
        cfg.reference_path,
        note=body.note,
    )
    return {
        "path": str(cfg.reference_path),
        "classes": sum(1 for _ in project.iter_classes()),
        "history": entry.id if entry else "",
    }


def _lock_rule(cfg_dir: Path) -> Any:
    """The `implementation-locks` rule that is on, or None."""
    from code_constraints.lint.config import load_rules

    rules = _journey_call(lambda: load_rules(cfg_dir)).of_type("implementation-locks")
    return rules[0] if rules else None


@app.get("/api/projects/{project_id}/locks")
def locks_overview(project_id: str) -> dict[str, Any]:
    """`cdec locks`: every element under lock, with the state of its digest."""
    from code_constraints.lock import (
        LockOptions,
        UnsupportedLockLanguage,
        check_locks,
        collect_targets,
        load_locks,
    )
    from code_constraints.lock.engine import is_locked_target

    cfg_dir = _configured_dir(_registry.project(project_id))
    cfg = _project_config(cfg_dir)
    rule = _lock_rule(cfg_dir)
    options = rule.lock_options() if rule else LockOptions()
    out: dict[str, Any] = {"rule": rule.rule_id if rule else "", "supported": True, "targets": []}
    try:
        found = collect_targets(cfg.source, cfg.language, options)
        entries = load_locks(cfg_dir)
        report = check_locks(cfg.source, cfg.language, entries, options)
    except UnsupportedLockLanguage as exc:
        return {**out, "supported": False, "reason": str(exc)}
    problems = {v.target: v for v in report.violations}
    seen: set[str] = set()
    for target in found:
        if not is_locked_target(target, options.patterns):
            continue
        seen.add(target.target)
        entry = entries.get(target.target)
        problem = problems.get(target.target)
        out["targets"].append(
            {
                "target": target.target,
                "kind": target.kind,
                "file": target.file,
                "line": target.line,
                "reason": target.reason or (entry.reason if entry else ""),
                # `new`: a tag with no recorded digest yet.
                "state": problem.kind if problem else ("ok" if entry else "new"),
                "message": problem.message if problem else "",
                "locked_at": entry.locked_at if entry else "",
                "locked_by": entry.locked_by if entry else "",
            }
        )
    # A recorded lock whose element is gone, or lost its tag.
    for name, problem in problems.items():
        if name not in seen:
            entry = entries.get(name)
            out["targets"].append(
                {
                    "target": name, "kind": entry.kind if entry else "", "file": problem.file,
                    "line": problem.line, "reason": entry.reason if entry else "",
                    "state": problem.kind, "message": problem.message,
                    "locked_at": entry.locked_at if entry else "",
                    "locked_by": entry.locked_by if entry else "",
                }
            )
    return out


@app.post("/api/projects/{project_id}/locks")
def locks_update(project_id: str, body: LockUpdate, request: Request) -> dict[str, Any]:
    """`cdec check --automatic-exceptions locks [--force] [--target …]`.

    Without `force` it only records digests for new locks. With `force` it
    accepts a change to frozen code, so the page names the targets."""
    from typing import cast

    from code_constraints.core.model import Project, SourceLanguage
    from code_constraints.lint.rules.base import RuleContext, RuleSkipped

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    cfg = _project_config(cfg_dir)
    rule = _lock_rule(cfg_dir)
    if rule is None:
        raise HTTPException(
            status_code=409,
            detail="no `implementation-locks` rule is on. Turn the rule on first.",
        )
    if body.force and not body.targets:
        raise HTTPException(
            status_code=400, detail="name the elements whose change you accept"
        )
    ctx = RuleContext(
        project=Project(source_language=cast(SourceLanguage, cfg.language)),
        has_diff=False,
        source=cfg.source,
        language=cfg.language,
        config_dir=cfg_dir,
        reference_path=cfg.reference_path,
    )
    try:
        lines = rule.accept_current_state(ctx, force=body.force, only=body.targets)
    except RuleSkipped as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"lines": [line.strip() for line in lines]}


@app.get("/api/tags")
def tag_catalog(lang: str) -> dict[str, Any]:
    """The constraint tags of one language, for the tag wizard."""
    from code_constraints.core.rules import RULE_CATALOG
    from code_constraints.core.tag_syntax import ENFORCED_BY, TAG_LANGUAGES

    if lang not in TAG_LANGUAGES:
        return {"supported": False, "tags": []}
    return {
        "supported": True,
        "tags": [
            {
                "id": spec.id,
                "summary": spec.summary,
                "targets": sorted(spec.targets),
                "params": list(spec.params),
                "enforced_by": ENFORCED_BY[spec.enforcement],
            }
            for spec in RULE_CATALOG.values()
        ],
    }


@app.post("/api/tags/snippet")
def tag_snippet_endpoint(body: TagSnippetRequest) -> dict[str, str]:
    from code_constraints.core.tag_syntax import tag_snippet

    try:
        return tag_snippet(body.tag, body.lang, body.values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/{project_id}/shims")
def shims_copy(project_id: str, request: Request) -> dict[str, Any]:
    """`cdec update-assets --no-agents`: copy the shim file into the project."""
    from code_constraints.cli.scaffold import ScaffoldError, copy_shims

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    cfg = _project_config(cfg_dir)
    try:
        written = copy_shims(cfg_dir.parent, cfg.language, force=True)
    except ScaffoldError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"written": [str(p) for p in written]}


@app.post("/api/projects/{project_id}/ci-scripts")
def ci_scripts(project_id: str, request: Request) -> dict[str, Any]:
    """Write `cdec-ci.sh` and `cdec-ci.bat` into the project root."""
    from code_constraints.cli.scaffold import write_ci_scripts
    from code_constraints.core.rulesdoc import load_document

    _require_local(request)
    cfg_dir = _configured_dir(_registry.project(project_id))
    cfg = _project_config(cfg_dir)
    source = str(load_document(cfg_dir / RULES_FILENAME).get("source") or ".")
    written = write_ci_scripts(cfg_dir.parent, cfg.language, Path(source))
    return {"written": [str(p) for p in written]}


@app.post("/api/projects/{project_id}/journey/migrate", response_model=JourneyStatus)
def journey_migrate(project_id: str, request: Request) -> JourneyStatus:
    """`cdec init --migrate`: fold config.yaml / baseline.yaml / locks.yaml
    into rules.yaml."""
    from code_constraints.cli.scaffold import ScaffoldError, migrate_cdec_config

    _require_local(request)
    info = _registry.project(project_id)
    cfg_dir = _find_cdec_dir(Path(info.path))
    try:
        migrate_cdec_config(cfg_dir)
    except ScaffoldError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return journey_status(project_id)


# ---------- one entry point: the start folder, the folders, the models ----------
#
# `cdec ui` starts with no argument. The home page offers the folder that the
# command ran in, the recent paths, a folder browser and a model file. After
# that, every page names a model the same way, with a model reference:
#
#     code             the source tree, parsed now
#     reference        .cdec/reference.xmi (the goal, when one is open)
#     history:<id>     the model of one history entry
#     git:<ref>        the source tree at a git revision
#     upload:<token>   a model file that the user opened in this session


class StartInfo(BaseModel):
    cwd: str
    # The source folder and the language to open, from rules.yaml when the
    # folder is a cdec project, else the folder itself and a detection.
    path: str
    lang: Optional[str] = None
    configured: bool


class FolderEntry(BaseModel):
    name: str
    path: str
    project: bool


class FolderListing(BaseModel):
    path: str
    parent: Optional[str] = None
    roots: list[str]
    folders: list[FolderEntry]


class ModelChoice(BaseModel):
    ref: str
    label: str
    kind: str


class ShowRequest(BaseModel):
    show: str = "code"
    against: str = ""


_MAX_FOLDERS = 500
# (project id, token) -> (file, name). The files are in the cache folder.
_uploads: dict[tuple[str, str], tuple[Path, str]] = {}


@app.get("/api/start", response_model=StartInfo)
def start_info(request: Request) -> StartInfo:
    """The folder that `cdec ui` ran in: the first choice of the home page."""
    from code_constraints.cli.detect import detect_language
    from code_constraints.lint.config import ConfigError, load_project_config

    _require_local(request)
    cwd = Path.cwd()
    rules_file = _find_rules_yaml(cwd)
    if rules_file is not None:
        try:
            cfg = load_project_config(rules_file.parent)
            return StartInfo(
                cwd=str(cwd), path=str(cfg.source), lang=cfg.language, configured=True
            )
        except ConfigError:
            pass  # A broken rules.yaml: the guide of the project names the fault.
    return StartInfo(
        cwd=str(cwd),
        path=str(cwd),
        lang=detect_language(cwd, max_files=_DETECT_MAX_FILES),
        configured=rules_file is not None,
    )


@app.get("/api/fs", response_model=FolderListing)
def list_folders(request: Request, path: str = "") -> FolderListing:
    """The folders in `path`, for the folder browser of the home page. With no
    path: the folder that the viewer runs in. It lists names only, and only
    for this machine: the tree of a disk is not for a page in another tab."""
    import os

    _require_local(request)
    folder = Path(path).expanduser() if path.strip() else Path.cwd()
    if not folder.is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {folder}")
    folder = folder.resolve()
    try:
        children = sorted(
            (p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name.lower(),
        )
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"cannot read {folder}: {exc}") from exc
    listdrives = getattr(os, "listdrives", None)  # Windows, Python 3.12+
    roots = [*(listdrives() if listdrives else [folder.anchor]), str(Path.home())]
    return FolderListing(
        path=str(folder),
        parent=None if folder.parent == folder else str(folder.parent),
        roots=roots,
        folders=[
            FolderEntry(name=p.name, path=str(p), project=(p / ".cdec" / RULES_FILENAME).is_file())
            for p in children[:_MAX_FOLDERS]
        ],
    )


async def _save_upload(upload: UploadFile, folder: Path) -> Path:
    """Write an uploaded model file into the cache. The extension chooses the
    codec, so only the two known ones pass."""
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in (".xmi", ".json"):
        raise HTTPException(status_code=400, detail="a model file is a .xmi or a .json file")
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail="the model file is empty")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex[:12]}{suffix}"
    path.write_bytes(data)
    return path


def _load_model_file(path: Path) -> Any:
    from code_constraints.core.model_io import load_model

    try:
        return load_model(path)
    except Exception as exc:  # malformed XML or JSON of any kind
        raise HTTPException(status_code=400, detail=f"cannot read the model file: {exc}") from exc


@app.post("/api/models/open", response_model=XmiInfo)
async def open_model_file(model: UploadFile = File(...)) -> XmiInfo:
    """Open one model file (`cdec parse --out`, a history entry, a reference)
    as a diagram. It has no source tree, so it gets a synthetic project."""
    path = await _save_upload(model, CACHE_ROOT / "_uploaded")
    try:
        project = _load_model_file(path)
    finally:
        path.unlink(missing_ok=True)
    project_id = "u" + uuid.uuid4().hex[:11]
    _registry.register(
        ProjectInfo(
            id=project_id,
            path=f"uploaded: {model.filename or 'model'}",
            lang=project.source_language,
        )
    )
    return _register_model(project_id, project)


def _register_model(project_id: str, model: Any) -> XmiInfo:
    xmi_id = uuid.uuid4().hex[:12]
    write_project(model, _project_cache(project_id) / f"{xmi_id}.xmi")
    xmi_info = XmiInfo(id=xmi_id, project_id=project_id)
    _registry.register_xmi(xmi_info)
    return xmi_info


def _model_file(info: ProjectInfo, ref: str) -> Path:
    """The file behind a model reference that is a file. A request names an
    entry or a token, never a path."""
    from code_constraints import journal

    kind, _, name = ref.partition(":")
    if kind == "reference":
        path = _find_cdec_dir(Path(info.path)) / REFERENCE_FILENAME
        if not path.is_file():
            raise HTTPException(status_code=409, detail=f"no reference model at {path}")
        return path
    if kind == "history":
        cfg_dir = _configured_dir(info)
        if name not in {e.id for e in journal.entries(cfg_dir)}:
            raise HTTPException(status_code=404, detail=f"unknown history entry: {name}")
        return journal.model_path(cfg_dir, name)
    if kind == "upload" and (info.id, name) in _uploads:
        return _uploads[(info.id, name)][0]
    raise HTTPException(status_code=404, detail=f"unknown model: {ref}")


def _model_of(info: ProjectInfo, ref: str) -> Any:
    """The model behind a model reference."""
    if ref == "code":
        return _parse(info.lang, Path(info.path))
    if ref.startswith("git:"):
        try:
            repo = Repo(info.path, search_parent_directories=True)
        except InvalidGitRepositoryError as exc:
            raise HTTPException(status_code=400, detail=f"not a git repo: {info.path}") from exc
        # The project can be a folder inside the repository.
        subpath = Path(info.path).resolve().relative_to(Path(repo.working_tree_dir or info.path).resolve())
        with tempfile.TemporaryDirectory(prefix="cdec-model-") as tmp:
            tree = _checkout(repo, ref[4:], Path(tmp) / "tree")
            return _parse_or_empty(info.lang, tree / subpath)
    return _load_model_file(_model_file(info, ref))


@app.get("/api/projects/{project_id}/models", response_model=list[ModelChoice])
def model_choices(project_id: str) -> list[ModelChoice]:
    """Every model of the project that a page can show, check or compare."""
    from code_constraints import journal

    info = _registry.project(project_id)
    out = [ModelChoice(ref="code", label="The code of today", kind="code")]
    rules_file = _find_rules_yaml(Path(info.path)) if Path(info.path).is_dir() else None
    if rules_file is not None:
        cfg_dir = rules_file.parent
        history = journal.entries(cfg_dir)
        if (cfg_dir / REFERENCE_FILENAME).is_file():
            goal = journal.open_goal(history)
            label = f"The goal: {goal.title}" if goal else "The reference model"
            out.append(ModelChoice(ref="reference", label=label, kind="reference"))
        out.extend(
            ModelChoice(
                ref=f"history:{e.id}",
                label=f"{e.created[:10]} {e.kind}: {e.title}",
                kind="history",
            )
            for e in reversed(history)
        )
    out.extend(
        ModelChoice(ref=f"upload:{token}", label=f"File: {name}", kind="file")
        for (pid, token), (_path, name) in _uploads.items()
        if pid == project_id
    )
    try:
        out.extend(ModelChoice(ref=f"git:{r}", label=f"git: {r}", kind="git") for r in list_refs(project_id))
    except HTTPException:
        pass  # Not in a git repository: no revision to offer.
    return out


@app.post("/api/projects/{project_id}/models/upload", response_model=ModelChoice)
async def model_upload(
    project_id: str, request: Request, model: UploadFile = File(...)
) -> ModelChoice:
    """Add a model file to the models of the project, for this session."""
    _require_local(request)
    _registry.project(project_id)
    path = await _save_upload(model, _project_cache(project_id) / "uploads")
    try:
        _load_model_file(path)
    except HTTPException:
        path.unlink(missing_ok=True)
        raise
    name = Path(model.filename or path.name).name
    _uploads[(project_id, path.stem)] = (path, name)
    return ModelChoice(ref=f"upload:{path.stem}", label=f"File: {name}", kind="file")


@app.post("/api/projects/{project_id}/models/show", response_model=XmiInfo)
def model_show(project_id: str, body: ShowRequest) -> XmiInfo:
    """One model as a diagram. With `against`, the diagram has the diff
    colours of the change from that model: green is in `show` only, red is in
    `against` only."""
    info = _registry.project(project_id)
    model = _model_of(info, body.show)
    if body.against:
        try:
            model = diff_projects(_model_of(info, body.against), model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _register_model(project_id, model)


class CheckRun(BaseModel):
    """The options of `cdec check`, with model references for the two models."""

    subject: str = "code"
    baseline: str = "reference"
    fail_on: str = "error"
    rules_files: list[str] = []
    bypass_locks: bool = False
    bypass_reason: str = ""


def _check_command(cfg_dir: Path, info: ProjectInfo, body: CheckRun) -> str:
    """The `cdec check` command line of a run, or "" when the CLI has none:
    the CLI checks the source tree, not a model."""
    import shlex

    if body.subject != "code":
        return ""
    args = ["cdec", "check"]
    if cfg_dir.resolve() != (Path.cwd() / ".cdec").resolve():
        args += ["--config", str(cfg_dir)]
    if body.fail_on != "error":
        args += ["--fail-on", body.fail_on]
    for name in body.rules_files:
        args += ["-R", name]
    if body.baseline.startswith("git:"):
        args += ["--base-ref", body.baseline[4:]]
    elif body.baseline != "reference":
        args += ["--reference", str(_model_file(info, body.baseline))]
    if body.bypass_locks:
        args += ["--bypass-locks"]
        if body.bypass_reason:
            args += ["--bypass-reason", body.bypass_reason]
    return shlex.join(args) if os.name != "nt" else subprocess.list2cmdline(args)


@app.post("/api/projects/{project_id}/check")
def check_run(project_id: str, body: CheckRun) -> dict[str, Any]:
    """`cdec check`: the same library call, the same report, the same exit
    code. It writes nothing. `subject` and `baseline` are model references:
    the code against the reference is the run of the CLI."""
    import time
    from datetime import datetime, timezone

    from code_constraints.lint.config import available_rule_files, load_rules
    from code_constraints.lint.pipeline import run_check
    from code_constraints.lint.rules.base import Severity

    info = _registry.project(project_id)
    cfg_dir = _configured_dir(info)
    if body.fail_on not in ("error", "warning", "none"):
        raise HTTPException(status_code=400, detail="fail_on must be error, warning or none")
    if body.bypass_locks and not body.bypass_reason.strip():
        raise HTTPException(status_code=400, detail="give the reason for the bypass of the locks")
    cfg = _project_config(cfg_dir)
    loaded = _journey_call(lambda: load_rules(cfg_dir, body.rules_files or None))
    base_ref = body.baseline[4:] if body.baseline.startswith("git:") else None
    reference = None if base_ref or body.baseline == "reference" else _model_file(info, body.baseline)
    started = time.perf_counter()
    if body.subject == "code":
        head, source = _parse(cfg.language, cfg.source), cfg.source
    else:
        head, source = _model_of(info, body.subject), None
    try:
        report = _journey_call(
            lambda: run_check(
                head,
                loaded.rules,
                cfg,
                source=source,
                language=cfg.language,
                reference=reference,
                base_ref=base_ref,
                repo=cfg_dir.parent,
                bypass_locks=body.bypass_locks,
                bypass_reason=body.bypass_reason,
            )
        )
    except (InvalidGitRepositoryError, GitCommandError, ODBError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"cannot read git ref {base_ref!r}: {exc}") from exc
    failed = report.has_failures(Severity(body.fail_on))
    return {
        "passed": not failed,
        "exit_code": 1 if failed else 0,
        "fail_on": body.fail_on,
        "report": report.to_json(),
        "human": report.to_human(),
        "command": _check_command(cfg_dir, info, body),
        "cwd": str(Path.cwd()),
        # Only the code against the reference has the keys of `cdec check`, so
        # only that run accepts an issue.
        "acceptable": body.subject == "code" and body.baseline == "reference",
        "rules": [
            {"id": r.rule_id, "type": r.type_name, "severity": r.severity.value}
            for r in loaded.rules
        ],
        "rule_files": [p.stem for p in available_rule_files(cfg_dir)],
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _record_rule_change(cfg_dir: Path, title: str) -> None:
    """A rule change of the web app, as an entry of the history. The rule is
    written already: a fault here must not make the request fail."""
    from code_constraints import journal

    try:
        cfg = _project_config(cfg_dir)
        journal.record(cfg_dir, "rules", title, _parse(cfg.language, cfg.source))
    except Exception:  # the history is a record, not a gate
        import logging

        logging.getLogger(__name__).exception("the history did not record: %s", title)


# ---------- static SPA mount ----------


class _NoCacheStaticFiles(StaticFiles):
    """Serve the SPA bundle with caching disabled.

    The default ``StaticFiles`` lets the browser cache ``index.html`` (via
    ETag/Last-Modified) and reuse it without revalidating. After a rebuild the
    hashed asset filenames change, but a stale cached ``index.html`` keeps
    pointing at the *old* hashes — the classic "my latest change isn't there"
    symptom. This is a local dev/inspection tool, so the cost of never caching
    is negligible; we force a fresh fetch every time.
    """

    def is_not_modified(self, response_headers, request_headers) -> bool:  # type: ignore[override]
        # Never answer with a 304 — always send the current bytes.
        return False

    async def get_response(self, path, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response


# A source checkout (editable install, `make serve`) has the built SPA at
# ``frontend/dist``; an installed wheel carries it as package data at
# ``web/_static``. The checkout wins, so a stale embedded copy never shadows a
# fresh `npm run build`.
_here = Path(__file__).resolve()
_frontend_dist = next(
    (d for d in (_here.parents[3] / "frontend" / "dist", _here.parent / "_static") if d.exists()),
    None,
)
# What to do when this install has no web UI. The build hook (hatch_build.py)
# puts the UI in every package, so only a package built with
# CDEC_SKIP_UI_BUILD=1, or a checkout with no `npm run build`, gets here.
NO_UI_HELP = (
    "This cdec install has no web UI: the API works, the pages do not. "
    "To fix it, install the released package: "
    "pip install --upgrade --force-reinstall code-constraints. "
    "In a clone of the repository, run: cd frontend && npm install && npm run build."
)

if _frontend_dist is not None:
    app.mount("/", _NoCacheStaticFiles(directory=str(_frontend_dist), html=True), name="spa")
else:
    from fastapi.responses import HTMLResponse

    @app.get("/", response_class=HTMLResponse)
    def _placeholder() -> str:
        return (
            "<!doctype html><meta charset=utf-8><title>cdec: no web UI</title>"
            "<body style='font:16px system-ui;max-width:42rem;margin:3rem auto;line-height:1.5'>"
            "<h1>The web UI is not installed</h1>"
            "<p>This cdec install has no web UI. The API works: see "
            "<a href='/api/docs'>/api/docs</a>.</p>"
            "<p>Install the released package:</p>"
            "<pre>pip install --upgrade --force-reinstall code-constraints</pre>"
            "<p>In a clone of the repository, build the UI:</p>"
            "<pre>cd frontend\nnpm install\nnpm run build</pre>"
        )
