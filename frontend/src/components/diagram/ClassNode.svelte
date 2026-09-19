<script lang="ts">
  import { Handle, Position, type NodeProps } from "@xyflow/svelte";
  import { diagramState } from "../../lib/state/diagram.svelte";
  import { openLayers } from "../../lib/state/layers.svelte";
  import { openLayerClasses } from "../../lib/state/layerClasses.svelte";
  import {
    layerName,
    ruleBadgeLabel,
    rulePresentation,
    ruleTooltip,
  } from "../../lib/rules";
  import { kindPresentation } from "../../lib/kinds";
  import type { ClassFlowNode } from "./types";

  let { data, id, selected }: NodeProps<ClassFlowNode> = $props();

  const visSymbol: Record<string, string> = {
    public: "+",
    protected: "#",
    private: "-",
    package: "~",
  };

  const kindTag = $derived(
    data.kind === "interface"
      ? "«interface»"
      : data.kind === "enum"
        ? "«enumeration»"
        : data.kind === "abstract"
          ? "«abstract»"
          : data.kind === "struct"
            ? "«struct»"
            : data.kind === "record"
              ? "«record»"
              : data.kind === "static"
                ? "«static»"
                : "",
  );

  const isExternal = $derived(data.kind === "external");

  // Edge-focus popup: emphasise the rows that produce the focused edge so it's
  // easy to see where a reference comes from. Empty/false on the main canvas.
  const hlAttrs = $derived(new Set(data.highlightAttributes ?? []));
  const hlOps = $derived(new Set(data.highlightOperations ?? []));

  const isHighlighted = $derived(
    diagramState.selectedClassId === id ||
      diagramState.highlightedNodeIds.has(id),
  );

  // Kind colour-coding: a left stripe (always) + a light header tint (only when
  // the diff status is `unchanged`, so diff colours still win).
  const kp = $derived(kindPresentation(data.kind));
  const headerStyle = $derived(
    data.status === "unchanged" ? `background:${kp.tint}` : "",
  );

  // Level-of-detail: when zoomed out (and LOD on), render header only.
  const compact = $derived(
    diagramState.lodEnabled && diagramState.lodTier !== "full",
  );
</script>

<div
  class="class-node status-{data.status}"
  class:selected
  class:highlighted={isHighlighted}
  class:external={isExternal}
  class:compact
  class:edge-related-header={data.highlightHeader}
  style="border-left: 5px solid {kp.color}"
