<script lang="ts">
  import { untrack } from "svelte";
  import {
    SvelteFlow,
    SvelteFlowProvider,
    Background,
    Controls,
    MiniMap,
    MarkerType,
    type Edge,
    type Node,
  } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";

  import {
    api,
    type ClassGraph,
    type ClassGraphEdge,
    type ClassGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import { layoutNodes } from "../../lib/layout/dagre";
  import {
    diagramState,
    setSelected,
    setVisibleSet,
    clearEdgeSelection,
    selectEdge,
    setNodePosition,
    setNodePositions,
    setLodTier,
    tierForZoom,
  } from "../../lib/state/diagram.svelte";
  import ClassNode from "./ClassNode.svelte";
  import FitOnSelect from "./FitOnSelect.svelte";
  import DiagramLegend from "./DiagramLegend.svelte";
  import type { ClassFlowNode, ClassNodeData } from "./types";
  import {
    setEdgeFocusGraph,
    openEdgeFocus,
  } from "../../lib/state/edgeFocus.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  const nodeTypes = { class: ClassNode };

  // Full unfiltered model — kept once so filter changes don't trigger refetch.
  let allNodes = $state<ClassFlowNode[]>([]);
  let allEdges = $state<Edge[]>([]);
  let graph = $state<ClassGraph | null>(null);
  let error = $state("");

  // Bindable working copies SvelteFlow drives (drag, selection, etc.)
  let nodes = $state<ClassFlowNode[]>([]);
  let edges = $state<Edge[]>([]);

  const NODE_WIDTH = 220;
  const HEADER_HEIGHT = 40;
  const ROW_HEIGHT = 18;
  function estimateHeight(c: ClassGraphNode): number {
    const rows =
      (diagramState.showAttributes ? c.attributes.length : 0) +
      (diagramState.showOperations ? c.operations.length : 0);
    return HEADER_HEIGHT + rows * ROW_HEIGHT + 16;
  }

  // Map a model edge to a dagre layout edge (rankdir "BT", so the fed target
  // ends up above the fed source). Inheritance keeps its child→base orientation
  // (base on top, weighted high to stay straight). Associations are REVERSED so
  // the field holder ranks ABOVE the type it references — the natural top-down
  // reading of a layered class diagram (controller → view → model).
  function toLayoutEdge(e: ClassGraphEdge) {
    const inheritance = e.kind === "inheritance";
    return {
      source: inheritance ? e.source : e.target,
      target: inheritance ? e.target : e.source,
      weight: inheritance ? 10 : 1,
    };
  }

  // Re-seed `nodes`/`edges` whenever:
  //  - the upstream model loads, OR
  //  - the visibility filter changes.
  // We apply any persisted position overrides on re-seed but DO NOT depend on
  // nodePositions reactively (the drag handler writes to it, which would
  // otherwise cause feedback).
  // Nodes that are a child in some inheritance edge (model stores child→parent).
  // At far LOD these are hidden so only base/standalone classes remain.
  const derivedIds = $derived(
    graph
      ? new Set(
          graph.edges
            .filter((e) => e.kind === "inheritance")
            .map((e) => e.source),
        )
      : new Set<string>(),
  );

  $effect(() => {
    const filter = diagramState.visibleClassIds;
    // Level-of-detail: at the `far` tier, drop derived classes and hide edges.
    const far = diagramState.lodEnabled && diagramState.lodTier === "far";
    const dropped = far ? derivedIds : null;
    const visibleN = allNodes.filter(
      (n) =>
        (filter === null || filter.has(n.id)) && !(dropped && dropped.has(n.id)),
    );
    const visibleIds = new Set(visibleN.map((n) => n.id));
    const overrides = diagramState.nodePositions;
    nodes = visibleN.map((n) => ({
      ...n,
      position: overrides.get(n.id) ?? n.position,
    }));
    if (far) {
      edges = [];
      return;
    }
    const visibleE = allEdges.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
    );
    // Overlay the selected-edge highlight so clicking an edge restyles it
    // reactively without touching the base `allEdges`.
    const selEdge = diagramState.selectedEdgeId;
    edges = visibleE.map((e) =>
      e.id === selEdge
        ? { ...e, style: "stroke:#2563eb;stroke-width:3", zIndex: 1000 }
        : e,
    );
  });

  $effect(() => {
    const xmiId = xmi.id;
    error = "";
    graph = null;
    allNodes = [];
    allEdges = [];
    setEdgeFocusGraph(null);
    api
      .classGraph(xmiId)
      .then((g) => {
        graph = g;
        setEdgeFocusGraph(g);
        // Publish model-orientation edges so the top toolbar can drive
        // focus / upstream / downstream reveal.
        diagramState.currentEdges = g.edges.map((e) => ({
          source: e.source,
          target: e.target,
        }));
        const positions = layoutNodes(
          g.nodes.map((n) => ({
            id: n.id,
            width: NODE_WIDTH,
            height: estimateHeight(n),
          })),
          g.edges.map(toLayoutEdge),
          { direction: "BT", nodeSep: 60, rankSep: 100 },
        );
        allNodes = g.nodes.map<ClassFlowNode>((n) => ({
          id: n.id,
          type: "class",
          data: n as ClassNodeData,
          position: positions.get(n.id) ?? { x: 0, y: 0 },
        }));
        // Apply a deep-link / proposal focus request now that qualified names
        // can be resolved to node ids. Unknown qnames are dropped silently so
        // a focus list from an older proposal survives model drift.
        const pending = diagramState.pendingFocusQnames;
        if (pending && pending.length > 0) {
          const wanted = new Set(pending);
          const ids = g.nodes
            .filter((n) => wanted.has(n.qualifiedName) || wanted.has(n.name))
            .map((n) => n.id);
          if (ids.length > 0) {
            setVisibleSet(ids);
            setSelected(ids[0]);
          }
          diagramState.pendingFocusQnames = null;
        }
        allEdges = g.edges.map<Edge>((e) => {
          const inheritance = e.kind === "inheritance";
          return {
            id: e.id,
            // Inheritance renders base→derived so the base node's bottom
            // handle connects to the derived node's top handle (the model
            // stores it child→parent). Associations keep their orientation.
            source: inheritance ? e.target : e.source,
            target: inheritance ? e.source : e.target,
            label: e.multiplicity || undefined,
            // UML generalization: a hollow triangle at the base end (start),
            // no marker at the derived end.
            markerStart: inheritance ? "uml-inheritance" : undefined,
            markerEnd: inheritance
              ? undefined
              : { type: MarkerType.Arrow, color: "#94a3b8" },
            style: inheritance
              ? "stroke:#475569;stroke-width:1.5"
              : "stroke:#94a3b8;stroke-width:1",
          };
        });
      })
      .catch((e: Error) => (error = e.message));
  });

  function onDragStop({ targetNode }: { targetNode: Node | null }) {
    if (!targetNode) return;
    setNodePosition(targetNode.id, { ...targetNode.position });
  }

  // Press `f` with an edge selected to pop up just its two endpoints, side by
  // side. Ignored while typing in a form field.
  function onKey(e: KeyboardEvent) {
    if (e.key !== "f" && e.key !== "F") return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target as HTMLElement | null;
    if (
      t &&
      (t.tagName === "INPUT" ||
        t.tagName === "TEXTAREA" ||
        t.isContentEditable)
    )
      return;
    const sel = diagramState.selectedEdgeId;
    if (!sel) return;
    e.preventDefault();
    openEdgeFocus(sel);
  }

  function onEdgeClick(edge: Edge) {
    // Map the rendered edge back to its model endpoints (inheritance edges are
    // rendered with source/target swapped).
    const model = graph?.edges.find((ge) => ge.id === edge.id);
    if (model) selectEdge(edge.id, model.source, model.target);
    else selectEdge(edge.id, edge.source, edge.target);
  }

  // Re-run dagre over the currently-visible subgraph when the panel asks for
  // a compact layout. Writes the new positions into `nodePositions`; the
  // visibility effect above picks them up and rewrites `nodes`.
  $effect(() => {
    const token = diagramState.relayoutToken;
    if (token === 0) return;
    untrack(() => {
      if (nodes.length === 0) return;
      const visibleIds = new Set(nodes.map((n) => n.id));
      const layoutInputNodes = nodes.map((n) => ({
        id: n.id,
        width: NODE_WIDTH,
        height: estimateHeight(n.data),
      }));
      // Feed dagre the model's semantic orientation (child→parent), NOT the
      // rendered `edges` — inheritance edges are swapped there, which under BT
      // would flip the base below the derived class on relayout.
      const layoutInputEdges = (graph?.edges ?? [])
        .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
        .map(toLayoutEdge);
      const positions = layoutNodes(layoutInputNodes, layoutInputEdges, {
        direction: "BT",
        nodeSep: 60,
        rankSep: 100,
      });
      setNodePositions(positions);
    });
  });
