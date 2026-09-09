<script lang="ts">
  import {
    api,
    type ActivityGraph,
    type ActivityGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import {
    diagramState,
    setSelected,
    setVisible,
    setVisibleSet,
    showAll as svcShowAll,
    hideAll as svcHideAll,
    isolate as svcIsolate,
    isVisible,
    requestRelayout,
  } from "../../lib/state/diagram.svelte";

  let { xmi, name }: { xmi: XmiInfo; name: string } = $props();

  let graph = $state<ActivityGraph | null>(null);
  let error = $state("");
  let query = $state("");
  let hops = $state(1);

  $effect(() => {
    const xmiId = xmi.id;
    const n = name;
    error = "";
    graph = null;
    api
      .activityGraph(xmiId, n)
      .then((g) => (graph = g))
      .catch((e: Error) => (error = e.message));
  });

  const filtered = $derived.by(() => {
    if (!graph) return [] as ActivityGraphNode[];
    const q = query.trim().toLowerCase();
    if (!q) return graph.nodes;
    return graph.nodes.filter(
      (n) =>
        (n.label ?? "").toLowerCase().includes(q) ||
        n.kind.toLowerCase().includes(q),
    );
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

  function isolateSelected() {
    if (!graph || !diagramState.selectedClassId) return;
    svcIsolate(diagramState.selectedClassId, hops, graph.edges);
  }

  function nodeLabel(n: ActivityGraphNode): string {
    if (n.label) return n.label;
    if (n.kind === "initial") return "● initial";
    if (n.kind === "final") return "● final";
    if (n.kind === "decision") return "◇ decision";
    if (n.kind === "merge") return "◇ merge";
    if (n.kind === "fork") return "▬ fork";
    if (n.kind === "join") return "▬ join";
    return "(unnamed)";
  }
</script>

<div class="panel">
  <div class="search">
    <input
      type="search"
      placeholder="Search nodes…"
      bind:value={query}
      autocomplete="off"
    />
    {#if graph}
      <span class="count">{filtered.length} / {graph.nodes.length}</span>
    {/if}
  </div>

  <div class="commands">
    <button onclick={svcShowAll}>Show all</button>
    <button onclick={svcHideAll}>Hide all</button>
    <button
      onclick={isolateSelected}
      disabled={!diagramState.selectedClassId}
      title="Limit to the selected node and its neighbours"
    >
      Isolate
    </button>
    <label class="hops" title="Edge-hops around the selected node">
      ±
      <input type="number" min="0" max="10" bind:value={hops} />
    </label>
    <button onclick={requestRelayout} title="Re-run auto-layout">Compact</button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if !graph}
    <p class="muted">Loading…</p>
  {:else}
    <ul class="node-list">
      {#each filtered as n (n.id)}
        <li>
          <label class="row checkbox">
            <input
              type="checkbox"
              checked={isVisible(n.id)}
              onchange={(e) =>
                toggleVisible(n.id, (e.currentTarget as HTMLInputElement).checked)}
            />
            <button
              type="button"
              class="row-button status-{n.status}"
              class:active={diagramState.selectedClassId === n.id}
              onclick={() => select(n.id)}
            >
              <span class="kind">{n.kind}</span>
              <span class="name">{nodeLabel(n)}</span>
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
    height: 100%;
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
  .commands {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--border);
    align-items: center;
  }
  .commands button {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.2rem 0.5rem;
    font-size: 0.75rem;
    cursor: pointer;
    color: var(--fg);
  }
  .commands button:hover:not(:disabled) {
    background: var(--hover);
  }
  .commands button:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .hops {
    display: inline-flex;
    align-items: center;
    gap: 0.15rem;
    font-size: 0.75rem;
    color: var(--muted);
  }
  .hops input {
    width: 2.5rem;
    padding: 0.15rem 0.3rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--fg);
    font-size: 0.75rem;
  }
  .node-list {
    list-style: none;
    margin: 0;
    padding: 0.25rem 0;
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
  .row-button {
    flex: 1;
    background: transparent;
    border: none;
    text-align: left;
    color: var(--fg);
    cursor: pointer;
    padding: 0.3rem;
    border-radius: 4px;
    display: flex;
    gap: 0.4rem;
    align-items: baseline;
  }
  .row-button:hover {
    background: var(--hover);
  }
  .row-button.active {
    background: var(--accent);
    color: white;
  }
  .row-button.status-added {
    border-left: 3px solid #16a34a;
  }
  .row-button.status-removed {
    border-left: 3px solid #dc2626;
    text-decoration: line-through;
  }
  .row-button.status-changed {
    border-left: 3px solid #ca8a04;
  }
  .kind {
    font-size: 0.65rem;
    text-transform: uppercase;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
    min-width: 4rem;
  }
  .row-button.active .kind {
    color: rgba(255, 255, 255, 0.85);
  }
  .name {
    font-size: 0.85rem;
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
