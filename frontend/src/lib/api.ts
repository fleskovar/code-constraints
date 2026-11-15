/** Every language the backend parses (`SUPPORTED_LANGUAGES` in core/model.py). */
export type Lang =
  | "python"
  | "csharp"
  | "typescript"
  | "svelte"
  | "odin"
  | "lua"
  | "julia";

export interface ProjectInfo {
  id: string;
  path: string;
  lang: Lang;
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
  /** Declaration modifiers as source text, e.g. `sealed` or `metaclass=ABCMeta` (parser-derived). */
  modifiers?: string[];
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

// ---------- workspace: recent paths and auto-saved views (.cdec_cache) ----------

/** The canvas state a workspace view holds. The server stores it as it is. */
export interface WorkspaceViewState {
  /** The diagram the view shows. Its ids below belong to that diagram. */
  diagram: { diagram: string; name?: string } | null;
  /** `null` means "everything visible". */
  visibleClassIds: string[] | null;
  nodePositions: Record<string, { x: number; y: number }>;
  display: {
    lodEnabled: boolean;
    showAttributes: boolean;
    showOperations: boolean;
    showInheritanceEdges: boolean;
    showReferenceEdges: boolean;
    revealVia: "all" | "inheritance" | "association";
  };
}

/** A view without its state. Times are seconds since the epoch. */
export interface WorkspaceViewMeta {
  id: string;
  name: string;
  created: number;
  last_used: number;
}

export interface WorkspaceView extends WorkspaceViewMeta {
  /** `null` for a view that was created and never saved. */
  state: WorkspaceViewState | null;
}

/** A recently opened path with its views, most recently used first. */
export interface RecentPath {
  id: string;
  path: string;
  lang: Lang;
  last_used: number;
  /** False when the folder is gone from the disk. */
  exists: boolean;
  views: WorkspaceViewMeta[];
}

/** An Error for a failed response. FastAPI puts the reason in a JSON
 *  `detail` field; show that text rather than the raw JSON body. */
async function httpError(res: Response): Promise<Error> {
  const body = await res.text();
  let detail: unknown = body;
  try {
    detail = (JSON.parse(body) as { detail?: unknown }).detail ?? body;
  } catch {
    // Not JSON: keep the body as it is.
  }
  const text = typeof detail === "string" ? detail : JSON.stringify(detail);
  return new Error(text || `${res.status} ${res.statusText}`);
}

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw await httpError(res);
  }
  return res.json() as Promise<T>;
}

async function voidFetch(url: string, init?: RequestInit): Promise<void> {
  const res = await fetch(url, init);
  if (!res.ok) {
    throw await httpError(res);
  }
}

// ---------- the journey: set up, rules, history ----------

/** The options of one `cdec check` run. `subject` and `baseline` are model
 *  references; the code against the reference is the run of the CLI. */
export interface CheckOptions {
  subject: string;
  baseline: string;
  fail_on: "error" | "warning" | "none";
  rules_files: string[];
  bypass_locks: boolean;
  bypass_reason: string;
}

/** One violation, as `cdec check --format json` prints it. */
export interface CheckViolation {
  key: string;
  rule_id: string;
  engine: string;
  severity: "error" | "warning";
  qualified_name: string;
  message: string;
  waivable: boolean;
  rule?: string;
  signature?: string;
  location?: { file: string; start_line: number; end_line: number };
}

/** The JSON report of `cdec check`. */
export interface CheckReport {
  violations: CheckViolation[];
  suppressed: CheckViolation[];
  bypassed: CheckViolation[];
  skipped: { rule_id: string; reason: string }[];
  summary: {
    errors: number;
    warnings: number;
    suppressed: number;
    skipped: number;
    bypassed: boolean;
    bypass_reason: string;
  };
}

export interface CheckResult {
  passed: boolean;
  exit_code: 0 | 1;
  fail_on: CheckOptions["fail_on"];
  report: CheckReport;
  /** The text that `cdec check` prints. */
  human: string;
  /** The command line of the run. Empty when the CLI has no such run. */
  command: string;
  cwd: string;
  /** True when an issue of this run can be accepted. */
  acceptable: boolean;
  rules: { id: string; type: string; severity: string }[];
  rule_files: string[];
  duration_ms: number;
  finished: string;
}

