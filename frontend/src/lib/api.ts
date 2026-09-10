export interface ProjectInfo {
  id: string;
  path: string;
  lang: "python" | "csharp" | "typescript" | "svelte";
}

export interface XmiInfo {
  id: string;
  project_id: string;
}

export interface ProposalInfo {
  /** xmi id of the annotated proposal diff. */
  id: string;
  project_id: string;
  /** Bumped on every push — the viewer polls and refreshes when it grows. */
  seq: number;
  /** Qualified class names the pusher asked the viewer to pre-filter to. */
  focus: string[];
}

export interface DiagramListing {
  classes: boolean;
  packages: boolean;
  activities: string[];
  sequences: string[];
}

export interface GitInfo {
  is_git: boolean;
  branch: string | null;
  head_sha: string | null;
  head_short: string | null;
  head_subject: string | null;
  parent_sha: string | null;
  parent_short: string | null;
  parent_subject: string | null;
  is_dirty: boolean | null;
  /** Absolute path of the git working tree root, or null when is_git=false. */
  repo_root: string | null;
  /** Project path relative to repo_root. Empty string when the project IS the repo root. */
  subpath: string | null;
}

export type DiffStatus = "unchanged" | "added" | "removed" | "changed";
export type Visibility = "public" | "protected" | "private" | "package";
export type ClassKind =
  | "class"
  | "interface"
  | "abstract"
  | "enum"
  | "struct"
  | "record"
  | "static";

export interface ClassGraphAttribute {
  name: string;
  type: string;
  visibility: Visibility;
  isStatic: boolean;
  status: DiffStatus;
  signature: string;
  description: string | null;
}

export interface ClassGraphRule {
  name: string;
  args: string[];
  kwargs: Record<string, string>;
}

export interface ClassGraphOperation {
  name: string;
  signature: string;
  returnType: string;
  visibility: Visibility;
  isStatic: boolean;
  isAbstract: boolean;
  status: DiffStatus;
  description: string | null;
  rules: ClassGraphRule[];
}

export interface ClassGraphNode {
  id: string;
  qualifiedName: string;
  name: string;
  kind: ClassKind | "external";
  /** True for synthetic placeholder nodes representing an external/framework
   *  supertype (e.g. MonoBehaviour) that isn't defined in the project. */
  external?: boolean;
  package: string;
  status: DiffStatus;
  description: string | null;
  attributes: ClassGraphAttribute[];
  operations: ClassGraphOperation[];
  rules: ClassGraphRule[];
  location: { file: string; startLine: number; endLine: number } | null;
}

/** A member of the source class that produces an edge — used to highlight where
 *  a reference originates (a field, a method, or the inheritance base). */
export interface ClassGraphEdgeMember {
  kind: "attribute" | "operation" | "inheritance";
  signature: string;
}

export interface ClassGraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "inheritance" | "association";
  multiplicity: string;
  status: DiffStatus;
  /** Source-class members that contribute this edge. Absent on older payloads. */
  members?: ClassGraphEdgeMember[];
}

export interface LayerDependencies {
  allow: Record<string, string[]>;
  source: string | null;
}

export interface ClassGraph {
  nodes: ClassGraphNode[];
  edges: ClassGraphEdge[];
  meta: { count: number; sourceLanguage: string };
}

export interface ChangeMember {
  kind: "attribute" | "operation";
  signature: string;
  status: "added" | "removed";
}

export interface Change {
  classId: string;
  classQname: string;
  kind: "added" | "removed" | "changed";
  summary: string;
  members: ChangeMember[];
}

export interface PackageGraphNode {
  id: string;
  kind: "package";
  name: string;
  qualifiedName: string;
  /** Parent package qualified-name (empty for roots). */
  parentQname: string;
  status: DiffStatus;
  description: string | null;
  /** Recursive count of classes in this package + all sub-packages. */
  classCount: number;
}

