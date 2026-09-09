<script lang="ts">
  import {
    api,
    type PackageGraph,
    type PackageGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import {
    diagramState,
    setSelected,
    setVisible,
    setVisibleSet,
    isVisible,
  } from "../../lib/state/diagram.svelte";
  import SavedViewsPanel from "./SavedViewsPanel.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  let graph = $state<PackageGraph | null>(null);
  let error = $state("");
  let query = $state("");

  $effect(() => {
    const xmiId = xmi.id;
    error = "";
    graph = null;
    api
      .packageGraph(xmiId)
      .then((g) => (graph = g))
      .catch((e: Error) => (error = e.message));
  });

  const filtered = $derived.by(() => {
    if (!graph) return [];
    const q = query.trim().toLowerCase();
    if (!q) return graph.nodes;
    return graph.nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        n.qualifiedName.toLowerCase().includes(q),
    );
  });

  const byId = $derived(
    graph ? new Map(graph.nodes.map((n) => [n.id, n])) : new Map<string, PackageGraphNode>(),
  );

  const related = $derived.by(() => {
    if (!graph || !diagramState.selectedClassId) return [];
    const id = diagramState.selectedClassId;
    const out: { id: string; direction: "out" | "in"; node: PackageGraphNode }[] = [];
    for (const e of graph.edges) {
      let neighbour: string | null = null;
      let direction: "out" | "in" = "out";
      if (e.source === id) {
        neighbour = e.target;
        direction = "out";
      } else if (e.target === id) {
        neighbour = e.source;
        direction = "in";
      }
      if (!neighbour) continue;
      const node = byId.get(neighbour);
      if (node) out.push({ id: neighbour, direction, node });
    }
    const seen = new Set<string>();
    return out.filter((r) => (seen.has(r.id) ? false : (seen.add(r.id), true)));
  });

  function select(id: string) {
    setSelected(id);
  }

  function toggleVisible(id: string, on: boolean) {
    if (!graph) return;
    if (diagramState.visibleClassIds === null) {
      const all = new Set(graph.nodes.map((n) => n.id));
      if (!on) all.delete(id);
      setVisibleSet(all);
    } else {
      setVisible(id, on);
    }
  }

</script>

<div class="panel">
  <div class="search">
    <input
      type="search"
      placeholder="Search packages…"
      bind:value={query}
      autocomplete="off"
    />
    {#if graph}
      <span class="count">{filtered.length} / {graph.nodes.length}</span>
    {/if}
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if !graph}
    <p class="muted">Loading…</p>
  {:else}
    {#if related.length}
      <div class="related">
        <h4>
          Depends to/from {byId.get(diagramState.selectedClassId!)?.name}
        </h4>
        <ul>
          {#each related as r (r.id)}
            <li>
              <button class="row" onclick={() => select(r.id)} title={r.node.qualifiedName}>
                <span class="badge {r.direction}">{r.direction === "out" ? "→" : "←"}</span>
                <span class="name">{r.node.name}</span>
                {#if r.node.parentQname}
                  <span class="pkg">{r.node.parentQname}</span>
                {/if}
              </button>
            </li>
          {/each}
        </ul>
      </div>
    {/if}

    <SavedViewsPanel graph={null} {xmi} />

    <ul class="class-list">
      {#each filtered as pkg (pkg.id)}
        <li>
          <label class="row checkbox" title={pkg.qualifiedName}>
            <input
              type="checkbox"
              checked={isVisible(pkg.id)}
              onchange={(e) =>
                toggleVisible(pkg.id, (e.currentTarget as HTMLInputElement).checked)}
            />
            <button
              type="button"
              class="row-button"
              class:active={diagramState.selectedClassId === pkg.id}
              onclick={() => select(pkg.id)}
            >
              <span class="name">{pkg.name}</span>
              {#if pkg.parentQname}
                <span class="pkg">{pkg.parentQname}</span>
              {/if}
              <span class="cls-count">{pkg.classCount}</span>
            </button>
          </label>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  .search {
    padding: 0.6rem 0.75rem 0.4rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .search input {
    flex: 1;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.85rem;
    background: var(--bg);
    color: var(--fg);
  }
  .count {
    font-size: 0.7rem;
    color: var(--muted);
  }
  .related {
    border-bottom: 1px solid var(--border);
    padding: 0.4rem 0;
    background: #fbfbfb;
    max-height: 30%;
    overflow-y: auto;
    flex: 0 0 auto;
  }
  .related h4 {
    margin: 0 0.75rem 0.25rem;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .related ul,
  .class-list {
    list-style: none;
    margin: 0;
    padding: 0.25rem 0;
  }
  .class-list {
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }
  .row.checkbox {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0 0.75rem;
    cursor: pointer;
  }
  .row.checkbox input[type="checkbox"] {
    flex-shrink: 0;
  }
  .row-button,
  .row {
    background: transparent;
    border: none;
    text-align: left;
    color: var(--fg);
    cursor: pointer;
  }
  .row-button {
    flex: 1;
    padding: 0.3rem 0.3rem;
    border-radius: 4px;
    display: flex;
    align-items: baseline;
    gap: 0.4rem;
  }
  .row-button:hover {
    background: var(--hover);
  }
  .row-button.active {
    background: var(--accent);
    color: white;
  }
  .row-button.active .pkg,
  .row-button.active .cls-count {
    color: rgba(255, 255, 255, 0.8);
  }
  .related .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.3rem 0.75rem;
  }
  .related .row:hover {
    background: var(--hover);
  }
  .name {
    font-size: 0.9rem;
    font-weight: 500;
  }
  .pkg {
    font-size: 0.7rem;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
  }
  .cls-count {
    margin-left: auto;
    background: var(--hover);
    border-radius: 8px;
    padding: 0 0.4rem;
    font-size: 0.7rem;
    color: var(--muted);
  }
  .badge {
    display: inline-block;
    width: 1.2em;
    text-align: center;
    color: #475569;
  }
  .error {
    color: #c63a3a;
    padding: 0.75rem;
  }
  .muted {
    color: var(--muted);
    padding: 0.75rem;
  }
</style>
