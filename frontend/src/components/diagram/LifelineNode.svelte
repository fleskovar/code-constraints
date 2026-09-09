<script lang="ts">
  import { Handle, Position, type NodeProps, type Node } from "@xyflow/svelte";
  import type { LifelineNodeData } from "./sequenceTypes";

  let { data }: NodeProps<Node<LifelineNodeData, "lifeline">> = $props();

  const rows = $derived.by(() => {
    const out: number[] = [];
    for (let i = 0; i < data.rowCount; i++) out.push(i);
    return out;
  });

  function rowY(i: number): number {
    return data.headerH + i * data.rowH + data.rowH / 2;
  }
</script>

<div class="lifeline status-{data.status}">
  <div class="header" title={data.represents}>
    <div class="name">{data.name}</div>
    {#if data.represents}
      <div class="represents">: {data.represents}</div>
    {/if}
  </div>
  <div
    class="line"
    style="top: {data.headerH}px; height: {data.rowCount * data.rowH}px;"
  ></div>
  {#each rows as r (r)}
    <Handle
      type="source"
      position={Position.Left}
      id={"row-" + r + "-left"}
      style={"top: " + rowY(r) + "px; opacity: 0; pointer-events: none;"}
    />
    <Handle
      type="target"
      position={Position.Left}
      id={"row-" + r + "-left-t"}
      style={"top: " + rowY(r) + "px; opacity: 0; pointer-events: none;"}
    />
    <Handle
      type="source"
      position={Position.Right}
      id={"row-" + r + "-right"}
      style={"top: " + rowY(r) + "px; opacity: 0; pointer-events: none;"}
    />
    <Handle
      type="target"
      position={Position.Right}
      id={"row-" + r + "-right-t"}
      style={"top: " + rowY(r) + "px; opacity: 0; pointer-events: none;"}
    />
  {/each}
</div>

<style>
  .lifeline {
    position: relative;
    width: 140px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .header {
    background: #eef2ff;
    border: 1px solid #94a3b8;
    border-radius: 4px;
    padding: 8px 10px;
    text-align: center;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  }
  .name {
    font-weight: 600;
    font-size: 12px;
  }
  .represents {
    font-size: 10px;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
  }
  .line {
    position: absolute;
    left: 50%;
    width: 0;
    border-left: 2px dashed #94a3b8;
    pointer-events: none;
  }
  .status-added .header {
    background: #daf7dc;
    border-color: #16a34a;
  }
  .status-removed .header {
    background: #fbd7d7;
    border-color: #dc2626;
    text-decoration: line-through;
  }
  .status-changed .header {
    background: #fff6cc;
    border-color: #ca8a04;
  }
</style>
