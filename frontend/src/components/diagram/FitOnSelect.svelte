<script lang="ts">
  import { untrack } from "svelte";
  import { useSvelteFlow } from "@xyflow/svelte";
  import {
    cycleRevealVia,
    diagramState,
    hideMany,
    requestRelayout,
    reveal,
    selectMany,
    selectSet,
    selectedIds,
    setSelected,
    type RevealDirection,
    type RevealVia,
  } from "../../lib/state/diagram.svelte";
  import { siblings, stepFrom } from "../../lib/reveal";

  // Fits the viewport on request and owns the canvas keys. The Keys menu of
  // the toolbar lists them for the user (`KEYS` in DiagramToolbar.svelte).
  // Must be mounted inside <SvelteFlowProvider> so useSvelteFlow has context.
  //
  // `allIds` is every node id of the diagram. A canvas passes it to turn on the
  // explorer keys (everything but `f`); its nodes must render
  // `highlightedNodeIds` and it must publish `diagramState.currentEdges`.
  let { allIds }: { allIds?: string[] } = $props();

  const { fitView, getNodes, getNode, getViewport, setCenter } = useSvelteFlow();

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

  // ---------- a short message at the bottom of the canvas ----------

  let root: HTMLElement | undefined = $state();
  let notice = $state("");
  let noticeTimer: ReturnType<typeof setTimeout> | undefined;
  function notify(message: string) {
    notice = message;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => (notice = ""), 2200);
  }

  // ---------- the selection, and moves over the graph ----------

  // What the keys act on: the selected node, the nodes `a` or Shift+click
  // selected, and the nodes SvelteFlow holds as selected (a Shift-drag box).
  function selection(): string[] {
    const ids = new Set(selectedIds());
    for (const n of getNodes()) if (n.selected) ids.add(n.id);
    return [...ids];
  }

  // Left to right, then top to bottom: the order the user reads the canvas in.
  function byPosition(ids: string[]): string[] {
    const at = new Map(getNodes().map((n) => [n.id, n.position]));
    const pos = (id: string) => at.get(id) ?? { x: 0, y: 0 };
    return [...ids].sort((a, b) => pos(a).x - pos(b).x || pos(a).y - pos(b).y);
  }

  // Pan to a node that is not fully on screen. The zoom stays: the detail tier
  // must not change under a key press.
  function bringIntoView(id: string) {
    const pane = root?.closest(".flow-wrap")?.querySelector(".svelte-flow");
    const el = pane?.querySelector(`.svelte-flow__node[data-id="${CSS.escape(id)}"]`);
    if (pane && el) {
      const p = pane.getBoundingClientRect();
      const r = el.getBoundingClientRect();
      if (r.left >= p.left && r.right <= p.right && r.top >= p.top && r.bottom <= p.bottom)
        return;
    }
    const n = getNode(id);
    if (!n) return;
    const w = n.measured?.width ?? 220;
    const h = n.measured?.height ?? 100;
    void setCenter(n.position.x + w / 2, n.position.y + h / 2, { zoom: getViewport().zoom });
  }

  function goTo(id: string) {
    setSelected(id, false);
    bringIntoView(id);
  }

  // The primary node and the visible nodes on its level, left to right.
  function level(): string[] {
    const id = diagramState.selectedClassId;
    const visible = new Set(getNodes().map((n) => n.id));
    if (!id || !visible.has(id)) return [];
    return byPosition(siblings(id, visible, diagramState.currentEdges, diagramState.revealVia));
  }

  // Tab / Shift+Tab: the next / previous node on the level of the primary one.
  function cycle(step: 1 | -1) {
    const ids = level();
    if (ids.length < 2) return;
    const i = ids.indexOf(diagramState.selectedClassId!);
    goTo(ids[(i + step + ids.length) % ids.length]);
  }

  // `w` / `s`: reveal what is hidden one step from the selection, then move
  // there. One selected node moves to one node. Several selected nodes (a
  // whole level, after Tab+a) move to the whole next level.
  function move(direction: RevealDirection) {
    const visible = new Set(getNodes().map((n) => n.id));
    const seeds = selection().filter((id) => visible.has(id));
    if (seeds.length === 0) return;
    const edges = diagramState.currentEdges;
    const next = stepFrom(seeds, edges, direction, diagramState.revealVia);
    const shown = next.filter((id) => visible.has(id));
    const revealed = reveal(direction, edges);
    const targets = [...shown, ...revealed];
    if (targets.length === 0) {
      notify(`Nothing ${direction === "up" ? "upstream" : "downstream"} of the selection`);
      return;
    }
    if (seeds.length > 1) {
      selectSet(targets);
    } else if (revealed.length > 0) {
      // The layout runs again and fits the view; positions are not final yet.
      setSelected(shown[0] ?? revealed[0], false);
    } else {
      goTo(byPosition(shown)[0]);
    }
  }

  const VIA_LABEL: Record<RevealVia, string> = {
    inheritance: "Inheritance",
    association: "References",
    all: "All",
  };

  // ---------- keys ----------

  // A form field takes the keys the user types. A checkbox is not one: the
  // list panel leaves the focus on the box that was ticked last.
  const TYPING =
    "input:not([type=checkbox]):not([type=radio]), textarea, select, [contenteditable]";
  const typing = (t: EventTarget | null) => !!(t as Element | null)?.closest?.(TYPING);

  // Tab is three things: a tap cycles the level, a hold with `a` selects the
  // level, a double tap switches "follow". So a tap acts on key-up, when it is
  // known that no `a` came, and a second tap inside this window is a double tap.
  const DOUBLE_TAP_MS = 300;
  let tabHeld = false;
  let tabChord = false;
  let tabBack = false;
  let lastTap = 0;
  // The selection before the last tap, the primary node first.
  let beforeTap: string[] = [];

  function onKey(e: KeyboardEvent) {
    if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
    // The canvas takes Tab only while an element is selected. With no
    // selection (Esc clears it) Tab moves the focus, as it does everywhere.
    if (e.key === "Tab" && allIds && (tabHeld || diagramState.selectedClassId)) {
      e.preventDefault();
      if (e.repeat) return;
      tabHeld = true;
      tabChord = false;
      tabBack = e.shiftKey;
      return;
    }
    if (e.repeat) return;
    const key = e.key.toLowerCase();
    if (key === "a" && allIds) {
      e.preventDefault();
      if (tabHeld) {
        tabChord = true;
        const ids = level();
        if (ids.length > 0) selectMany(ids);
      } else selectMany(getNodes().map((n) => n.id));
      return;
    }
    if (key === "escape") {
      if (allIds) setSelected(null);
      return;
    }
    if (allIds && (key === "w" || key === "s" || key === "l")) {
      e.preventDefault();
      if (key === "l") requestRelayout();
      else move(key === "w" ? "up" : "down");
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

  function onKeyUp(e: KeyboardEvent) {
    if (e.key !== "Tab" || !tabHeld) return;
    tabHeld = false;
    if (tabChord) return;
    const now = performance.now();
    if (now - lastTap < DOUBLE_TAP_MS) {
      // The first tap moved the selection one step. Put it back.
      lastTap = 0;
      if (beforeTap.length > 0) selectSet(beforeTap);
      notify(`Follow: ${VIA_LABEL[cycleRevealVia()]}`);
      return;
    }
    lastTap = now;
    const primary = diagramState.selectedClassId!;
    beforeTap = [primary, ...selectedIds().filter((id) => id !== primary)];
    cycle(tabBack ? -1 : 1);
  }

  // Ctrl+C: the selection as text for a document, one element per line:
  // `Namespace.Class (path/to/File.cs)`. Text the user selected on the page
  // is copied as usual.
  function onCopy(e: ClipboardEvent) {
    if (!allIds || typing(e.target) || !window.getSelection()?.isCollapsed) return;
    const ids = new Set(selection());
    const lines = byPosition([...ids]).map((id) => {
      const d = (getNode(id)?.data ?? {}) as {
        name?: string;
        qualifiedName?: string;
        location?: { file?: string } | null;
      };
      const name = d.qualifiedName || d.name || id;
      return d.location?.file ? `${name} (${d.location.file})` : name;
    });
    if (lines.length === 0 || !e.clipboardData) return;
    e.clipboardData.setData("text/plain", lines.join("\n"));
    e.preventDefault();
    notify(lines.length === 1 ? `Copied: ${lines[0]}` : `Copied ${lines.length} elements`);
  }
</script>

<svelte:window
  onkeydown={onKey}
  onkeyup={onKeyUp}
  onblur={() => (tabHeld = false)}
  oncopy={onCopy}
/>

<div class="canvas-notice" bind:this={root} role="status" aria-live="polite">
  {#if notice}<span>{notice}</span>{/if}
</div>

<style>
  .canvas-notice {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 14px;
    display: flex;
    justify-content: center;
    pointer-events: none;
    z-index: 6;
  }
  .canvas-notice span {
    background: rgba(17, 24, 39, 0.9);
    color: white;
    font-size: 0.8rem;
    padding: 0.3rem 0.7rem;
    border-radius: 5px;
    max-width: 80%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
