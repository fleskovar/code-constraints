<script lang="ts">
  import { Handle, Position, type NodeProps, type Node } from "@xyflow/svelte";
  import type { ActivityGraphNode } from "../../lib/api";

  type Data = ActivityGraphNode & Record<string, unknown>;
  let { data }: NodeProps<Node<Data, "activity">> = $props();
</script>

<div class="activity-node kind-{data.kind} status-{data.status}">
  <Handle type="target" position={Position.Top} />
  {#if data.kind === "initial" || data.kind === "final"}
    <span class="dot" aria-label={data.kind}></span>
  {:else if data.kind === "decision" || data.kind === "merge"}
    <span class="diamond"><span class="diamond-label">{data.label}</span></span>
  {:else if data.kind === "fork" || data.kind === "join"}
    <span class="bar" aria-label={data.kind}></span>
  {:else}
    <span class="action">{data.label || "(unnamed)"}</span>
  {/if}
  <Handle type="source" position={Position.Bottom} />
</div>

<style>
  .activity-node {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 11px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .dot {
    display: inline-block;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #1f2937;
  }
  .kind-final .dot {
    border: 3px solid #fff;
    box-shadow: 0 0 0 2px #1f2937;
    background: #1f2937;
  }
  .action {
    background: #fff;
    border: 1px solid #cbd5e1;
    border-radius: 14px;
    padding: 6px 14px;
    min-width: 110px;
    text-align: center;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  }
  .diamond {
    width: 110px;
    height: 60px;
    background: #fff;
    border: 1px solid #cbd5e1;
    transform: rotate(45deg);
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .diamond-label {
    transform: rotate(-45deg);
    text-align: center;
    max-width: 70px;
  }
  .bar {
    display: inline-block;
    width: 80px;
    height: 6px;
    background: #1f2937;
    border-radius: 2px;
  }
  /* diff statuses */
  .status-added .action,
  .status-added .diamond {
    background: #daf7dc;
  }
  .status-removed .action,
  .status-removed .diamond {
    background: #fbd7d7;
    text-decoration: line-through;
  }
  .status-changed .action,
  .status-changed .diamond {
    background: #fff6cc;
  }
</style>