>
  <Handle type="target" position={Position.Top} />
  <header style={headerStyle}>
    {#if isExternal}<span class="kind-tag" style="color:{kp.color}">«external»</span
      >{:else if kindTag}<span class="kind-tag" style="color:{kp.color}">{kindTag}</span>{/if}
    <span class="name">{data.name}</span>
    {#if !compact && data.rules.length}
      <span class="rule-badges">
        {#each data.rules as r, i (i + "|" + r.name)}
          {#if r.name === "layer"}
            <button
              type="button"
              class="rule-badge layer-badge"
              style="background:{rulePresentation(r.name).color}"
              title={ruleTooltip(r) + " — click to view layer dependencies · right-click to list classes"}
              onpointerdown={(e) => e.stopPropagation()}
              onclick={(e) => {
                e.stopPropagation();
                openLayers(layerName(r));
              }}
              oncontextmenu={(e) => {
                e.preventDefault();
                e.stopPropagation();
                openLayerClasses(layerName(r));
              }}>{ruleBadgeLabel(r)}</button
            >
          {:else}
            <span
              class="rule-badge"
              style="background:{rulePresentation(r.name).color}"
              title={ruleTooltip(r)}>{ruleBadgeLabel(r)}</span
            >
          {/if}
        {/each}
      </span>
    {/if}
  </header>
  {#if !compact}
  {#if data.attributes.length && diagramState.showAttributes}
    <ul class="members attributes">
      {#each data.attributes as a, i (i + "|" + a.signature)}
        <li class="status-{a.status}" class:edge-related={hlAttrs.has(a.signature)}>
          <span class="vis">{visSymbol[a.visibility] ?? "+"}</span>
          <span class="member-name" class:static={a.isStatic}>{a.name}</span>
          {#if a.type}<span class="type"> : {a.type}</span>{/if}
        </li>
      {/each}
    </ul>
  {/if}
  {#if data.operations.length && diagramState.showOperations}
    <ul class="members operations">
      {#each data.operations as o, i (i + "|" + o.signature)}
        <li class="status-{o.status}" class:edge-related={hlOps.has(o.signature)}>
          <span class="vis">{visSymbol[o.visibility] ?? "+"}</span>
          <span
            class="member-name"
            class:static={o.isStatic}
            class:abstract={o.isAbstract}>{o.name}</span
          ><span class="paren">(</span><span class="paren">)</span>{#if o.returnType}<span
              class="type"
            > : {o.returnType}</span
          >{/if}{#each o.rules as r, ri (ri + "|" + r.name)}<span
              class="rule-badge inline"
              style="background:{rulePresentation(r.name).color}"
              title={ruleTooltip(r)}>{rulePresentation(r.name).label}</span
            >{/each}
        </li>
      {/each}
    </ul>
  {/if}
  {/if}
  <Handle type="source" position={Position.Bottom} />
</div>

<style>
  .class-node {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      "Helvetica Neue", sans-serif;
    font-size: 11px;
    background: #fff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    min-width: 180px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
    overflow: hidden;
  }
  .class-node.compact header {
    border-bottom: none;
  }
  .class-node.highlighted {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.25);
  }
  .class-node.selected {
    border-color: #2563eb;
  }
  .class-node.external {
    border-style: dashed;
    border-color: #94a3b8;
    background: #f8fafc;
    opacity: 0.9;
    min-width: 120px;
  }
  .class-node.external .name {
    color: #475569;
    font-weight: 500;
  }
  header {
    background: #f1f5f9;
    padding: 6px 10px;
    border-bottom: 1px solid #cbd5e1;
    text-align: center;
  }
  .kind-tag {
    display: block;
    color: #64748b;
    font-size: 10px;
    margin-bottom: 1px;
  }
  .name {
    font-weight: 600;
  }
  .rule-badges {
    display: block;
    margin-top: 3px;
  }
  .rule-badge {
    display: inline-block;
    color: #fff;
    font-size: 9px;
    line-height: 1.2;
    padding: 0 4px;
    border-radius: 3px;
    margin: 1px 2px 0 0;
    vertical-align: middle;
    cursor: help;
  }
  .layer-badge {
    border: none;
    font-family: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  .layer-badge:hover {
    filter: brightness(1.12);
    text-decoration: underline;
  }
  .rule-badge.inline {
    margin-left: 4px;
  }
  .members {
    list-style: none;
    margin: 0;
    padding: 4px 8px;
  }
  .members + .members {
    border-top: 1px solid #e5e7eb;
  }
  .members li {
    line-height: 1.5;
    white-space: nowrap;
  }
  .vis {
    display: inline-block;
    width: 0.9em;
    color: #64748b;
  }
  .member-name.static {
    font-style: italic;
  }
  .member-name.abstract {
    font-style: italic;
  }
  .type {
    color: #475569;
  }
  .paren {
    color: #64748b;
  }
  /* diff statuses */
  .class-node.status-added header {
    background: #daf7dc;
  }
  .class-node.status-removed header {
    background: #fbd7d7;
  }
  .class-node.status-changed header {
    background: #fff6cc;
  }
  li.status-added {
    background: #daf7dc;
    color: #166534;
  }
  li.status-removed {
    background: #fbd7d7;
    color: #b91c1c;
    text-decoration: line-through;
  }
  /* edge-focus highlight: the member(s) producing the focused edge. Placed last
     so it wins over the unchanged-row default; diff backgrounds still show via
     the left accent bar. */
  .members li.edge-related {
    font-weight: 700;
    background: #fde68a;
    box-shadow: inset 3px 0 0 #f59e0b;
    border-radius: 2px;
  }
  .class-node.edge-related-header header {
    box-shadow: inset 0 0 0 2px #f59e0b;
  }
  .class-node.edge-related-header header .name {
    font-weight: 800;
  }
</style>
