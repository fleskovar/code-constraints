"""FastAPI backend for the code-constraints web viewer.

Endpoints are intentionally thin orchestrators over `code_constraints.core` + parsers. All
expensive artifacts (parsed XMIs) live on disk under `.cdec_cache/<project_id>/` so the
UI can reload freely. Every diagram is a JSON graph the client lays out; the server
renders no images. No auth — local use only.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

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
async def set_reference(project_id: str, request: Request) -> ReferenceResult:
    """Write raw XMI bytes (the current/edited diagram) to the project's
    `.cdec/reference.xmi`, after validating they parse as a Project. Used by the
    'Set as reference' button to seed or update the architecture baseline."""
    info = _registry.project(project_id)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty request body")
    # Validate the bytes parse as a real Project before overwriting the baseline.
    with tempfile.NamedTemporaryFile(suffix=".xmi", delete=False) as tmp:
        tmp.write(body)
        tmp_path = Path(tmp.name)
    try:
        read_project(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"not a valid XMI: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)
    cdec_dir = _find_cdec_dir(Path(info.path))
    cdec_dir.mkdir(parents=True, exist_ok=True)
    ref_path = cdec_dir / REFERENCE_FILENAME
    ref_path.write_bytes(body)
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
    cache_root = CACHE_ROOT / "_uploaded"
    cache_root.mkdir(parents=True, exist_ok=True)
    # Write the uploads to temp files so xmi_reader can ingest them.
    old_bytes = await old_xmi.read()
    new_bytes = await new_xmi.read()
    if not old_bytes or not new_bytes:
        raise HTTPException(status_code=400, detail="both XMI files must be non-empty")
    with tempfile.NamedTemporaryFile(
        suffix=".xmi", delete=False, dir=str(cache_root)
    ) as ofh:
        ofh.write(old_bytes)
        old_tmp = Path(ofh.name)
    with tempfile.NamedTemporaryFile(
        suffix=".xmi", delete=False, dir=str(cache_root)
    ) as nfh:
        nfh.write(new_bytes)
        new_tmp = Path(nfh.name)
    try:
        try:
            old_proj = read_project(old_tmp)
            new_proj = read_project(new_tmp)
        except Exception as exc:  # malformed XML, missing root, etc.
            raise HTTPException(
                status_code=400, detail=f"could not parse uploaded XMI: {exc}"
            ) from exc
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
if _frontend_dist is not None:
    app.mount("/", _NoCacheStaticFiles(directory=str(_frontend_dist), html=True), name="spa")
else:

    @app.get("/")
    def _placeholder() -> dict[str, str]:
        return {
            "status": "ok",
            "message": "Frontend not built. Run `npm install && npm run build` in /frontend.",
            "api_docs": "/api/docs",
        }
