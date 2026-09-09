<script lang="ts">
  import { untrack } from "svelte";
  import {
    SvelteFlow,
    SvelteFlowProvider,
    Background,
    Controls,
    MarkerType,
    type Edge,
    type Node,
  } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";

  import {
    api,
    type ActivityGraph,
    type ActivityGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import { layoutNodes } from "../../lib/layout/dagre";
  import {
    diagramState,
    setSelected,
    setNodePosition,
    setNodePositions,
  } from "../../lib/state/diagram.svelte";
  import ActivityNode from "./ActivityNode.svelte";
  import FitOnSelect from "./FitOnSelect.svelte";

  let { xmi, name }: { xmi: XmiInfo; name: string } = $props();

  type Data = ActivityGraphNode & Record<string, unknown>;
  type FlowNode = Node<Data, "activity">;

  const nodeTypes = { activity: ActivityNode };

  let graph = $state<ActivityGraph | null>(null);
  let allNodes = $state<FlowNode[]>([]);
  let allEdges = $state<Edge[]>([]);
  let nodes = $state<FlowNode[]>([]);
  let edges = $state<Edge[]>([]);
  let error = $state("");

  function nodeSize(n: ActivityGraphNode): { w: number; h: number } {
    if (n.kind === "initial" || n.kind === "final") return { w: 30, h: 30 };
    if (n.kind === "decision" || n.kind === "merge") return { w: 120, h: 70 };
    if (n.kind === "fork" || n.kind === "join") return { w: 90, h: 16 };
    return { w: 140, h: 36 };
  }

  function edgeStyle(status: string): string {
    if (status === "added") return "stroke:#16a34a;stroke-width:1.8";
    if (status === "removed")
      return "stroke:#dc2626;stroke-width:1.8;stroke-dasharray:4 4";
    return "stroke:#475569;stroke-width:1.5";
  }

  $effect(() => {
    const xmiId = xmi.id;
    const n = name;
    error = "";
    graph = null;
    allNodes = [];
    allEdges = [];
    api
      .activityGraph(xmiId, n)
      .then((g: ActivityGraph) => {
        graph = g;
        const positions = layoutNodes(
          g.nodes.map((nn) => {
            const s = nodeSize(nn);
            return { id: nn.id, width: s.w, height: s.h };
          }),
          g.edges,
          { direction: "TB", nodeSep: 40, rankSep: 60 },
        );
        allNodes = g.nodes.map<FlowNode>((nn) => ({
          id: nn.id,
          type: "activity",
          data: nn as Data,
          position: positions.get(nn.id) ?? { x: 0, y: 0 },
          draggable: true,
        }));
        allEdges = g.edges.map<Edge>((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.guard || undefined,
          markerEnd: {
            type: MarkerType.Arrow,
            color:
              e.status === "added"
                ? "#16a34a"
                : e.status === "removed"
                  ? "#dc2626"
                  : "#475569",
          },
          style: edgeStyle(e.status),
        }));
      })
      .catch((e: Error) => (error = e.message));
  });

  // Re-seed bindable nodes/edges based on visibility filter + persisted positions.
  $effect(() => {
    const filter = diagramState.visibleClassIds;
    const visibleN =
      filter === null ? allNodes : allNodes.filter((n) => filter.has(n.id));
    const visibleIds = new Set(visibleN.map((n) => n.id));
    const visibleE =
      filter === null
        ? allEdges
        : allEdges.filter(
            (e) => visibleIds.has(e.source) && visibleIds.has(e.target),
          );
    const overrides = diagramState.nodePositions;
    nodes = visibleN.map((n) => ({
      ...n,
      position: overrides.get(n.id) ?? n.position,
    }));
    edges = [...visibleE];
  });

  function onDragStop({ targetNode }: { targetNode: Node | null }) {
    if (!targetNode) return;
    setNodePosition(targetNode.id, { ...targetNode.position });
  }

  $effect(() => {
    const token = diagramState.relayoutToken;
    if (token === 0) return;
    untrack(() => {
      if (nodes.length === 0) return;
      const visibleIds = new Set(nodes.map((n) => n.id));
      const layoutInputNodes = nodes.map((n) => {
        const s = nodeSize(n.data);
        return { id: n.id, width: s.w, height: s.h };
      });
      const layoutInputEdges = edges
        .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))
        .map((e) => ({ source: e.source, target: e.target }));
      const positions = layoutNodes(layoutInputNodes, layoutInputEdges, {
        direction: "TB",
        nodeSep: 40,
        rankSep: 60,
      });
      setNodePositions(positions);
    });
  });
</script>

{#if error}
  <p class="error">{error}</p>
{:else if !graph}
  <p class="muted">Loading activity…</p>
{:else}
  <div class="flow-wrap">
    <SvelteFlowProvider>
      <SvelteFlow
        bind:nodes
        bind:edges
        {nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        onnodeclick={({ node }) => setSelected(node.id)}
        onpaneclick={() => setSelected(null)}
        onnodedragstop={onDragStop}
      >
        <Background />
        <Controls />
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
