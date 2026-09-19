<script lang="ts">
  import {
    api,
    type Change,
    type DiagramChange,
    type DiagramListing,
    type XmiInfo,
  } from "../lib/api";
  import { diagramState, setSelected } from "../lib/state/diagram.svelte";
  import {
    editorState,
    loadFromJson,
    setBaseline,
    setMode,
  } from "../lib/state/editor.svelte";
  import ClassDiagramFlow from "./diagram/ClassDiagramFlow.svelte";
  import PackageDiagramFlow from "./diagram/PackageDiagramFlow.svelte";
  import ActivityDiagramFlow from "./diagram/ActivityDiagramFlow.svelte";
  import SequenceDiagramFlow from "./diagram/SequenceDiagramFlow.svelte";
  import ClassListPanel from "./panel/ClassListPanel.svelte";
  import ClassDetailsPanel from "./panel/ClassDetailsPanel.svelte";
  import PackageListPanel from "./panel/PackageListPanel.svelte";
  import ActivityListPanel from "./panel/ActivityListPanel.svelte";
  import SequenceListPanel from "./panel/SequenceListPanel.svelte";
  import DiffWalkthrough from "./diff/DiffWalkthrough.svelte";
  import ActivityDiffWalkthrough from "./diff/ActivityDiffWalkthrough.svelte";
  import SequenceDiffWalkthrough from "./diff/SequenceDiffWalkthrough.svelte";
  import EditorCanvas from "./editor/EditorCanvas.svelte";
  import LayerDependenciesModal from "./panel/LayerDependenciesModal.svelte";
  import LayerClassesModal from "./panel/LayerClassesModal.svelte";
  import EdgeFocusModal from "./diagram/EdgeFocusModal.svelte";
  import DiagramToolbar from "./DiagramToolbar.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  let editorBusy = $state(false);
  let editorError = $state("");

  async function editCurrent() {
    editorError = "";
    editorBusy = true;
    try {
      const res = await fetch(`/api/xmi/${xmi.id}/source`);
      if (!res.ok) throw new Error(`fetch source: ${res.status}`);
      const blob = await res.blob();
      const draft = await api.editFromXmi(blob, `${xmi.id}.xmi`);
      loadFromJson(draft, `${xmi.id}.xmi`);
      setMode("edit");
      // Keep `visibleClassIds`: the editor graph uses the same stable ids, so
      // the view the user built carries over. Positions are re-laid out.
      diagramState.nodePositions = new Map();
    } catch (e) {
      editorError = (e as Error).message;
    } finally {
      editorBusy = false;
    }
  }

  async function saveFile() {
    editorError = "";
    editorBusy = true;
    try {
      const blob = await api.editToXmi(editorState.project, editorState.fileName);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = editorState.fileName || "diagram.xmi";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      editorState.dirty = false;
    } catch (err) {
      editorError = (err as Error).message;
    } finally {
      editorBusy = false;
    }
  }

  function exitEditor() {
    setMode("view");
    setBaseline(null);
    editorError = "";
  }

  async function compareVsReference() {
    editorError = "";
    editorBusy = true;
    try {
      setBaseline(await api.referenceModel(xmi.project_id));
    } catch (e) {
      editorError = (e as Error).message;
    } finally {
      editorBusy = false;
    }
  }

  async function setEditedAsReference() {
    editorError = "";
    editorBusy = true;
    try {
      const blob = await api.editToXmi(editorState.project, editorState.fileName);
      const res = await api.setReference(xmi.project_id, blob);
      editorError = `Saved as reference: ${res.path}`;
    } catch (err) {
      editorError = (err as Error).message;
    } finally {
      editorBusy = false;
    }
  }

  let listing = $state<DiagramListing | null>(null);
  let changes = $state<Change[]>([]);
  let activityChanges = $state<DiagramChange[]>([]);
  let sequenceChanges = $state<DiagramChange[]>([]);
  let selected = $state<{ diagram: string; name?: string } | null>(null);
  let error = $state("");

  $effect(() => {
    error = "";
    listing = null;
    changes = [];
    activityChanges = [];
    sequenceChanges = [];
    selected = null;
    setSelected(null);
    api
      .diagrams(xmi.id)
      .then((l) => {
        listing = l;
        if (l.classes) selected = { diagram: "class" };
        else if (l.packages) selected = { diagram: "package" };
        else if (l.activities[0]) selected = { diagram: "activity", name: l.activities[0] };
        else if (l.sequences[0]) selected = { diagram: "sequence", name: l.sequences[0] };
      })
      .catch((e: Error) => (error = e.message));
    api.changes(xmi.id).then((c) => (changes = c)).catch(() => {});
    api.activityChanges(xmi.id).then((c) => (activityChanges = c)).catch(() => {});
    api.sequenceChanges(xmi.id).then((c) => (sequenceChanges = c)).catch(() => {});
  });

  function pick(diagram: string, name?: string) {
    // Class, package, activity-node, and lifeline ids all flow through the
    // same `visibleClassIds` / `nodePositions` store. Clear on EVERY pick
    // (including activity/sequence name switches) so namespaces don't leak.
    selected = name ? { diagram, name } : { diagram };
    setSelected(null);
    diagramState.visibleClassIds = null;
    diagramState.nodePositions = new Map();
    diagramState.currentEdges = [];
    diagramState.revealStack = [];
  }

  const toolbarKind = $derived<"class" | "package" | "other">(
    selected?.diagram === "class"
      ? "class"
      : selected?.diagram === "package"
        ? "package"
        : "other",
  );
