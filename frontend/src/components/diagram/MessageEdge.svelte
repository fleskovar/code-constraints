<script lang="ts">
  import { BaseEdge, EdgeLabel, type EdgeProps } from "@xyflow/svelte";
  import type { MessageEdgeData } from "./sequenceTypes";

  let {
    sourceX,
    sourceY,
    targetX,
    targetY,
    markerEnd,
    data,
  }: EdgeProps & { data?: MessageEdgeData } = $props();

  const d: MessageEdgeData = $derived(
    data ?? {
      label: "",
      guard: "",
      isReturn: false,
      status: "unchanged",
      selfCall: false,
    },
  );

  const color = $derived(
    d.status === "added"
      ? "#16a34a"
      : d.status === "removed"
        ? "#dc2626"
        : "#1f2937",
  );

  const strokeDash = $derived(
    d.isReturn || d.status === "removed" ? "6 4" : "0",
  );

  const path = $derived.by(() => {
    if (d.selfCall) {
      const r = 24;
      return `M ${sourceX} ${sourceY} h ${r} v ${r} h -${r}`;
    }
    return `M ${sourceX} ${sourceY} L ${targetX} ${targetY}`;
  });

  const labelX = $derived(
    d.selfCall ? sourceX + 28 : (sourceX + targetX) / 2,
  );
  const labelY = $derived(
    d.selfCall ? sourceY + 12 : (sourceY + targetY) / 2 - 8,
  );
</script>

<BaseEdge
  {markerEnd}
  {path}
  style="stroke: {color}; stroke-width: 1.6; stroke-dasharray: {strokeDash}; fill: none;"
/>
<EdgeLabel x={labelX} y={labelY}>
  <div class="msg-label status-{d.status}" title={d.guard ? `guard: ${d.guard}` : undefined}>
    {#if d.guard}<span class="guard">[{d.guard}]</span> {/if}{d.label}
  </div>
</EdgeLabel>

<style>
  .msg-label {
    background: rgba(255, 255, 255, 0.92);
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 11px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #1f2937;
    white-space: nowrap;
  }
  .msg-label.status-added {
    color: #166534;
    background: #ecfdf5;
  }
  .msg-label.status-removed {
    color: #991b1b;
    background: #fef2f2;
    text-decoration: line-through;
  }
  .msg-label.status-changed {
    color: #92400e;
    background: #fffbeb;
  }
  .guard {
    color: #6366f1;
    font-style: italic;
    margin-right: 0.15rem;
  }
</style>
