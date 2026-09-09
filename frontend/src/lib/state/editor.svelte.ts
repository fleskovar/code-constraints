// Editor singleton: holds an in-memory ProjectDraft + the mutators used by
// the modal forms and the canvas. Persistence is download/upload only, like
// SavedViews — there's no server-side store.

import type {
  AssociationDraft,
  AttributeDraft,
  ClassDraft,
  ClassKind,
  OperationDraft,
  PackageDraft,
  ProjectDraft,
  Visibility,
} from "../api";

export type EditorMode = "view" | "edit";

export interface EditorState {
  project: ProjectDraft;
  mode: EditorMode;
  /** True after any mutator runs; reset on load/save. */
  dirty: boolean;
  /** Track the last loaded file name so Save can suggest it. */
  fileName: string;
  /** Baseline model to diff the draft against (live edit + diff preview).
   *  `null` = no baseline loaded; `compare` toggles the diff rendering. */
  baseline: ProjectDraft | null;
  compare: boolean;
  /** Whether the JSON code panel is shown alongside the canvas. */
  codePanelOpen: boolean;
}

export const editorState: EditorState = $state({
  project: emptyProject(),
  mode: "view" as EditorMode,
  dirty: false,
  fileName: "diagram.xmi",
  baseline: null as ProjectDraft | null,
  compare: false,
  codePanelOpen: false,
});

export function setBaseline(draft: ProjectDraft | null): void {
  editorState.baseline = draft;
  editorState.compare = draft !== null;
}

export function toggleCompare(): void {
  if (editorState.baseline === null) return;
  editorState.compare = !editorState.compare;
}

export function toggleCodePanel(): void {
  editorState.codePanelOpen = !editorState.codePanelOpen;
}

/** Replace the whole draft (used by the JSON code panel). Marks dirty. */
export function replaceProject(draft: ProjectDraft): void {
  editorState.project = draft;
  editorState.dirty = true;
}

// Modal state lifted to module scope. EditorCanvas instance state wasn't
// propagating mutations from click handlers reliably in production builds;
// a shared singleton avoids the issue and matches the editorState pattern.
import type { AssociationDraft as _A } from "../api";

// Resolved view of the editor canvas: node-id → qualified name, populated by
// EditorFlowView whenever the server returns a refreshed graph. EditorCanvas
// reads it when translating SvelteFlow click events back to model classes.
// Stored as plain Map (not $state) since we never reactively read from it.
export const flowGraphIndex = {
  qnameById: new Map<string, string>(),
};

export interface ModalState {
  classOpen: boolean;
  classInitial: ClassDraft | null;
  classExisting: boolean;
  classOriginalQname: string | null;

  assocOpen: boolean;
  assocInitial: _A | null;
  assocIndex: number;
  assocExisting: boolean;

  edgePickerOpen: boolean;
  edgePickerSource: string;
  edgePickerTarget: string;
  edgePickerSourceLabel: string;
  edgePickerTargetLabel: string;
}

export const modalState: ModalState = $state({
  classOpen: false,
  classInitial: null,
  classExisting: false,
  classOriginalQname: null,

  assocOpen: false,
  assocInitial: null,
  assocIndex: -1,
  assocExisting: false,

  edgePickerOpen: false,
  edgePickerSource: "",
  edgePickerTarget: "",
  edgePickerSourceLabel: "",
  edgePickerTargetLabel: "",
});

export function openClassModal(
  initial: ClassDraft,
  isExisting: boolean,
  originalQname: string | null = null,
): void {
  modalState.classInitial = initial;
  modalState.classExisting = isExisting;
  modalState.classOriginalQname = originalQname;
  modalState.classOpen = true;
}

export function closeClassModal(): void {
  modalState.classOpen = false;
  modalState.classInitial = null;
}

export function openAssocModal(
  initial: _A,
  index: number,
  isExisting: boolean,
): void {
  modalState.assocInitial = initial;
  modalState.assocIndex = index;
  modalState.assocExisting = isExisting;
  modalState.assocOpen = true;
}

export function closeAssocModal(): void {
  modalState.assocOpen = false;
  modalState.assocInitial = null;
}

export function openEdgePicker(
  source: string,
  target: string,
  sourceLabel: string,
  targetLabel: string,
): void {
  modalState.edgePickerSource = source;
  modalState.edgePickerTarget = target;
  modalState.edgePickerSourceLabel = sourceLabel;
  modalState.edgePickerTargetLabel = targetLabel;
  modalState.edgePickerOpen = true;
}

export function closeEdgePicker(): void {
  modalState.edgePickerOpen = false;
}

export function emptyProject(): ProjectDraft {
  return {
    source_language: "python",
    packages: [],
    activities: [],
    sequences: [],
    associations: [],
    root_path: "",
  };
}

export function newBlank(
  language: "python" | "csharp" | "typescript" | "svelte" = "python",
): void {
  editorState.project = emptyProject();
  editorState.project.source_language = language;
  editorState.dirty = false;
  editorState.fileName = "diagram.xmi";
}

export function loadFromJson(draft: ProjectDraft, fileName?: string): void {
  editorState.project = draft;
  editorState.dirty = false;
  if (fileName) editorState.fileName = fileName;
}

export function setMode(mode: EditorMode): void {
  editorState.mode = mode;
}

// ---------- class lookups / iteration ----------

export function* iterClasses(p: ProjectDraft): Generator<ClassDraft> {
  yield* iterClassesIn(p.packages);
}

