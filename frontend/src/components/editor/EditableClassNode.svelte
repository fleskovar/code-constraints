<script lang="ts">
  import { Handle, Position, type NodeProps } from "@xyflow/svelte";
  import { diagramState } from "../../lib/state/diagram.svelte";
  import {
    defaultAttribute,
    defaultOperation,
    findClass,
    setAttributes,
    setOperations,
  } from "../../lib/state/editor.svelte";
  import type { ClassFlowNode } from "../diagram/types";

  let { data, id, selected }: NodeProps<ClassFlowNode> = $props();

  // Quick-add: append a default member directly on the canvas; double-click
  // the class afterwards to refine it in the modal.
  function quickAddAttribute(e: MouseEvent) {
    e.stopPropagation();
    const cls = findClass(data.qualifiedName);
    if (!cls) return;
    setAttributes(data.qualifiedName, [...cls.attributes, defaultAttribute()]);
  }
  function quickAddOperation(e: MouseEvent) {
    e.stopPropagation();
    const cls = findClass(data.qualifiedName);
    if (!cls) return;
    setOperations(data.qualifiedName, [...cls.operations, defaultOperation()]);
  }

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

  const isHighlighted = $derived(diagramState.selectedClassId === id);

  // Trigger custom DOM events so the canvas can open the right modal without
  // a tight coupling to the parent. The canvas listens for these via the
  // wrapping <div> in EditorCanvas.svelte.
  function emit(type: string, detail: unknown) {
    window.dispatchEvent(new CustomEvent(`editor:${type}`, { detail }));
  }
</script>

<div
  class="class-node status-{data.status} editable"
  class:selected
  class:highlighted={isHighlighted}
>
  <Handle type="target" position={Position.Top} />
  <header
    ondblclick={() =>
      emit("edit-class", { qualifiedName: data.qualifiedName })}
    role="button"
    tabindex="-1"
    title="Double-click to edit class"
  >
    {#if kindTag}<span class="kind-tag">{kindTag}</span>{/if}
    <span class="name">{data.name}</span>
    <button
      class="pencil"
      title="Edit class"
      onclick={(e) => {
        e.stopPropagation();
        emit("edit-class", { qualifiedName: data.qualifiedName });
      }}>✎</button
    >
  </header>
  <ul
    class="members attributes"
    ondblclick={() =>
      emit("edit-class", { qualifiedName: data.qualifiedName, section: "attributes" })}
  >
    {#each data.attributes as a, i (i + "|" + a.signature)}
      <li class="status-{a.status}">
        <span class="vis">{visSymbol[a.visibility] ?? "+"}</span>
        <span class="member-name" class:static={a.isStatic}>{a.name}</span>
        {#if a.type}<span class="type"> : {a.type}</span>{/if}
      </li>
    {/each}
    {#if data.attributes.length === 0}
      <li class="placeholder">— no attributes —</li>
    {/if}
    <li class="quick-add">
      <button title="Add attribute" onclick={quickAddAttribute}
        >+ attribute</button
      >
    </li>
  </ul>
  <ul
    class="members operations"
    ondblclick={() =>
      emit("edit-class", { qualifiedName: data.qualifiedName, section: "operations" })}
  >
    {#each data.operations as o, i (i + "|" + o.signature)}
      <li class="status-{o.status}">
        <span class="vis">{visSymbol[o.visibility] ?? "+"}</span>
        <span
          class="member-name"
          class:static={o.isStatic}
          class:abstract={o.isAbstract}>{o.name}</span
        ><span class="paren">(</span><span class="paren">)</span>{#if o.returnType}<span
            class="type"
          > : {o.returnType}</span
        >{/if}
      </li>
    {/each}
    {#if data.operations.length === 0}
      <li class="placeholder">— no operations —</li>
    {/if}
    <li class="quick-add">
      <button title="Add method" onclick={quickAddOperation}>+ method</button>
    </li>
  </ul>
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
    min-width: 200px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
    overflow: hidden;
  }
  .class-node.editable {
    border-style: dashed;
  }
  .class-node.highlighted {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.25);
  }
  .class-node.selected {
    border-color: #2563eb;
  }
  header {
    background: #f1f5f9;
    padding: 6px 10px;
    border-bottom: 1px solid #cbd5e1;
    text-align: center;
    position: relative;
    cursor: pointer;
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
  .pencil {
    position: absolute;
    top: 4px;
    right: 6px;
    background: transparent;
    border: none;
    color: #64748b;
    font-size: 0.85rem;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.1s;
  }
  .class-node:hover .pencil {
    opacity: 1;
  }
  .members {
    list-style: none;
    margin: 0;
    padding: 4px 8px;
    cursor: pointer;
  }
  .members + .members {
    border-top: 1px solid #e5e7eb;
  }
  .members li {
    line-height: 1.5;
    white-space: nowrap;
  }
  .placeholder {
    color: #cbd5e1;
    font-style: italic;
  }
  .quick-add {
    display: none;
  }
  .class-node:hover .quick-add {
    display: block;
  }
  .quick-add button {
    background: transparent;
    border: 1px dashed #cbd5e1;
    border-radius: 3px;
    color: #64748b;
    font-size: 10px;
    padding: 0 4px;
    cursor: pointer;
    line-height: 1.4;
  }
  .quick-add button:hover {
    background: #f1f5f9;
    color: #1a1a1a;
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
  .class-node.status-added header {
    background: #daf7dc;
  }
  .class-node.status-removed header {
    background: #fbd7d7;
  }
  .class-node.status-changed header {
    background: #fff6cc;
  }
</style>
