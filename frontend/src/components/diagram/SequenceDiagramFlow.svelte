<script lang="ts">
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
    type SequenceGraph,
    type XmiInfo,
  } from "../../lib/api";
  import {
    diagramState,
    setSelected,
    setNodePosition,
  } from "../../lib/state/diagram.svelte";
  import LifelineNode from "./LifelineNode.svelte";
  import MessageEdge from "./MessageEdge.svelte";
  import FragmentNode from "./FragmentNode.svelte";
  import type { FragmentNodeData, LifelineNodeData } from "./sequenceTypes";

  let { xmi, name }: { xmi: XmiInfo; name: string } = $props();

  type LifelineFlowNode = Node<LifelineNodeData, "lifeline">;
  type FragmentFlowNode = Node<FragmentNodeData, "fragment">;
  type FlowNode = LifelineFlowNode | FragmentFlowNode;

  const nodeTypes = { lifeline: LifelineNode, fragment: FragmentNode };
  const edgeTypes = { message: MessageEdge };

  const COL_W = 200;
  const HEADER_H = 56;
  const ROW_H = 44;
  const LIFELINE_W = 140;
  const FRAG_PAD_X = 24;
  const FRAG_PAD_Y = 6;

  let graph = $state<SequenceGraph | null>(null);
  let allNodes = $state<FlowNode[]>([]);
  let allEdges = $state<Edge[]>([]);
  let nodes = $state<FlowNode[]>([]);
  let edges = $state<Edge[]>([]);
  let error = $state("");

  $effect(() => {
    const xmiId = xmi.id;
    const n = name;
    error = "";
    graph = null;
    allNodes = [];
    allEdges = [];
    api
      .sequenceGraph(xmiId, n)
      .then((g) => {
        graph = g;
        const rowCount = Math.max(g.messages.length, 1);
        const columnById = new Map(g.lifelines.map((ll) => [ll.id, ll.column]));

        // Fragment nodes render BEHIND lifelines + messages. Order matters:
        // SvelteFlow paints in array order, so we push fragments first.
        const minCol = g.lifelines.length
          ? Math.min(...g.lifelines.map((l) => l.column))
          : 0;
        const maxCol = g.lifelines.length
          ? Math.max(...g.lifelines.map((l) => l.column))
          : 0;
        const fragX = minCol * COL_W - FRAG_PAD_X;
        const fragW = (maxCol - minCol) * COL_W + LIFELINE_W + FRAG_PAD_X * 2;
        const fragmentNodes: FragmentFlowNode[] = (g.fragments ?? []).map(
          (f) => ({
            id: f.id,
            type: "fragment",
            data: {
              kind: f.kind,
              label: f.label,
              width: fragW,
              height: (f.endRow - f.startRow + 1) * ROW_H + FRAG_PAD_Y * 2,
              status: f.status,
            },
            position: {
              x: fragX,
              y: HEADER_H + f.startRow * ROW_H - FRAG_PAD_Y,
            },
            draggable: false,
            selectable: false,
          }),
        );

        const lifelineNodes: LifelineFlowNode[] = g.lifelines.map((ll) => ({
          id: ll.id,
          type: "lifeline",
          data: {
            ...ll,
            rowCount,
            headerH: HEADER_H,
            rowH: ROW_H,
          } as LifelineNodeData,
          position: { x: ll.column * COL_W, y: 0 },
          draggable: true,
          selectable: true,
        }));

        allNodes = [...fragmentNodes, ...lifelineNodes];
        allEdges = g.messages.map<Edge>((m) => {
          const senderCol = columnById.get(m.sender) ?? 0;
          const receiverCol = columnById.get(m.receiver) ?? 0;
          const selfCall = m.sender === m.receiver;
          // Pick which side of each lifeline the edge attaches to so it always
          // goes outward toward the other lifeline.
          let sourceHandle: string;
          let targetHandle: string;
          if (selfCall) {
            sourceHandle = `row-${m.row}-right`;
            targetHandle = `row-${m.row}-right-t`;
          } else if (receiverCol > senderCol) {
            sourceHandle = `row-${m.row}-right`;
            targetHandle = `row-${m.row}-left-t`;
          } else {
            sourceHandle = `row-${m.row}-left`;
            targetHandle = `row-${m.row}-right-t`;
          }
          const color =
            m.status === "added"
              ? "#16a34a"
              : m.status === "removed"
                ? "#dc2626"
                : "#1f2937";
          return {
            id: m.id,
            source: m.sender,
            target: m.receiver,
            sourceHandle,
            targetHandle,
            type: "message",
            data: {
              label: m.label,
              guard: m.guard ?? "",
              isReturn: m.isReturn,
              status: m.status,
              selfCall,
            },
            markerEnd: {
              type: m.isReturn ? MarkerType.Arrow : MarkerType.ArrowClosed,
              color,
            },
          };
        });
      })
      .catch((e: Error) => (error = e.message));
  });

  // Apply visibility + persisted positions. visibleClassIds (mode-agnostic)
  // holds lifeline ids here; hiding a lifeline also drops messages touching it.
  // Fragments are not toggle-able — they always show. They're cheap to render
  // and hiding them based on partial lifeline visibility would be confusing.
  $effect(() => {
    const filter = diagramState.visibleClassIds;
    const visibleN =
      filter === null
        ? allNodes
        : allNodes.filter((n) => n.type === "fragment" || filter.has(n.id));
    const visibleLifelineIds = new Set(
      visibleN.filter((n) => n.type === "lifeline").map((n) => n.id),
    );
    const visibleE =
      filter === null
        ? allEdges
        : allEdges.filter(
            (e) =>
              visibleLifelineIds.has(e.source) &&
              visibleLifelineIds.has(e.target),
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
</script>

{#if error}
  <p class="error">{error}</p>
{:else if !graph}
  <p class="muted">Loading sequence…</p>
{:else}
  <div class="flow-wrap">
    <SvelteFlowProvider>
      <SvelteFlow
        bind:nodes
        bind:edges
        {nodeTypes}
        {edgeTypes}
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