</script>

<svelte:window onkeydown={onKey} />

{#if error}
  <p class="error">{error}</p>
{:else if !graph}
  <p class="muted">Loading class graph…</p>
{:else}
  <div class="flow-wrap">
    <!-- Custom hollow-triangle marker for UML generalization (referenced by
         inheritance edges via markerStart="url(#uml-inheritance)"). -->
    <svg style="position:absolute;width:0;height:0" aria-hidden="true">
      <defs>
        <marker
          id="uml-inheritance"
          markerWidth="14"
          markerHeight="14"
          refX="11"
          refY="5"
          orient="auto-start-reverse"
          markerUnits="userSpaceOnUse"
        >
          <path
            d="M0,0 L11,5 L0,10 z"
            fill="#ffffff"
            stroke="#475569"
            stroke-width="1"
          />
        </marker>
      </defs>
    </svg>
    <SvelteFlowProvider>
      <SvelteFlow
        bind:nodes
        bind:edges
        {nodeTypes}
        fitView
        minZoom={0.1}
        maxZoom={2}
        onlyRenderVisibleElements
        elevateNodesOnSelect={false}
        elevateEdgesOnSelect={false}
        proOptions={{ hideAttribution: true }}
        onnodeclick={({ node }) => setSelected(node.id)}
        onedgeclick={({ edge }) => onEdgeClick(edge)}
        onpaneclick={() => {
          setSelected(null);
          clearEdgeSelection();
        }}
        onnodedragstop={onDragStop}
        onmoveend={(_e, viewport) => setLodTier(tierForZoom(viewport.zoom))}
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </SvelteFlow>
      <FitOnSelect />
    </SvelteFlowProvider>
    <DiagramLegend />
  </div>
{/if}

<style>
  .flow-wrap {
    height: 100%;
    width: 100%;
    position: relative;
  }
  .error {
    color: #c63a3a;
    padding: 1rem;
  }
  .muted {
    color: var(--muted);
    padding: 1rem;
  }
</style>