/** The folder that `cdec ui` ran in: the first choice of the home page. */
export interface StartInfo {
  cwd: string;
  /** The source folder to open. */
  path: string;
  lang: Lang | null;
  /** True when the folder has a `.cdec/rules.yaml`. */
  configured: boolean;
}

export interface FolderListing {
  path: string;
  parent: string | null;
  /** The drives, and the home folder. */
  roots: string[];
  folders: { name: string; path: string; project: boolean }[];
}

/** A model that a page can show, check or compare. `ref` names it:
 *  `code`, `reference`, `history:<id>`, `git:<ref>` or `upload:<token>`. */
export interface ModelChoice {
  ref: string;
  label: string;
  kind: "code" | "reference" | "history" | "file" | "git";
}

/** One recorded decision in `.cdec/history/`. `start` is where the journey
 *  began, `goal` is a target model, `checkpoint` is the code at one moment,
 *  `rules` is a rule that the web app changed. */
export interface HistoryEntry {
  id: string;
  kind: "start" | "goal" | "checkpoint" | "rules";
  title: string;
  note: string;
  /** ISO time, UTC. */
  created: string;
  author: string;
  commit: string;
  /** True when this model became `.cdec/reference.xmi`. */
  reference: boolean;
  /** classes, packages, exceptions, locks. */
  stats: Record<string, number>;
  rules: { id: string; type: string; severity: string }[];
  /** A checkpoint that was recorded while a goal was open: the id of the goal. */
  goal: string;
  /** to_build, to_change, unplanned: class-level differences from the goal. */
  distance: Record<string, number>;
}

export type Journey = "greenfield" | "brownfield";

/** What the guide reads to find the next step. */
export interface JourneyStatus {
  configured: boolean;
  config_dir: string;
  language: string | null;
  source: string | null;
  journey: Journey | "";
  reference: boolean;
  /** Rules that are on. */
  rules: number;
  /** False when the rules are in `.cdec/rules/`: the tool does not write there. */
  rules_editable: boolean;
  exceptions: number;
  locks: number;
  history: number;
  goals: number;
  checkpoints: number;
  /** The goal that is open now. */
  goal: HistoryEntry | null;
  /** The types of the rules that are on, for example `tag-conformance`. */
  rule_types: string[];
  /** The shim file of the language ("" when the language has no tags). */
  shim: string;
  shim_present: boolean;
  /** Old per-concern files that the migration folds into rules.yaml. */
  legacy: string[];
  error: string;
}

/** A rule entry of rules.yaml: `id`, `type`, `severity`, and the options. */
export type RuleEntry = Record<string, unknown>;

/** A rule on its way to the server: the mapping of the form, or YAML text. */
export type RuleDraft = { entry: RuleEntry } | { yaml: string };

/** An accepted issue in the `exceptions:` list. */
export interface AcceptedIssue {
  key: string;
  rule: string;
  qualified_name: string;
  detail: string;
  reason: string;
  added: string;
  added_by: string;
  /** The rule ran and did not report the issue: the exception covers nothing. */
  stale: boolean;
}

export interface LockRow {
  target: string;
  kind: string;
  file: string;
  line: number;
  reason: string;
  /** `ok`, `new` (a tag with no digest yet), or what is wrong: `changed`,
   *  `missing`, `removed`, `unlocked`, `algo-mismatch`. */
  state: string;
  message: string;
  locked_at: string;
  locked_by: string;
}

export interface LocksOverview {
  /** The id of the `implementation-locks` rule, or "" when none is on. */
  rule: string;
  supported: boolean;
  reason?: string;
  targets: LockRow[];
}

export interface TagSpec {
  id: string;
  summary: string;
  targets: string[];
  params: string[];
  /** The rule type that makes the tag binding. */
  enforced_by: string;
}

