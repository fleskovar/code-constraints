<script lang="ts">
  import { Handle, Position, type Node, type NodeProps } from "@xyflow/svelte";
  import type { PackageGraphNode } from "../../lib/api";
  import { diagramState } from "../../lib/state/diagram.svelte";

  type Data = PackageGraphNode & Record<string, unknown>;
  let { data, id, selected }: NodeProps<Node<Data, "package">> = $props();

  const isHighlighted = $derived(
    diagramState.selectedClassId === id ||
      diagramState.highlightedNodeIds.has(id),
  );
</script>

<div class="package-node status-{data.status}" class:selected class:highlighted={isHighlighted}>
  <Handle type="target" position={Position.Top} />
  <span class="folder-tab"></span>
  <div class="body">
    <div class="title">{data.name}</div>
    {#if data.parentQname}
      <div class="qname">{data.parentQname}</div>
    {/if}
    <div class="badge">{data.classCount} class{data.classCount === 1 ? "" : "es"}</div>
  </div>
  <Handle type="source" position={Position.Bottom} />
</div>

<style>
  .package-node {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 11px;
    min-width: 160px;
    border: 1px solid #94a3b8;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
    position: relative;
    padding-top: 0;
  }
  .folder-tab {
    display: block;
    width: 40%;
    height: 10px;
    border: 1px solid #94a3b8;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    background: #f1f5f9;
    margin-left: 8px;
    margin-top: -10px;
    margin-bottom: 0;
  }
  .body {
    padding: 6px 10px 8px;
    background: #f8fafc;
    border-radius: 0 6px 6px 6px;
  }
  .title {
    font-weight: 600;
    color: #1f2937;
  }
  .qname {
    color: #64748b;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 10px;
    margin-top: 1px;
  }
  .badge {
    margin-top: 4px;
    color: #475569;
    font-size: 10px;
  }
  .package-node.highlighted {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.25);
  }
  .package-node.selected {
    border-color: #2563eb;
  }
  .package-node.status-added .body {
    background: #daf7dc;
  }
  .package-node.status-removed .body {
    background: #fbd7d7;
  }
  .package-node.status-changed .body {
    background: #fff6cc;
  }
</style>