export interface PackageGraphEdge {
  id: string;
  source: string;
  target: string;
  kind: "dependency";
  multiplicity: string;
  status: DiffStatus;
}

export interface PackageGraph {
  nodes: PackageGraphNode[];
  edges: PackageGraphEdge[];
  meta: { count: number; edgeCount: number };
}

export type ActivityNodeKind =
  | "initial"
  | "final"
  | "action"
  | "decision"
  | "merge"
  | "fork"
  | "join";

export interface ActivityGraphNode {
  id: string;
  kind: ActivityNodeKind;
  label: string;
  status: DiffStatus;
}

export interface ActivityGraphEdge {
  id: string;
  source: string;
  target: string;
  guard: string;
  status: DiffStatus;
}

export interface ActivityGraph {
  nodes: ActivityGraphNode[];
  edges: ActivityGraphEdge[];
  meta: { count: number; name: string; granularity: string };
}

export interface SequenceLifeline {
  id: string;
  name: string;
  represents: string;
  column: number;
  status: DiffStatus;
}

export interface SequenceMessage {
  id: string;
  sender: string;
  receiver: string;
  label: string;
  isReturn: boolean;
  /** Optional guard condition (e.g. "result == 'ok'") from the surrounding
   * if-branch; the frontend prefixes the message label with `[guard]`. */
  guard: string;
  row: number;
  status: DiffStatus;
}

export interface SequenceFragment {
  id: string;
  kind: "alt" | "opt" | "loop";
  label: string;
  startRow: number;
  endRow: number;
  status: DiffStatus;
}

export interface SequenceGraph {
  lifelines: SequenceLifeline[];
  messages: SequenceMessage[];
  fragments: SequenceFragment[];
  meta: {
    name: string;
    lifelineCount: number;
    messageCount: number;
    fragmentCount: number;
  };
}

export interface DiagramChangeMember {
  kind: "node" | "edge" | "lifeline" | "message";
  signature: string;
  status: "added" | "removed";
  nodeId?: string;
  messageRow?: number;
}

export interface DiagramChange {
  diagramKind: "activity" | "sequence";
  diagramName: string;
  diagramId: string;
  kind: "added" | "removed" | "changed";
  summary: string;
  members: DiagramChangeMember[];
}

// ---------- Editor draft model (mirrors the Python dataclasses) ----------
// snake_case on the wire so the backend converters are dumb asdict/from_dict
// calls; UI code converts via the helpers in lib/editor/model.ts.

export interface ParameterDraft {
  name: string;
  type: string;
  default: string | null;
}

export interface AttributeDraft {
  name: string;
  type: string;
  visibility: Visibility;
  is_static: boolean;
  is_readonly: boolean;
  default: string | null;
  description: string | null;
  status: DiffStatus;
}

export interface OperationDraft {
  name: string;
  parameters: ParameterDraft[];
  return_type: string;
  visibility: Visibility;
  is_static: boolean;
  is_abstract: boolean;
  description: string | null;
  status: DiffStatus;
}

export interface ClassDraft {
  name: string;
  qualified_name: string;
  kind: ClassKind;
  attributes: AttributeDraft[];
  operations: OperationDraft[];
  bases: string[];
  /** Raw type-name strings referenced in method bodies (parser-derived). */
  dependencies?: string[];
  location: { file: string; start_line: number; end_line: number } | null;
  layout: {
    x: number;
    y: number;
    width: number;
    height: number;
    collapsed: boolean;
  } | null;
  description: string | null;
  status: DiffStatus;
}

export interface PackageDraft {
  name: string;
  qualified_name: string;
  classes: ClassDraft[];
  sub_packages: PackageDraft[];
  layout: ClassDraft["layout"];
  description: string | null;
  status: DiffStatus;
}

export interface AssociationDraft {
  source: string;
  target: string;
  name: string | null;
  source_multiplicity: string | null;
  target_multiplicity: string | null;
  source_role: string | null;
  target_role: string | null;
  status: DiffStatus;
}