export interface RuleStarter {
  type: string;
  group: string;
  title: string;
  summary: string;
  /** The rule compares the code with `.cdec/reference.xmi`. */
  needs_reference: boolean;
  yaml: string;
  entry: RuleEntry;
}

export interface RuleGallery {
  groups: { id: string; title: string; summary: string }[];
  starters: RuleStarter[];
}

/** One issue of `cdec check`. `key` is the key that the CLI prints. */
export interface Issue {
  key: string;
  rule_id: string;
  qualified_name: string;
  message: string;
  severity: string;
  file: string;
  line: number;
  /** False for a lock violation: it cannot become an exception. */
  waivable: boolean;
  /** True when an exception covers the issue. */
  waived: boolean;
  waiver_reason: string;
}

export interface RuleRow {
  id: string;
  type: string;
  severity: "error" | "warning" | "off";
  open: number;
  accepted: number;
  /** Why the rule did not run, or "". */
  skipped: string;
  yaml: string;
  entry: RuleEntry;
}

export interface RulesOverview {
  rules_file: string;
  editable: boolean;
  /** True for the code against the reference: the run that `cdec check` does,
   *  and the one whose issues can be accepted. */
  default_inputs: boolean;
  rules: RuleRow[];
  issues: Issue[];
  exceptions: AcceptedIssue[];
}

export interface RulePreview {
  open: number;
  accepted: number;
  skipped: string;
  issues: Issue[];
}

