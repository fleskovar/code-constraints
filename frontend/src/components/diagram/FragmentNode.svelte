<script lang="ts">
  import { type NodeProps, type Node } from "@xyflow/svelte";
  import type { FragmentNodeData } from "./sequenceTypes";

  let { data }: NodeProps<Node<FragmentNodeData, "fragment">> = $props();
</script>

<div
  class="frag status-{data.status} kind-{data.kind}"
  style:width="{data.width}px"
  style:height="{data.height}px"
>
  <div class="header">
    <span class="kind">{data.kind}</span>
    {#if data.label}<span class="label">[{data.label}]</span>{/if}
  </div>
</div>

<style>
  .frag {
    box-sizing: border-box;
    border: 1.5px solid #94a3b8;
    border-radius: 6px;
    background: rgba(148, 163, 184, 0.08);
    pointer-events: none; /* let clicks reach lifelines / messages behind */
    position: relative;
  }
  .frag.kind-alt {
    border-color: #6366f1;
    background: rgba(99, 102, 241, 0.07);
  }
  .frag.kind-opt {
    border-color: #0ea5e9;
    background: rgba(14, 165, 233, 0.07);
  }
  .frag.kind-loop {
    border-color: #10b981;
    background: rgba(16, 185, 129, 0.07);
  }
  .frag.status-added {
    border-color: #16a34a;
    background: rgba(22, 163, 74, 0.1);
  }
  .frag.status-removed {
    border-color: #dc2626;
    background: rgba(220, 38, 38, 0.08);
    border-style: dashed;
  }
  .header {
    position: absolute;
    top: -1px;
    left: -1px;
    padding: 1px 8px 2px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    font-size: 11px;
    background: inherit;
    border-bottom-right-radius: 6px;
    border-right: 1.5px solid currentColor;
    border-bottom: 1.5px solid currentColor;
    color: #475569;
  }
  .kind {
    font-weight: 700;
    text-transform: uppercase;
    font-size: 10px;
    margin-right: 4px;
  }
  .frag.kind-alt .header { color: #4338ca; }
  .frag.kind-opt .header { color: #0369a1; }
  .frag.kind-loop .header { color: #047857; }
  .label {
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-style: italic;
  }
</style>