export interface ProjectDraft {
  source_language: "python" | "csharp" | "typescript" | "svelte";
  packages: PackageDraft[];
  /** Activities/sequences are preserved on round-trip but the editor doesn't
   *  expose UI for editing them; we just keep them as opaque blobs. */
  activities: unknown[];
  sequences: unknown[];
  associations: AssociationDraft[];
  root_path: string;
}

export interface ServerViewListing {
  name: string;
  filename: string;
}

export interface ServerView {
  schema: "code-constraints/view@2";
  name: string;
  /** Qualified class names to show; everything not listed is hidden. */
  visible: string[];
  /** Optional canvas positions keyed by qualified class name. */
  positions?: Record<string, { x: number; y: number }>;
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

async function voidFetch(url: string, init?: RequestInit): Promise<void> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
}

export const api = {
  registerProject(path: string, lang: "python" | "csharp" | "typescript" | "svelte"): Promise<ProjectInfo> {
    return jsonFetch("/api/projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path, lang }),
    });
  },
  listProjects(): Promise<ProjectInfo[]> {
    return jsonFetch("/api/projects");
  },
  parse(projectId: string): Promise<XmiInfo> {
    return jsonFetch(`/api/projects/${projectId}/parse`, { method: "POST" });
  },
  latestProposal(projectId: string): Promise<ProposalInfo> {
    return jsonFetch(`/api/projects/${projectId}/proposal`);
  },
  referenceModel(projectId: string): Promise<ProjectDraft> {
    return jsonFetch(`/api/projects/${projectId}/reference-model`);
  },
  refs(projectId: string): Promise<string[]> {
    return jsonFetch(`/api/projects/${projectId}/refs`);
  },
  gitInfo(projectId: string): Promise<GitInfo> {
    return jsonFetch(`/api/projects/${projectId}/git-info`);
  },
  async quickDiff(projectId: string, subpath?: string): Promise<XmiInfo> {
    // Convenience: diff HEAD vs HEAD~1, scoped to the project's location
    // inside the repo. If the project sits in a sub-directory of a larger
    // repo (e.g. examples/python_demo inside code_constraints), passing the
    // sub-directory as `subpath` keeps the diff narrow rather than
    // including every other file in the repo.
    let effectiveSubpath = subpath;
    if (effectiveSubpath === undefined) {
      try {
        const info = await api.gitInfo(projectId);
        effectiveSubpath = info.subpath ?? "";
      } catch {
        effectiveSubpath = "";
      }
    }
    return jsonFetch(`/api/projects/${projectId}/diff`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        old_ref: "HEAD~1",
        new_ref: "HEAD",
        subpath: effectiveSubpath,
      }),
    });
  },
  diff(projectId: string, oldRef: string, newRef: string, subpath = ""): Promise<XmiInfo> {
    return jsonFetch(`/api/projects/${projectId}/diff`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ old_ref: oldRef, new_ref: newRef, subpath }),
    });
  },
  diagrams(xmiId: string): Promise<DiagramListing> {
    return jsonFetch(`/api/xmi/${xmiId}/diagrams`);
  },
  classGraph(xmiId: string): Promise<ClassGraph> {
    return jsonFetch(`/api/xmi/${xmiId}/model?diagram=class`);
  },
  layerDependencies(projectId: string): Promise<LayerDependencies> {
    return jsonFetch(`/api/projects/${projectId}/layers`);
  },
  changes(xmiId: string): Promise<Change[]> {
    return jsonFetch(`/api/xmi/${xmiId}/changes`);
  },
  packageGraph(xmiId: string): Promise<PackageGraph> {
    return jsonFetch(`/api/xmi/${xmiId}/model?diagram=package`);
  },
  activityGraph(xmiId: string, name: string): Promise<ActivityGraph> {
    const q = new URLSearchParams({ diagram: "activity", name });
    return jsonFetch(`/api/xmi/${xmiId}/model?${q.toString()}`);
  },
  sequenceGraph(xmiId: string, name: string): Promise<SequenceGraph> {
    const q = new URLSearchParams({ diagram: "sequence", name });
    return jsonFetch(`/api/xmi/${xmiId}/model?${q.toString()}`);
  },
  activityChanges(xmiId: string): Promise<DiagramChange[]> {
    return jsonFetch(`/api/xmi/${xmiId}/changes?kind=activity`);
  },
  sequenceChanges(xmiId: string): Promise<DiagramChange[]> {
    return jsonFetch(`/api/xmi/${xmiId}/changes?kind=sequence`);
  },
  async diffXmiFiles(oldXmi: File, newXmi: File): Promise<XmiInfo> {
    const fd = new FormData();
    fd.append("old_xmi", oldXmi);
    fd.append("new_xmi", newXmi);
    const res = await fetch("/api/xmi/diff", { method: "POST", body: fd });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<XmiInfo>;
  },
  async diffSourceVsXmi(
    path: string,
    lang: "python" | "csharp" | "typescript" | "svelte",
    referenceXmi: File,
  ): Promise<XmiInfo> {
    const fd = new FormData();
    fd.append("reference_xmi", referenceXmi);
    fd.append("path", path);
    fd.append("lang", lang);
    const res = await fetch("/api/projects/diff-vs-xmi", {
      method: "POST",
      body: fd,
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<XmiInfo>;
  },
  // Hydrate ProjectInfo for a synthetic project_id (e.g. an upload diff)
  // so the existing viewer chrome has something to display.
  async projectInfo(projectId: string): Promise<ProjectInfo | null> {
    const all = await api.listProjects();
    return all.find((p) => p.id === projectId) ?? null;
  },
  async editFromXmi(file: File | Blob, filename = "diagram.xmi"): Promise<ProjectDraft> {
    const fd = new FormData();
    fd.append("file", file, filename);
    const res = await fetch("/api/edit/from-xmi", { method: "POST", body: fd });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<ProjectDraft>;
  },
  async editClassGraph(project: ProjectDraft): Promise<ClassGraph> {
    const res = await fetch("/api/edit/model?diagram=class", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(project),
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<ClassGraph>;
  },
  /** Class graph of `draft` diffed against `baseline` (statuses annotated). */
  async editDiffGraph(
    baseline: ProjectDraft,
    draft: ProjectDraft,
  ): Promise<ClassGraph> {
    const res = await fetch("/api/edit/diff-model?diagram=class", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ old: baseline, new: draft }),
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<ClassGraph>;
  },
  async setReference(projectId: string, xmi: Blob): Promise<{ path: string }> {
    const res = await fetch(`/api/projects/${projectId}/reference`, {
      method: "PUT",
      headers: { "content-type": "application/xml" },
      body: xmi,
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.json() as Promise<{ path: string }>;
  },
  listViews(projectId: string): Promise<ServerViewListing[]> {
    return jsonFetch(`/api/projects/${projectId}/views`);
  },
  getView(projectId: string, filename: string): Promise<ServerView> {
    return jsonFetch(`/api/projects/${projectId}/views/${encodeURIComponent(filename)}`);
  },
  saveView(projectId: string, filename: string, view: ServerView): Promise<void> {
    return voidFetch(
      `/api/projects/${projectId}/views/${encodeURIComponent(filename)}`,
      {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(view),
      },
    );
  },
  deleteView(projectId: string, filename: string): Promise<void> {
    return voidFetch(
      `/api/projects/${projectId}/views/${encodeURIComponent(filename)}`,
      { method: "DELETE" },
    );
  },
  async editToXmi(project: ProjectDraft, downloadName?: string): Promise<Blob> {
    const payload = downloadName
      ? { ...project, download_name: downloadName }
      : project;
    const res = await fetch("/api/edit/to-xmi", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status} ${res.statusText}: ${detail}`);
    }
    return res.blob();
  },
};
