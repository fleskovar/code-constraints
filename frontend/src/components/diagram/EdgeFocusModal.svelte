<script lang="ts">
  import {
    SvelteFlow,
    SvelteFlowProvider,
    Background,
    Controls,
    MarkerType,
    type Edge,
  } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";

  import Modal from "../editor/Modal.svelte";
  import ClassNode from "./ClassNode.svelte";
  import type { ClassFlowNode, ClassNodeData } from "./types";
  import { edgeFocus, closeEdgeFocus } from "../../lib/state/edgeFocus.svelte";

  const nodeTypes = { class: ClassNode };

  // Node width mirrors ClassDiagramFlow; place the two nodes side by side, close
  // together, with a small horizontal gap.
  const NODE_WIDTH = 220;
  const GAP = 80;

  // Reactive bindable copies SvelteFlow drives. Rebuilt whenever the focused
  // edge/endpoints change.
  let nodes = $state<ClassFlowNode[]>([]);
  let edges = $state<Edge[]>([]);

  $effect(() => {
    const { source, target, edge } = edgeFocus;
    if (!source || !target || !edge) {
      nodes = [];
      edges = [];
      return;
    }
    // The reference originates on the source class. Tag the source node with the
    // member signatures the edge carries so ClassNode emphasises those rows /
    // its header (inheritance).
    const members = edge.members ?? [];
    const sourceData: ClassNodeData = {
      ...source,
      highlightAttributes: members
        .filter((m) => m.kind === "attribute")
        .map((m) => m.signature),
      highlightOperations: members
        .filter((m) => m.kind === "operation")
        .map((m) => m.signature),
      highlightHeader: members.some((m) => m.kind === "inheritance"),
    };
    nodes = [
      {
        id: source.id,
        type: "class",
        data: sourceData,
        position: { x: 0, y: 0 },
      },
      {
        id: target.id,
        type: "class",
        data: target as ClassNodeData,
        position: { x: NODE_WIDTH + GAP, y: 0 },
      },
    ];
    // Reproduce ClassDiagramFlow's render rules: inheritance renders base→derived
    // (source/target swapped) with the hollow-triangle marker; associations keep
    // their orientation with an arrow head + multiplicity label.
    const inheritance = edge.kind === "inheritance";
    edges = [
      {
        id: edge.id,
        source: inheritance ? edge.target : edge.source,
        target: inheritance ? edge.source : edge.target,
        label: edge.multiplicity || undefined,
        markerStart: inheritance ? "uml-inheritance" : undefined,
        markerEnd: inheritance
          ? undefined
          : { type: MarkerType.Arrow, color: "#94a3b8" },
        style: inheritance
          ? "stroke:#475569;stroke-width:1.5"
          : "stroke:#94a3b8;stroke-width:1",
      },
    ];
  });
</script>

<Modal
  open={edgeFocus.open}
  title="Edge focus"
  width="780px"
  onclose={closeEdgeFocus}
>
  <div class="edge-focus-canvas">
    <!-- Hollow-triangle marker for UML generalization (copied from
         ClassDiagramFlow) so inheritance edges render correctly here too. -->
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
    {#if edgeFocus.open}
      <SvelteFlowProvider>
        <SvelteFlow
          bind:nodes
          bind:edges
          {nodeTypes}
          fitView
          minZoom={0.2}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showLock={false} />
        </SvelteFlow>
      </SvelteFlowProvider>
    {/if}
  </div>
</Modal>

<style>
  .edge-focus-canvas {
    position: relative;
    width: 100%;
    height: 460px;
    background: var(--bg);
    border-radius: 4px;
    overflow: hidden;
  }
</style>
