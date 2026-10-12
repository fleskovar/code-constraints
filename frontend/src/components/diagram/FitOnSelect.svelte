<script lang="ts">
  import { untrack } from "svelte";
  import { useSvelteFlow } from "@xyflow/svelte";
  import {
    diagramState,
    hideMany,
    selectMany,
    selectedIds,
  } from "../../lib/state/diagram.svelte";

  // Fits the viewport on request and owns the canvas keys: `f` fits on the
  // selection, `a` selects every node on the canvas, `h` hides the selection.
  // Must be mounted inside <SvelteFlowProvider> so useSvelteFlow has context.
  //
  // `allIds` is every node id of the diagram. A canvas passes it to turn on the
  // `a` and `h` keys; its nodes must render `highlightedNodeIds`.
  let { allIds }: { allIds?: string[] } = $props();

  const { fitView, getNodes } = useSvelteFlow();

  // No fit here takes a `duration`. An animated fit flies through a far lower
  // zoom on its way, and a node that mounts mid-flight restarts it. The
  // interrupted flight reports that transit zoom to `onmoveend`, the detail
  // tier changes, every node is re-seeded, and the flight can stop half way.
  function fit(ids: string[]) {
    void fitView({ nodes: ids.map((id) => ({ id })), padding: 0.3, maxZoom: 1.3 });
  }

  // A selection made away from the canvas asks for a fit through `fitToken`.
  // A click on a canvas node does not: only the `f` key moves the view then.
  $effect(() => {
    if (diagramState.fitToken === 0) return;
    const id = untrack(() => diagramState.selectedClassId);
    if (!id) return;
    // Defer one tick so fitView doesn't write into SvelteFlow's internal node
    // store while we're still inside the user-state effect (which xyflow
    // otherwise warns about as a synchronous update during render).
    queueMicrotask(() => fit([id]));
  });

  // After a re-layout, refit the whole visible subgraph. We defer two ticks
  // so the position updates have propagated through bind:nodes and the new
  // node measurements are settled before fitView reads them.
  $effect(() => {
    const token = diagramState.relayoutToken;
    if (token === 0) return;
    queueMicrotask(() => {
      queueMicrotask(() => {
        void fitView({ padding: 0.2 });
      });
    });
  });

  // What `f` and `h` act on: the selected node, the nodes `a` selected, and
  // the nodes SvelteFlow holds as selected (Ctrl-click, Shift-drag box).
  function selection(): string[] {
    const ids = new Set(selectedIds());
    for (const n of getNodes()) if (n.selected) ids.add(n.id);
    return [...ids];
  }

  function onKey(e: KeyboardEvent) {
    if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return;
    // Ignored while the user types in a form field. A checkbox is not one: the
    // list panel leaves the focus on the box that was ticked last.
    const t = e.target as Element | null;
    if (
      t?.closest?.(
        "input:not([type=checkbox]):not([type=radio]), textarea, select, [contenteditable]",
      )
    )
      return;
    const key = e.key.toLowerCase();
    if (key === "a" && allIds) {
      e.preventDefault();
      selectMany(getNodes().map((n) => n.id));
      return;
    }
    if (key !== "f" && !(key === "h" && allIds)) return;
    // A selected edge owns `f` (Inspect edge), and an edge cannot be hidden.
    if (diagramState.selectedEdgeId) return;
    const ids = selection();
    if (ids.length === 0) return;
    e.preventDefault();
    if (key === "f") fit(ids);
    else hideMany(ids, allIds!);
  }
</script>

<svelte:window onkeydown={onKey} />
