<script lang="ts">
  import type { Connection, Edge, Node } from "@xyflow/svelte";

  import {
    diagramState,
    setSelected,
    setNodePosition,
  } from "../../lib/state/diagram.svelte";
  import {
    defaultClass,
    editorState,
    findClass,
    flowGraphIndex,
    openAssocModal,
    openClassModal,
    openEdgePicker,
    modalState,
    removeClass,
    toggleCodePanel,
    toggleCompare,
  } from "../../lib/state/editor.svelte";
  import EditorFlowView from "./EditorFlowView.svelte";
  import EditorTextPanel from "./EditorTextPanel.svelte";

  // Resolve a SvelteFlow node id back to a class qualified name. The map is
  // populated by EditorFlowView each time the backend returns a fresh graph.
  function qnameOf(id: string): string | undefined {
    return flowGraphIndex.qnameById.get(id);
  }

  function onDragStop({ targetNode }: { targetNode: Node | null }) {
    if (!targetNode) return;
    setNodePosition(targetNode.id, { ...targetNode.position });
  }

  function onConnect(c: Connection) {
    if (!c.source || !c.target || c.source === c.target) return;
    openEdgePicker(
      c.source,
      c.target,
      qnameOf(c.source) ?? c.source,
      qnameOf(c.target) ?? c.target,
    );
  }

  function onEditClassEvent(e: Event) {
    const { qualifiedName } = (e as CustomEvent).detail as {
      qualifiedName: string;
    };
    const cls = findClass(qualifiedName);
    if (!cls) return;
    openClassModal(cls, true, qualifiedName);
  }

  function openAddClassModal() {
    openClassModal(defaultClass({ name: "NewClass" }), false, null);
  }

  function onEdgeClick(edge: Edge) {
    const kind = (edge.data as { kind?: string } | undefined)?.kind;
    if (kind === "inheritance") {
      const sourceQname = qnameOf(edge.source);
      const cls = sourceQname ? findClass(sourceQname) : null;
      if (cls && sourceQname) {
        openClassModal(cls, true, sourceQname);
      }
      return;
    }
    const sQ = qnameOf(edge.source);
    const tQ = qnameOf(edge.target);
    if (!sQ || !tQ) return;
    const idx = editorState.project.associations.findIndex(
      (a) => a.source === sQ && a.target === tQ,
    );
    if (idx >= 0) {
      openAssocModal(
        { ...editorState.project.associations[idx] },
        idx,
        true,
      );
    }
  }

  // Delete / Backspace removes the selected class (with its inheritance refs
  // and associations). Ignored while typing or while a modal is open.
  function onKeydown(e: KeyboardEvent) {
    if (e.key !== "Delete" && e.key !== "Backspace") return;
    if (modalState.classOpen || modalState.assocOpen || modalState.edgePickerOpen)
      return;
    const t = e.target as HTMLElement | null;
    if (
      t &&
      (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)
    )
      return;
    const selectedId = diagramState.selectedClassId;
    if (!selectedId) return;
    const qname = qnameOf(selectedId);
    if (!qname || !findClass(qname)) return;
    e.preventDefault();
    removeClass(qname);
    setSelected(null);
  }

  $effect(() => {
    const handler = (e: Event) => onEditClassEvent(e);
    window.addEventListener("editor:edit-class", handler);
    return () => window.removeEventListener("editor:edit-class", handler);
  });
</script>

<svelte:window onkeydown={onKeydown} />

<div class="flow-wrap">
  <div class="toolbar">
    <button type="button" onclick={openAddClassModal}>+ Add class</button>
    <button
      type="button"
      class:active={editorState.codePanelOpen}
      onclick={toggleCodePanel}
      title="Edit the model as JSON side-by-side with the canvas"
    >Code</button>
    {#if editorState.baseline}
      <button
        type="button"
        class:active={editorState.compare}
        onclick={toggleCompare}
        title="Toggle live diff styling against the loaded baseline"
      >Compare{editorState.compare ? " ✓" : ""}</button>
    {/if}
    <span class="hint"
      >Drag between nodes to draw a relationship · Delete removes the selected
      class</span
    >
  </div>
  <div class="split">
    <div class="canvas-cell">
      <EditorFlowView
        onnodeclickid={(id) => setSelected(id)}
        onpaneclick={() => setSelected(null)}
        onnodedragstop={onDragStop}
        onconnect={onConnect}
        onedgeclick={onEdgeClick}
      />
    </div>
    {#if editorState.codePanelOpen}
      <div class="code-cell">
        <EditorTextPanel />
      </div>
    {/if}
  </div>
</div>

<style>
  .flow-wrap {
    height: 100%;
    width: 100%;
    display: flex;
    flex-direction: column;
  }
  .toolbar {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border, #e2e8f0);
    background: var(--surface, #fff);
  }
  .toolbar button {
    background: var(--surface, #fff);
    border: 1px solid var(--border, #cbd5e1);
    border-radius: 4px;
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .toolbar button:hover {
    background: var(--hover, #f1f5f9);
  }
  .toolbar button.active {
    background: var(--accent, #2563eb);
    color: white;
    border-color: var(--accent, #2563eb);
  }
  .hint {
    font-size: 0.8rem;
    color: var(--muted, #64748b);
  }
  .split {
    flex: 1;
    min-height: 0;
    display: flex;
  }
  .canvas-cell {
    flex: 1;
    min-width: 0;
    min-height: 0;
  }
  .code-cell {
    flex: 0 0 clamp(320px, 34%, 560px);
    min-height: 0;
  }
</style>
