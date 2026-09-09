<script lang="ts">
  import {
    api,
    type ClassGraph,
    type ClassGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import { diagramState } from "../../lib/state/diagram.svelte";
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
</script>

<div class="panel">
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
</div>

<style>
  .panel {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--border);
    flex: 0 0 auto;
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
