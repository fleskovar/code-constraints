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
    type PackageGraph,
    type PackageGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import { layoutNodes } from "../../lib/layout/dagre";
  import {
    diagramState,
    setSelected,
    clearEdgeSelection,
    selectEdge,
    setNodePosition,
    setNodePositions,
  } from "../../lib/state/diagram.svelte";
  import PackageNode from "./PackageNode.svelte";
  import FitOnSelect from "./FitOnSelect.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  type Data = PackageGraphNode & Record<string, unknown>;
  type PackageFlowNode = Node<Data, "package">;

  const nodeTypes = { package: PackageNode };

  let allNodes = $state<PackageFlowNode[]>([]);
  let allEdges = $state<Edge[]>([]);
  let graph = $state<PackageGraph | null>(null);
  let error = $state("");

  let nodes = $state<PackageFlowNode[]>([]);
  let edges = $state<Edge[]>([]);

  const NODE_WIDTH = 200;
  const NODE_HEIGHT = 80;

  $effect(() => {
    const filter = diagramState.visibleClassIds;
    const visibleN =
      filter === null ? allNodes : allNodes.filter((n) => filter.has(n.id));
    const visibleIds = new Set(visibleN.map((n) => n.id));
    const visibleE =
      filter === null
        ? allEdges
        : allEdges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target));
    const overrides = diagramState.nodePositions;
    nodes = visibleN.map((n) => ({
      ...n,
      position: overrides.get(n.id) ?? n.position,
    }));
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
    api
      .packageGraph(xmiId)
      .then((g) => {
        graph = g;
        diagramState.currentEdges = g.edges.map((e) => ({
          source: e.source,
          target: e.target,
        }));
        const positions = layoutNodes(
          g.nodes.map((n) => ({ id: n.id, width: NODE_WIDTH, height: NODE_HEIGHT })),
          g.edges.map((e) => ({ source: e.source, target: e.target })),
          { direction: "BT", nodeSep: 50, rankSep: 90 },
        );
        allNodes = g.nodes.map<PackageFlowNode>((n) => ({
          id: n.id,
          type: "package",
          data: n as Data,
          position: positions.get(n.id) ?? { x: 0, y: 0 },
        }));
        allEdges = g.edges.map<Edge>((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          markerEnd: { type: MarkerType.Arrow, color: "#475569" },
          style: "stroke:#475569;stroke-width:1.5",
        }));
      })
      .catch((e: Error) => (error = e.message));
  });

  function onDragStop({ targetNode }: { targetNode: Node | null }) {
    if (!targetNode) return;
    setNodePosition(targetNode.id, { ...targetNode.position });
  }

  function onEdgeClick(edge: Edge) {
    selectEdge(edge.id, edge.source, edge.target);
  }

  // Re-run dagre on the currently visible subgraph when the panel requests it.
  $effect(() => {
    const token = diagramState.relayoutToken;
    if (token === 0) return;
    untrack(() => {
      if (nodes.length === 0) return;
      const visibleIds = new Set(nodes.map((n) => n.id));
      const positions = layoutNodes(
        nodes.map((n) => ({ id: n.id, width: NODE_WIDTH, height: NODE_HEIGHT })),
        edges
          .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
          .map((e) => ({ source: e.source, target: e.target })),
        { direction: "BT", nodeSep: 50, rankSep: 90 },
      );
      setNodePositions(positions);
    });
  });
</script>

{#if error}
  <p class="error">{error}</p>
{:else if !graph}
  <p class="muted">Loading package graph…</p>
{:else}
  <div class="flow-wrap">
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
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
      </SvelteFlow>
      <FitOnSelect />
    </SvelteFlowProvider>
  </div>
{/if}

<style>
  .flow-wrap {
    height: 100%;
    width: 100%;
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
