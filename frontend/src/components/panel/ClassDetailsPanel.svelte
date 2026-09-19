<script lang="ts">
  import {
    api,
    type ClassGraph,
    type ClassGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import {
    diagramState,
    relatedClasses,
    setSelected,
  } from "../../lib/state/diagram.svelte";
  import CollapsibleSection from "./CollapsibleSection.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  let graph = $state<ClassGraph | null>(null);

  $effect(() => {
    const xmiId = xmi.id;
    graph = null;
    api
      .classGraph(xmiId)
      .then((g) => (graph = g))
      .catch(() => (graph = null));
  });

  const byId = $derived(
    graph ? new Map(graph.nodes.map((n) => [n.id, n])) : new Map<string, ClassGraphNode>(),
  );

  const selected = $derived(
    diagramState.selectedClassId ? byId.get(diagramState.selectedClassId) ?? null : null,
  );

  const related = $derived.by(() => {
    if (!graph || !selected) return [];
    return relatedClasses(selected.id, graph.edges)
      .map((r) => ({ ...r, node: byId.get(r.id) }))
      .filter((r) => r.node);
  });

  // Collapsed to its title bar so it never has to cover the canvas.
  let open = $state(true);
</script>

<div class="inspector" class:open>
  <button
    type="button"
    class="head"
    aria-expanded={open}
    title={open ? "Collapse the inspector" : "Expand the inspector"}
    onclick={() => (open = !open)}
  >
    <span>{selected ? selected.name : "Inspector"}</span>
    <span class="caret">{open ? "▾" : "▸"}</span>
  </button>
  {#if open}
  <div class="body">
  <CollapsibleSection title="Details">
  {#if !selected}
    <p class="placeholder">Select a class to see details.</p>
  {:else}
    <div class="class-header">
      <span class="class-name">{selected.name}</span>
      <span class="kind">{selected.kind}</span>
    </div>
    {#if selected.package}
      <div class="pkg">{selected.package}</div>
    {/if}

    {#if selected.description}
      <p class="description">{selected.description}</p>
    {:else}
      <p class="description muted">No description.</p>
    {/if}

    {#if selected.attributes.length}
      <h5>Attributes</h5>
      <ul class="members">
        {#each selected.attributes as a, i (i + "|" + a.signature)}
          <li>
            <code class="sig">{a.signature}</code>
            {#if a.description}
              <p class="member-desc">{a.description}</p>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    {#if selected.operations.length}
      <h5>Operations</h5>
      <ul class="members">
        {#each selected.operations as o, i (i + "|" + o.signature)}
          <li>
            <code class="sig">{o.signature}</code>
            {#if o.description}
              <p class="member-desc">{o.description}</p>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    {#if selected.location}
      <p class="location" title={selected.location.file}>
        {selected.location.file}:{selected.location.startLine}
      </p>
    {/if}
  {/if}
  </CollapsibleSection>

  {#if related.length}
    <div class="related">
      <CollapsibleSection title="Related to {selected?.name}">
        <ul>
          {#each related as r (r.id)}
            <li>
              <button class="row" onclick={() => setSelected(r.id)} title={r.node!.qualifiedName}>
                <span class="badge {r.kind} {r.direction}">
                  {r.kind === "inheritance" ? "⇧" : "→"}
                </span>
                <span class="name">{r.node!.name}</span>
                <span class="rel-pkg">{r.node!.package}</span>
              </button>
            </li>
          {/each}
        </ul>
      </CollapsibleSection>
    </div>
  {/if}
  </div>
  {/if}
</div>

<style>
  .inspector {
    position: absolute;
    top: 12px;
    right: 12px;
    z-index: 5;
    width: 300px;
    max-height: calc(100% - 24px);
    display: flex;
    flex-direction: column;
    background: rgba(255, 255, 255, 0.97);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 6px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  }
  .inspector:not(.open) {
    width: auto;
    max-width: 300px;
  }
  .head {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.35rem 0.6rem;
    background: transparent;
    border: none;
    cursor: pointer;
    font: inherit;
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--fg);
    text-align: left;
  }
  .head span:first-child {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .open .head {
    border-bottom: 1px solid var(--border, #e5e7eb);
  }
  .caret {
    color: var(--muted);
    font-size: 0.7rem;
  }
  .body {
    min-height: 0;
    overflow-y: auto;
    padding: 0.6rem 0.75rem;
  }
  .related {
    margin-top: 0.6rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--border, #e5e7eb);
  }
  .related ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.25rem 0.3rem;
    background: transparent;
    border: none;
    border-radius: 4px;
    text-align: left;
    color: var(--fg);
    cursor: pointer;
  }
  .row:hover {
    background: var(--hover);
  }
  .name {
    font-size: 0.85rem;
    font-weight: 500;
  }
  .rel-pkg {
    font-size: 0.7rem;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .badge {
    flex-shrink: 0;
    display: inline-block;
    width: 1.2em;
    height: 1.2em;
    line-height: 1.2em;
    text-align: center;
    border-radius: 3px;
    background: #e2e8f0;
    color: #475569;
    font-size: 0.7rem;
  }
  .badge.inheritance {
    background: #dbeafe;
    color: #1d4ed8;
  }
  .badge.association {
    background: #fef3c7;
    color: #b45309;
  }
  .badge.in {
    transform: rotate(180deg);
  }
  .placeholder {
    margin: 0;
    color: var(--muted);
    font-size: 0.8rem;
    font-style: italic;
  }
  .class-header {
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }
  .class-name {
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--fg);
  }
  .kind {
    font-size: 0.7rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .pkg {
    font-size: 0.7rem;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
    margin-bottom: 0.4rem;
  }
  .description {
    margin: 0.3rem 0 0.6rem;
    font-size: 0.85rem;
    line-height: 1.4;
    color: var(--fg);
    white-space: pre-wrap;
  }
  .description.muted {
    color: var(--muted);
    font-style: italic;
  }
  h5 {
    margin: 0.5rem 0 0.25rem;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .members {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .members li {
    margin-bottom: 0.4rem;
  }
  .sig {
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 0.78rem;
    color: var(--fg);
  }
  .member-desc {
    margin: 0.15rem 0 0;
    font-size: 0.78rem;
    color: var(--muted);
    line-height: 1.35;
    white-space: pre-wrap;
  }
  .location {
    margin: 0.5rem 0 0;
    font-size: 0.7rem;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