</script>

<div class="viewer">
<LayerDependenciesModal projectId={xmi.project_id} />
<LayerClassesModal {xmi} />
<EdgeFocusModal />
<header class="editor-bar">
  <div class="mode">
    <span class="label">Mode:</span>
    <button class:active={editorState.mode === "view"} onclick={exitEditor}>View</button>
    <button
      class:active={editorState.mode === "edit"}
      disabled={editorState.mode === "edit" || editorBusy}
      onclick={editCurrent}
    >Edit this diagram</button>
  </div>
  {#if editorState.mode !== "edit"}
    <DiagramToolbar kind={toolbarKind} {xmi} />
  {/if}
  <div class="editor-actions">
    {#if editorState.mode === "edit"}
      <button class="primary" onclick={saveFile} disabled={editorBusy}>
        Save .xmi{editorState.dirty ? " *" : ""}
      </button>
      <button
        onclick={setEditedAsReference}
        disabled={editorBusy}
        title="Save the edited diagram as this project's reference architecture (.cdec/reference.xmi)"
      >
        Set as reference
      </button>
      {#if !editorState.baseline}
        <button
          onclick={compareVsReference}
          disabled={editorBusy}
          title="Load .cdec/reference.xmi as a baseline and show live diff styling while editing"
        >
          Compare vs reference
        </button>
      {/if}
    {/if}
    {#if editorBusy}<span class="muted">…</span>{/if}
    {#if editorError}<span class="error">{editorError}</span>{/if}
  </div>
</header>

<div
  class="layout"
  class:has-changes={editorState.mode !== "edit" &&
    ((selected?.diagram === "class" && changes.length > 0) ||
      (selected?.diagram === "activity" && activityChanges.length > 0) ||
      (selected?.diagram === "sequence" && sequenceChanges.length > 0))}
>
  {#if editorState.mode === "edit"}
    <main class="canvas flow editor-fullwidth">
      <EditorCanvas />
    </main>
  {:else}
    <aside class="sidebar classes">
      <nav class="diagram-tabs">
        {#if listing}
          {#if listing.classes}
            <button
              class:active={selected?.diagram === "class"}
              onclick={() => pick("class")}>Class</button
            >
          {/if}
          {#if listing.packages}
            <button
              class:active={selected?.diagram === "package"}
              onclick={() => pick("package")}>Package</button
            >
          {/if}
          {#each listing.activities as a}
            <button
              class:active={selected?.diagram === "activity" && selected.name === a}
              onclick={() => pick("activity", a)}
              title="Activity: {a}">{a}</button
            >
          {/each}
          {#each listing.sequences as s}
            <button
              class:active={selected?.diagram === "sequence" && selected.name === s}
              onclick={() => pick("sequence", s)}
              title="Sequence: {s}">{s}</button
            >
          {/each}
        {/if}
      </nav>

      {#if error}
        <p class="muted error">{error}</p>
      {:else if !listing}
        <p class="muted">Loading…</p>
      {:else if selected?.diagram === "class"}
        <ClassListPanel {xmi} />
      {:else if selected?.diagram === "package"}
        <PackageListPanel {xmi} />
      {:else if selected?.diagram === "activity" && selected.name}
        <ActivityListPanel {xmi} name={selected.name} />
      {:else if selected?.diagram === "sequence" && selected.name}
        <SequenceListPanel {xmi} name={selected.name} />
      {/if}
    </aside>

    {#if selected?.diagram === "class"}
      <main class="canvas flow">
        <ClassDiagramFlow {xmi} />
        <ClassDetailsPanel {xmi} />
      </main>
      {#if changes.length > 0}
        <aside class="sidebar changes">
          <DiffWalkthrough {changes} />
        </aside>
      {/if}
    {:else if selected?.diagram === "package"}
      <main class="canvas flow">
        <PackageDiagramFlow {xmi} />
      </main>
    {:else if selected?.diagram === "activity" && selected.name}
      <main class="canvas flow">
        <ActivityDiagramFlow {xmi} name={selected.name} />
      </main>
      {#if activityChanges.length > 0}
        <aside class="sidebar changes">
          <ActivityDiffWalkthrough
            changes={activityChanges}
            activityName={selected.name}
            onpick={(n) => pick("activity", n)}
          />
        </aside>
      {/if}
    {:else if selected?.diagram === "sequence" && selected.name}
      <main class="canvas flow">
        <SequenceDiagramFlow {xmi} name={selected.name} />
      </main>
      {#if sequenceChanges.length > 0}
        <aside class="sidebar changes">
          <SequenceDiffWalkthrough
            changes={sequenceChanges}
            sequenceName={selected.name}
            onpick={(n) => pick("sequence", n)}
          />
        </aside>
      {/if}
    {:else}
      <main class="canvas flow"></main>
    {/if}
  {/if}
</div>
</div>

<style>
  .viewer {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .editor-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex: 0 0 auto;
  }
  .editor-bar .mode,
  .editor-bar .editor-actions {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .editor-bar .label {
    font-size: 0.8rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .editor-bar button {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.25rem 0.6rem;
    font-size: 0.85rem;
    cursor: pointer;
    color: var(--fg);
  }
  .editor-bar button:hover:not(:disabled) {
    background: var(--hover);
  }
  .editor-bar button.active {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .editor-bar button.primary {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .editor-bar button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .editor-fullwidth {
    grid-column: 1 / -1;
  }
  .layout {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: 260px 1fr;
    grid-template-areas: "classes canvas";
  }
  .layout.has-changes {
    grid-template-columns: 260px 1fr 280px;
    grid-template-areas: "classes canvas changes";
  }
  .sidebar.classes {
    grid-area: classes;
    border-right: 1px solid var(--border);
    background: var(--surface);
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .sidebar.changes {
    grid-area: changes;
    border-left: 1px solid var(--border);
    background: var(--surface);
    min-height: 0;
    overflow: hidden;
  }
  .canvas {
    grid-area: canvas;
  }
  .sidebar {
    border-right: 1px solid var(--border);
    background: var(--surface);
    overflow-y: auto;
  }
  .diagram-tabs {
    flex: 0 0 auto;
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .diagram-tabs button {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.25rem 0.6rem;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--fg);
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .diagram-tabs button:hover:not(.active) {
    background: var(--hover);
  }
  .diagram-tabs button.active {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .canvas {
    position: relative;
    overflow: hidden;
    background: var(--bg);
    min-width: 0;
    min-height: 0;
  }
  .error {
    color: #c63a3a;
  }
  .muted {
    color: var(--muted);
  }
</style>
