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
    toggleCompare,
  } from "../lib/state/editor.svelte";
  import { openLayers } from "../lib/state/layers.svelte";
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
  import ToolbarMenu from "./ToolbarMenu.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  let busy = $state(false);
  let status = $state<{ kind: "ok" | "error"; msg: string } | null>(null);

  function report(kind: "ok" | "error", msg: string) {
    status = { kind, msg };
    if (kind === "ok") setTimeout(() => (status = null), 5000);
  }

  // Run one bar action: show the busy marker, report a thrown error.
  async function run(action: () => Promise<void>) {
    status = null;
    busy = true;
    try {
      await action();
    } catch (e) {
      report("error", (e as Error).message);
    } finally {
      busy = false;
    }
  }

  const editCurrent = () =>
    run(async () => {
      const res = await fetch(`/api/xmi/${xmi.id}/source`);
      if (!res.ok) throw new Error(`fetch source: ${res.status}`);
      const draft = await api.editFromXmi(await res.blob(), `${xmi.id}.xmi`);
      loadFromJson(draft, `${xmi.id}.xmi`);
      setMode("edit");
      // Keep `visibleClassIds`: the editor graph uses the same stable ids, so
      // the view the user built carries over. Positions are re-laid out.
      diagramState.nodePositions = new Map();
    });

  function download(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  const saveXmi = () =>
    run(async () => {
      const name = editorState.fileName || "diagram.xmi";
      download(await api.editToXmi(editorState.project, name), name);
      editorState.dirty = false;
    });

  function saveJson() {
    const name = (editorState.fileName || "diagram.xmi").replace(/\.xmi$/i, ".json");
    const body = JSON.stringify($state.snapshot(editorState.project), null, 2);
    download(new Blob([body], { type: "application/json" }), name);
    editorState.dirty = false;
  }

  // The next "Edit" reloads the model from the parse, so unsaved edits are
  // lost once the user leaves. Ask first.
  function leaveEditor() {
    if (editorState.mode !== "edit") return;
    if (
      editorState.dirty &&
      !confirm("You have unsaved edits. Leave edit mode and discard them?")
    )
      return;
    setMode("view");
    setBaseline(null);
    status = null;
  }

  // Load .cdec/reference.xmi as the diff baseline once, then toggle it.
  const toggleReferenceCompare = () =>
    run(async () => {
      if (editorState.baseline) toggleCompare();
      else setBaseline(await api.referenceModel(xmi.project_id));
    });

  // View mode saves the parsed diagram; edit mode saves the draft. Either way
  // it overwrites the file the `reference-architecture` rule gates against.
  function setAsReference() {
    const what = editorState.mode === "edit" ? "the edited diagram" : "this diagram";
    if (
      !confirm(
        `Overwrite .cdec/reference.xmi with ${what}? ` +
          "cdec check compares the code against this file.",
      )
    )
      return;
    void run(async () => {
      let blob: Blob;
      if (editorState.mode === "edit") {
        blob = await api.editToXmi(editorState.project, editorState.fileName);
      } else {
        const res = await fetch(`/api/xmi/${xmi.id}/source`);
        if (!res.ok) throw new Error(`fetch source: ${res.status}`);
        blob = await res.blob();
      }
      const saved = await api.setReference(xmi.project_id, blob);
      report("ok", `Saved as reference: ${saved.path}`);
    });
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

  // Space jumps to the search box of the left panel, except in two cases. A
  // text field keeps the key to type a space. A control that the user reached
  // with Tab keeps it too, because Space is how the keyboard activates a button
  // or a checkbox. A control that only holds the focus after a mouse click does
  // not: the user is on the canvas, not on that control. `:focus-visible`
  // cannot tell the two apart, Chrome turns it on at the first key press.
  let tabbed = false;
  function onKey(e: KeyboardEvent) {
    if (e.key === "Tab") tabbed = true;
    if (e.key !== " " || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target as Element | null;
    if (
      t?.closest?.(
        "input:not([type=checkbox]):not([type=radio]), textarea, [contenteditable]",
      )
    )
      return;
    if (tabbed && t?.closest?.("input, select, button, summary, a")) return;
    const box = document.querySelector<HTMLInputElement>('.search input[type="search"]');
    if (!box) return;
    e.preventDefault();
    box.focus();
    box.select();
  }

  const toolbarKind = $derived<"class" | "package" | "other">(
    selected?.diagram === "class"
      ? "class"
      : selected?.diagram === "package"
        ? "package"
        : "other",
  );
</script>

<svelte:window onkeydown={onKey} onpointerdown={() => (tabbed = false)} />

<div class="viewer">
<LayerDependenciesModal projectId={xmi.project_id} />
<LayerClassesModal {xmi} />
<EdgeFocusModal />
<header class="editor-bar">
  <div class="mode" role="group" aria-label="Mode">
    <button
      class:active={editorState.mode === "view"}
      aria-pressed={editorState.mode === "view"}
      onclick={leaveEditor}
      title="Explore the parsed diagram"
    >View</button>
    <button
      class:active={editorState.mode === "edit"}
      aria-pressed={editorState.mode === "edit"}
      disabled={busy}
      onclick={() => editorState.mode !== "edit" && editCurrent()}
      title="Edit a copy of this diagram. The source code does not change."
    >Edit</button>
  </div>
  {#if editorState.mode !== "edit"}
    <DiagramToolbar kind={toolbarKind} />
  {/if}
  <div class="editor-actions">
    {#if busy}<span class="muted">…</span>{/if}
    {#if status}<span class="status {status.kind}">{status.msg}</span>{/if}
    {#if editorState.mode === "edit"}
      <button
        class="primary"
        onclick={saveXmi}
        disabled={busy}
        title="Download the edited diagram as XMI"
      >
        Save .xmi{editorState.dirty ? " *" : ""}
      </button>
      <button
        onclick={saveJson}
        disabled={busy}
        title="Download the edited diagram as model JSON, the format that cdec propose reads"
      >
        Save .json
      </button>
    {/if}
    <ToolbarMenu
      label="Architecture"
      align="right"
      title="Project actions: the layer rules and the reference architecture"
    >
      <button onclick={() => openLayers(null)}>Layers &amp; rules…</button>
      <span class="menu-note">The layers and their allowed dependencies (rules.yaml).</span>
      <hr />
      {#if editorState.mode === "edit"}
        <button onclick={toggleReferenceCompare} disabled={busy}>
          {editorState.baseline && editorState.compare
            ? "Stop comparing with reference"
            : "Compare with reference"}
        </button>
        <span class="menu-note">Show live diff colours against .cdec/reference.xmi while you edit.</span>
      {/if}
      <button onclick={setAsReference} disabled={busy}>
        {editorState.mode === "edit" ? "Set edited diagram as reference…" : "Set as reference…"}
      </button>
      <span class="menu-note">Overwrite .cdec/reference.xmi, the model that cdec check compares the code against.</span>
    </ToolbarMenu>
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
  /* Scoped to the bar's own buttons so menu items keep the menu style. */
  .mode button,
  .editor-actions > button {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.25rem 0.6rem;
    font-size: 0.85rem;
    cursor: pointer;
    color: var(--fg);
    white-space: nowrap;
  }
  .mode button:hover:not(:disabled):not(.active),
  .editor-actions > button:hover:not(:disabled) {
    background: var(--hover);
  }
  /* View | Edit reads as one two-state switch. */
  .editor-bar .mode {
    gap: 0;
  }
  .mode button:first-child {
    border-radius: 4px 0 0 4px;
  }
  .mode button:last-child {
    border-radius: 0 4px 4px 0;
    border-left: none;
  }
  .mode button.active,
  .editor-actions > button.primary {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .mode button:disabled,
  .editor-actions > button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .status {
    font-size: 0.75rem;
    max-width: 28rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status.ok {
    color: #166534;
  }
  .status.error {
    color: #c63a3a;
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
