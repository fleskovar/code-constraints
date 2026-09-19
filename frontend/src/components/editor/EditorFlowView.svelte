<script lang="ts">
  // Renders the editor's SvelteFlow canvas.
  //
  // The graph (nodes + edges) is fetched from the backend via
  // POST /api/edit/model so it goes through the same `build_class_graph`
  // function that view mode uses. There is no parallel TypeScript graph
  // builder — that way attribute-derived associations, inheritance lookup
  // rules, dedup behaviour, etc. cannot diverge between the two modes.
  //
  // SvelteFlow is wired with `bind:nodes` / `bind:edges` to local $state
  // arrays. We deliberately avoid `useSvelteFlow().setNodes()` from inside
  // an $effect because that imperative path was observed to stall Svelte 5's
  // reactivity scheduler for unrelated $state in ancestor components.

  import { untrack } from "svelte";
  import {
    SvelteFlow,
    SvelteFlowProvider,
    Background,
    Controls,
    MiniMap,
    MarkerType,
    type Connection,
    type Edge,
    type Node,
  } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";

  import { api, type ClassGraphNode } from "../../lib/api";
  import { layoutNodes } from "../../lib/layout/dagre";
  import {
    diagramState,
    setNodePositions,
    setVisibleSet,
  } from "../../lib/state/diagram.svelte";
  import {
    editorState,
    findClass,
    flowGraphIndex,
  } from "../../lib/state/editor.svelte";
  import EditableClassNode from "./EditableClassNode.svelte";
  import FitOnSelect from "../diagram/FitOnSelect.svelte";
  import type { ClassFlowNode, ClassNodeData } from "../diagram/types";

  interface Props {
    onnodeclickid: (id: string) => void;
    onpaneclick: () => void;
    onnodedragstop: (event: { targetNode: Node | null }) => void;
    onconnect: (c: Connection) => void;
    onedgeclick: (edge: Edge) => void;
  }

  let {
    onnodeclickid,
    onpaneclick,
    onnodedragstop,
    onconnect,
    onedgeclick,
  }: Props = $props();

  const nodeTypes = { class: EditableClassNode };

  const NODE_WIDTH = 220;
  const HEADER_HEIGHT = 40;
  const ROW_HEIGHT = 18;
  function estimateHeight(c: ClassGraphNode): number {
    const rows =
      Math.max(c.attributes.length, 1) + Math.max(c.operations.length, 1);
    return HEADER_HEIGHT + rows * ROW_HEIGHT + 16;
  }

  // SvelteFlow's bound stores. We populate them when the server returns a
  // fresh graph.
  let nodes = $state<ClassFlowNode[]>([]);
  let edges = $state<Edge[]>([]);
  let fetchError = $state("");

  // Guards against stale responses: when the user fires several mutations
  // quickly we only honour the latest in-flight request.
  let requestSeq = 0;

  $effect(() => {
    const proj = editorState.project;
    // Touch nested slices so Svelte 5's per-property tracking picks up adds
    // and edits on classes / attributes / operations / bases / associations.
    void proj.packages;
    void proj.associations;
    for (const p of proj.packages) {
      void p.classes;
      for (const c of p.classes) {
        void c.attributes;
        void c.operations;
        void c.bases;
        void c.kind;
        void c.name;
        void c.qualified_name;
      }
    }

    const myToken = ++requestSeq;
    // Snapshot the proxy so we don't ship live $state references over JSON.
    const payload = $state.snapshot(proj);

    // Live diff preview: when a baseline is loaded and compare is on, the
    // server diffs baseline → draft and the graph comes back with statuses,
    // which EditableClassNode already knows how to style.
    const baseline =
      editorState.compare && editorState.baseline
        ? $state.snapshot(editorState.baseline)
        : null;

    (baseline
      ? api.editDiffGraph(baseline, payload)
      : api.editClassGraph(payload)
    )
      .then((graph) => {
        if (myToken !== requestSeq) return; // a newer request superseded us
        applyGraph(graph.nodes, graph.edges);
        fetchError = "";
      })
      .catch((e: Error) => {
        if (myToken !== requestSeq) return;
        fetchError = e.message;
      });
  });

  type GraphEdgeIn = {
    id: string;
    source: string;
    target: string;
    kind: "inheritance" | "association";
    multiplicity: string;
    status: string;
  };

  // Latest graph from the server; the effect below filters it by
  // `visibleClassIds`, so a view built in view mode carries over into the editor.
  let graphNodes = $state.raw<ClassGraphNode[]>([]);
  let graphEdges = $state.raw<GraphEdgeIn[]>([]);
  let knownIds: Set<string> | null = null;

  function applyGraph(gNodes: ClassGraphNode[], gEdges: GraphEdgeIn[]) {
    // Refresh the shared qname-by-id index so EditorCanvas can resolve
    // SvelteFlow click events back to model classes.
    flowGraphIndex.qnameById.clear();
    for (const n of gNodes) flowGraphIndex.qnameById.set(n.id, n.qualifiedName);

    // A class the user just added (or renamed) must not vanish behind the
    // active filter, so draft classes new to this graph join the visible set.
    const filter = untrack(() => diagramState.visibleClassIds);
    if (filter !== null && knownIds !== null) {
      const added = gNodes.filter(
        (n) => !knownIds!.has(n.id) && findClass(n.qualifiedName),
      );
      if (added.length) setVisibleSet([...filter, ...added.map((n) => n.id)]);
    }
    knownIds = new Set(gNodes.map((n) => n.id));
    graphNodes = gNodes;
    graphEdges = gEdges;
  }

  $effect(() => {
    const filter = diagramState.visibleClassIds;
    const gNodes = graphNodes.filter((n) => filter === null || filter.has(n.id));
    const shownIds = new Set(gNodes.map((n) => n.id));
    const gEdges = graphEdges.filter(
      (e) => shownIds.has(e.source) && shownIds.has(e.target),
    );

    // Untracked read so writing back into nodePositions doesn't re-fire us.
    const existingPositions = untrack(() => diagramState.nodePositions);
    const newOnes = gNodes.filter((n) => !existingPositions.has(n.id));
    const positions = new Map<string, { x: number; y: number }>(
      existingPositions,
    );
    if (newOnes.length) {
      const fresh = layoutNodes(
        gNodes.map((n) => ({
          id: n.id,
          width: NODE_WIDTH,
          height: estimateHeight(n),
        })),
        gEdges.map((e) => ({ source: e.source, target: e.target })),
        { direction: "BT", nodeSep: 60, rankSep: 100 },
      );
      for (const n of newOnes) {
        const p = fresh.get(n.id);
        if (p) positions.set(n.id, p);
      }
      untrack(() => setNodePositions(positions));
    }

    nodes = gNodes.map<ClassFlowNode>((n) => ({
      id: n.id,
      type: "class",
      data: n as ClassNodeData,
      position: positions.get(n.id) ?? { x: 0, y: 0 },
    }));
    edges = gEdges.map<Edge>((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.multiplicity || undefined,
      data: { kind: e.kind } as Record<string, unknown>,
      markerEnd: {
        type:
          e.kind === "inheritance"
            ? MarkerType.ArrowClosed
            : MarkerType.Arrow,
        color: e.kind === "inheritance" ? "#475569" : "#94a3b8",
      },
      style:
        e.kind === "inheritance"
          ? "stroke:#475569;stroke-width:1.5"
          : "stroke:#94a3b8;stroke-width:1",
    }));
  });

  // Re-run dagre over the current nodes when the panel requests a compact
  // layout. Mirrors ClassDiagramFlow's behaviour.
  $effect(() => {
    const token = diagramState.relayoutToken;
    if (token === 0) return;
    untrack(() => {
      if (nodes.length === 0) return;
      const positions = layoutNodes(
        nodes.map((n) => ({
          id: n.id,
          width: NODE_WIDTH,
          height: estimateHeight(n.data),
        })),
        edges.map((e) => ({ source: e.source, target: e.target })),
        { direction: "BT", nodeSep: 60, rankSep: 100 },
      );
      setNodePositions(positions);
      nodes = nodes.map((n) => ({
        ...n,
        position: positions.get(n.id) ?? n.position,
      }));
    });
  });
</script>

<div class="flow">
  {#if fetchError}
    <p class="error">Graph build failed: {fetchError}</p>
  {/if}
  <SvelteFlowProvider>
    <SvelteFlow
      bind:nodes
      bind:edges
      {nodeTypes}
      fitView
      minZoom={0.1}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
      onnodeclick={({ node }) => onnodeclickid(node.id)}
      {onpaneclick}
      {onnodedragstop}
      {onconnect}
      onedgeclick={({ edge }) => onedgeclick(edge)}
    >
      <Background />
      <Controls />
      <MiniMap pannable zoomable />
    </SvelteFlow>
    <FitOnSelect />
  </SvelteFlowProvider>
</div>

<style>
  .flow {
    flex: 1;
    min-height: 0;
    height: 100%;
    position: relative;
  }
  .error {
    position: absolute;
    top: 0.5rem;
    left: 50%;
    transform: translateX(-50%);
    background: #fef2f2;
    border: 1px solid #fca5a5;
    color: #b91c1c;
    padding: 0.4rem 0.75rem;
    border-radius: 4px;
    font-size: 0.8rem;
    z-index: 10;
    pointer-events: none;
  }
</style>