function* iterClassesIn(pkgs: PackageDraft[]): Generator<ClassDraft> {
  for (const pkg of pkgs) {
    yield* pkg.classes;
    yield* iterClassesIn(pkg.sub_packages);
  }
}

export function findClass(qname: string): ClassDraft | null {
  for (const c of iterClasses(editorState.project)) {
    if (c.qualified_name === qname) return c;
  }
  return null;
}

export function allClassQnames(): string[] {
  return Array.from(iterClasses(editorState.project)).map((c) => c.qualified_name);
}

// ---------- package helpers ----------

function ensurePackage(qname: string): PackageDraft {
  if (!qname) qname = "__root__";
  // walk pkgs first (flat lookup) — we keep packages flat in the editor for
  // simplicity; sub_packages from imported XMIs are preserved on save by
  // round-tripping through editToXmi but the editor itself doesn't nest.
  let pkg = editorState.project.packages.find((p) => p.qualified_name === qname);
  if (pkg) return pkg;
  const name = qname === "__root__" ? "__root__" : qname.split(".").pop() ?? qname;
  pkg = {
    name,
    qualified_name: qname,
    classes: [],
    sub_packages: [],
    layout: null,
    description: null,
    status: "unchanged",
  };
  editorState.project.packages.push(pkg);
  bump();
  return pkg;
}

function removeClassFromPackages(qname: string): ClassDraft | null {
  for (const pkg of editorState.project.packages) {
    const idx = pkg.classes.findIndex((c) => c.qualified_name === qname);
    if (idx >= 0) {
      const [cls] = pkg.classes.splice(idx, 1);
      return cls;
    }
  }
  return null;
}

function bump(): void {
  editorState.dirty = true;
}

// ---------- class mutators ----------

export interface NewClassInit {
  name: string;
  package?: string;
  kind?: ClassKind;
  bases?: string[];
}

export function defaultClass(init: NewClassInit): ClassDraft {
  const pkg = (init.package ?? "").trim();
  const qname = pkg ? `${pkg}.${init.name}` : init.name;
  return {
    name: init.name,
    qualified_name: qname,
    kind: init.kind ?? "class",
    attributes: [],
    operations: [],
    bases: init.bases ?? [],
    location: null,
    layout: null,
    description: null,
    status: "unchanged",
  };
}

export function addClass(cls: ClassDraft): ClassDraft {
  const pkgQname = packageOfQname(cls.qualified_name);
  const pkg = ensurePackage(pkgQname);
  pkg.classes.push(cls);
  bump();
  return cls;
}

export function updateClass(oldQname: string, next: ClassDraft): void {
  const cls = removeClassFromPackages(oldQname);
  if (!cls) return;
  // If the qualified name changed, also rewrite references in bases and assocs
  if (oldQname !== next.qualified_name) {
    for (const other of iterClasses(editorState.project)) {
      other.bases = other.bases.map((b) => (b === oldQname ? next.qualified_name : b));
    }
    for (const a of editorState.project.associations) {
      if (a.source === oldQname) a.source = next.qualified_name;
      if (a.target === oldQname) a.target = next.qualified_name;
    }
  }
  // Preserve attributes/operations/bases from `next` (caller supplies the merged result).
  const pkg = ensurePackage(packageOfQname(next.qualified_name));
  pkg.classes.push(next);
  bump();
}

export function removeClass(qname: string): void {
  removeClassFromPackages(qname);
  // Drop inheritance refs + associations that involve this class.
  for (const other of iterClasses(editorState.project)) {
    other.bases = other.bases.filter((b) => b !== qname);
  }
  editorState.project.associations = editorState.project.associations.filter(
    (a) => a.source !== qname && a.target !== qname,
  );
  bump();
}

function packageOfQname(qname: string): string {
  const i = qname.lastIndexOf(".");
  return i >= 0 ? qname.slice(0, i) : "";
}

// ---------- attribute / operation / base mutators ----------

export function defaultAttribute(): AttributeDraft {
  return {
    name: "field",
    type: "",
    visibility: "public" as Visibility,
    is_static: false,
    is_readonly: false,
    default: null,
    description: null,
    status: "unchanged",
  };
}

export function defaultOperation(): OperationDraft {
  return {
    name: "method",
    parameters: [],
    return_type: "",
    visibility: "public" as Visibility,
    is_static: false,
    is_abstract: false,
    description: null,
    status: "unchanged",
  };
}

export function setAttributes(qname: string, attrs: AttributeDraft[]): void {
  const cls = findClass(qname);
  if (!cls) return;
  cls.attributes = attrs;
  bump();
}

export function setOperations(qname: string, ops: OperationDraft[]): void {
  const cls = findClass(qname);
  if (!cls) return;
  cls.operations = ops;
  bump();
}

export function setBases(qname: string, bases: string[]): void {
  const cls = findClass(qname);
  if (!cls) return;
  cls.bases = bases;
  bump();
}

// ---------- association mutators ----------

export function defaultAssociation(source: string, target: string): AssociationDraft {
  return {
    source,
    target,
    name: null,
    source_multiplicity: null,
    target_multiplicity: null,
    source_role: null,
    target_role: null,
    status: "unchanged",
  };
}

export function addAssociation(a: AssociationDraft): void {
  editorState.project.associations.push(a);
  bump();
}

export function updateAssociation(index: number, next: AssociationDraft): void {
  if (index < 0 || index >= editorState.project.associations.length) return;
  editorState.project.associations[index] = next;
  bump();
}

export function removeAssociation(index: number): void {
  editorState.project.associations.splice(index, 1);
  bump();
}