function postJson<T>(url: string, body: unknown, method = "POST"): Promise<T> {
  return jsonFetch(url, {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  journey(projectId: string): Promise<JourneyStatus> {
    return jsonFetch(`/api/projects/${projectId}/journey`);
  },
  /** `cdec init` for the open project. */
  journeyInit(projectId: string, journey: Journey): Promise<JourneyStatus> {
    return postJson(`/api/projects/${projectId}/journey/init`, { journey });
  },
  ruleGallery(): Promise<RuleGallery> {
    return jsonFetch("/api/rule-starters");
  },
  /** Run the check and group the issues by rule. `subject` is the model
   *  that the rules read, `baseline` the model that the diff rules compare
   *  with. Both are model references. */
  rules(projectId: string, subject = "code", baseline = "reference"): Promise<RulesOverview> {
    const q = new URLSearchParams({ subject, baseline });
    return jsonFetch(`/api/projects/${projectId}/rules?${q}`);
  },
  start(): Promise<StartInfo> {
    return jsonFetch("/api/start");
  },
  folders(path = ""): Promise<FolderListing> {
    return jsonFetch(`/api/fs?path=${encodeURIComponent(path)}`);
  },
  models(projectId: string): Promise<ModelChoice[]> {
    return jsonFetch(`/api/projects/${projectId}/models`);
  },
  /** One model as a diagram, with the diff colours of the change from
   *  `against` when that is given. */
  showModel(projectId: string, show: string, against = ""): Promise<XmiInfo> {
    return postJson(`/api/projects/${projectId}/models/show`, { show, against });
  },
  /** Add a model file (.xmi or .json) to the models of the project. */
  uploadModel(projectId: string, file: File): Promise<ModelChoice> {
    const fd = new FormData();
    fd.append("model", file);
    return jsonFetch(`/api/projects/${projectId}/models/upload`, { method: "POST", body: fd });
  },
  /** Open one model file with no project behind it. */
  openModelFile(file: File): Promise<XmiInfo> {
    const fd = new FormData();
    fd.append("model", file);
    return jsonFetch("/api/models/open", { method: "POST", body: fd });
  },
  /** Run one draft rule against the code of today. Writes nothing. */
  previewRule(projectId: string, draft: RuleDraft, replaces = ""): Promise<RulePreview> {
    return postJson(`/api/projects/${projectId}/rules/preview`, { ...draft, replaces });
  },
  addRule(
    projectId: string,
    draft: RuleDraft,
    acceptExisting: boolean,
  ): Promise<{ id: string; accepted: number }> {
    return postJson(`/api/projects/${projectId}/rules`, {
      ...draft,
      accept_existing: acceptExisting,
    });
  },
  /** A rule entry in both forms: the mapping and the YAML text. */
  ruleEntry(draft: RuleDraft): Promise<{ entry: RuleEntry; yaml: string }> {
    return postJson("/api/rule-entry", draft);
  },
  replaceRule(projectId: string, ruleId: string, draft: RuleDraft): Promise<void> {
    return voidFetch(`/api/projects/${projectId}/rules/${encodeURIComponent(ruleId)}/entry`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(draft),
    });
  },
  removeRule(projectId: string, ruleId: string): Promise<void> {
    return voidFetch(`/api/projects/${projectId}/rules/${encodeURIComponent(ruleId)}`, {
      method: "DELETE",
    });
  },
  /** Withdraw exceptions: the issues fail the check again. */
  removeExceptions(projectId: string, keys: string[]): Promise<{ removed: number }> {
    return postJson(`/api/projects/${projectId}/exceptions`, { keys }, "DELETE");
  },
  /** Drop the exceptions whose issue does not occur any more. */
  pruneExceptions(projectId: string): Promise<{ removed: number }> {
    return postJson(`/api/projects/${projectId}/exceptions/prune`, {});
  },
  /** The code of today against the reference. Green: the code must still
   *  build it. Red: it is in the code and not in the reference. */
  referenceCompare(projectId: string): Promise<XmiInfo> {
    return postJson(`/api/projects/${projectId}/reference/compare`, {});
  },
  /** The code as it is becomes the reference. An open goal closes. */
  referenceSnapshot(
    projectId: string,
    title: string,
    note: string,
  ): Promise<{ path: string; classes: number; history: string }> {
    return postJson(`/api/projects/${projectId}/reference/snapshot`, { title, note });
  },
  locks(projectId: string): Promise<LocksOverview> {
    return jsonFetch(`/api/projects/${projectId}/locks`);
  },
  /** Without `force`: record the digests of new locks. With `force`: accept
   *  the change of the named elements. */
  updateLocks(projectId: string, force: boolean, targets: string[]): Promise<{ lines: string[] }> {
    return postJson(`/api/projects/${projectId}/locks`, { force, targets });
  },
  tags(lang: string): Promise<{ supported: boolean; tags: TagSpec[] }> {
    return jsonFetch(`/api/tags?lang=${encodeURIComponent(lang)}`);
  },
  /** How to write one tag in one language, with the import that it needs. */
  tagSnippet(
    lang: string,
    tag: string,
    values: Record<string, string>,
  ): Promise<{ tag: string; import: string }> {
    return postJson("/api/tags/snippet", { lang, tag, values });
  },
  copyShims(projectId: string): Promise<{ written: string[] }> {
    return postJson(`/api/projects/${projectId}/shims`, {});
  },
  writeCiScripts(projectId: string): Promise<{ written: string[] }> {
    return postJson(`/api/projects/${projectId}/ci-scripts`, {});
  },
  /** Fold the old config.yaml / baseline.yaml / locks.yaml into rules.yaml. */
  migrate(projectId: string): Promise<JourneyStatus> {
    return postJson(`/api/projects/${projectId}/journey/migrate`, {});
  },
  setRuleSeverity(projectId: string, ruleId: string, severity: string): Promise<void> {
    return voidFetch(`/api/projects/${projectId}/rules/${encodeURIComponent(ruleId)}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ severity }),
    });
  },
  acceptIssues(
    projectId: string,
    keys: string[],
    reason: string,
  ): Promise<{ allowed: number; refused: { key: string; reason: string }[]; unknown: string[] }> {
    return postJson(`/api/projects/${projectId}/exceptions`, { keys, reason });
  },
  history(projectId: string): Promise<HistoryEntry[]> {
    return jsonFetch(`/api/projects/${projectId}/history`);
  },
  recordCheckpoint(projectId: string, title: string, note: string): Promise<HistoryEntry> {
    return postJson(`/api/projects/${projectId}/history`, { title, note });
  },
  /** The model of one history entry as a diagram, with the diff colours of the
   *  change from `against` when that is given. */
  historyFrame(projectId: string, entry: string, against: string): Promise<XmiInfo> {
    return postJson(`/api/projects/${projectId}/history/frame`, { entry, against });
  },
  registerProject(path: string, lang: Lang): Promise<ProjectInfo> {
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
      throw await httpError(res);
    }
    return res.json() as Promise<XmiInfo>;
  },
  async diffSourceVsXmi(
    path: string,
    lang: Lang,
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
      throw await httpError(res);
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
      throw await httpError(res);
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
      throw await httpError(res);
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
      throw await httpError(res);
    }
    return res.json() as Promise<ClassGraph>;
  },
  /** Overwrite `.cdec/reference.xmi`. The project history records the model
   *  as a goal (a target) or as a checkpoint (the code as it is). */
  async setReference(
    projectId: string,
    xmi: Blob,
    record: { kind: "goal" | "checkpoint"; title: string; note: string },
  ): Promise<{ path: string }> {
    const query = new URLSearchParams(record).toString();
    const res = await fetch(`/api/projects/${projectId}/reference?${query}`, {
      method: "PUT",
      headers: { "content-type": "application/xml" },
      body: xmi,
    });
    if (!res.ok) {
      throw await httpError(res);
    }
    return res.json() as Promise<{ path: string }>;
  },
  /** Show the source file of a class in the file manager of the desktop, or
   *  open it in an editor. The server does this on the machine it runs on. */
  nodeDesktopAction(
    xmiId: string,
    nodeId: string,
    action: "reveal" | "open",
    line = 0,
  ): Promise<void> {
    const at = line > 0 ? `?line=${line}` : "";
    return voidFetch(`/api/xmi/${xmiId}/nodes/${encodeURIComponent(nodeId)}/${action}${at}`, {
      method: "POST",
    });
  },
  /** `cdec check`: the same report and exit code as the CLI. Writes nothing. */
  runCheck(projectId: string, options: CheckOptions): Promise<CheckResult> {
    return postJson(`/api/projects/${projectId}/check`, options);
  },
  /** Suggest the language of a source tree. `lang` is null when the path is
   *  not a directory or holds no known language. */
  detectLanguage(path: string): Promise<{ lang: Lang | null; is_dir: boolean }> {
    return jsonFetch(`/api/detect-language?path=${encodeURIComponent(path)}`);
  },
  workspace(): Promise<RecentPath[]> {
    return jsonFetch("/api/workspace");
  },
  touchRecent(projectId: string): Promise<void> {
    return voidFetch(`/api/workspace/recent/${projectId}`, { method: "POST" });
  },
  forgetRecent(projectId: string): Promise<void> {
    return voidFetch(`/api/workspace/recent/${projectId}`, { method: "DELETE" });
  },
  workspaceViews(projectId: string): Promise<WorkspaceViewMeta[]> {
    return jsonFetch(`/api/projects/${projectId}/workspace/views`);
  },
  /** Create a view. Without a name the server calls it the next `Untitled N`. */
  createWorkspaceView(projectId: string, name?: string): Promise<WorkspaceView> {
    return jsonFetch(`/api/projects/${projectId}/workspace/views`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(name ? { name } : {}),
    });
  },
  /** Read a view with its state and mark it as used now. */
  openWorkspaceView(projectId: string, viewId: string): Promise<WorkspaceView> {
    return jsonFetch(`/api/projects/${projectId}/workspace/views/${viewId}/open`, {
      method: "POST",
    });
  },
  /** Rename a view and/or replace its state. `keepalive` lets the request
   *  finish while the page closes. */
  saveWorkspaceView(
    projectId: string,
    viewId: string,
    body: { name?: string; state?: WorkspaceViewState },
    keepalive = false,
  ): Promise<WorkspaceViewMeta> {
    return jsonFetch(`/api/projects/${projectId}/workspace/views/${viewId}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      keepalive,
    });
  },
  deleteWorkspaceView(projectId: string, viewId: string): Promise<void> {
    return voidFetch(`/api/projects/${projectId}/workspace/views/${viewId}`, {
      method: "DELETE",
    });
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
      throw await httpError(res);
    }
    return res.blob();
  },
};
