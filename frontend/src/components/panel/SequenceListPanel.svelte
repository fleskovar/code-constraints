<script lang="ts">
  import {
    api,
    type SequenceGraph,
    type XmiInfo,
  } from "../../lib/api";
  import {
    diagramState,
    setSelected,
    setVisible,
    setVisibleSet,
    showAll as svcShowAll,
    hideAll as svcHideAll,
    isVisible,
  } from "../../lib/state/diagram.svelte";

  let { xmi, name }: { xmi: XmiInfo; name: string } = $props();

  let graph = $state<SequenceGraph | null>(null);
  let error = $state("");
  let query = $state("");

  $effect(() => {
    const xmiId = xmi.id;
    const n = name;
    error = "";
    graph = null;
    api
      .sequenceGraph(xmiId, n)
      .then((g) => (graph = g))
      .catch((e: Error) => (error = e.message));
  });

  const filteredLifelines = $derived.by(() => {
    if (!graph) return [];
    const q = query.trim().toLowerCase();
    if (!q) return graph.lifelines;
    return graph.lifelines.filter(
      (l) =>
        l.name.toLowerCase().includes(q) ||
        l.represents.toLowerCase().includes(q),
    );
  });

  const filteredMessages = $derived.by(() => {
    if (!graph) return [];
    const q = query.trim().toLowerCase();
    if (!q) return graph.messages;
    return graph.messages.filter((m) => m.label.toLowerCase().includes(q));
  });

  function toggleVisible(id: string, on: boolean) {
    if (!graph) return;
    if (diagramState.visibleClassIds === null) {
      const all = new Set(graph.lifelines.map((n) => n.id));
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
      placeholder="Search lifelines / messages…"
      bind:value={query}
      autocomplete="off"
    />
  </div>

  <div class="commands">
    <button onclick={svcShowAll}>Show all</button>
    <button onclick={svcHideAll}>Hide all</button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if !graph}
    <p class="muted">Loading…</p>
  {:else}
    <div class="section-label">
      Lifelines ({filteredLifelines.length} / {graph.lifelines.length})
    </div>
    <ul class="lifeline-list">
      {#each filteredLifelines as l (l.id)}
        <li>
          <label class="row checkbox">
            <input
              type="checkbox"
              checked={isVisible(l.id)}
              onchange={(e) =>
                toggleVisible(l.id, (e.currentTarget as HTMLInputElement).checked)}
            />
            <button
              class="row-button status-{l.status}"
              class:active={diagramState.selectedClassId === l.id}
              onclick={() => setSelected(l.id)}
            >
              <span class="name">{l.name}</span>
              {#if l.represents}
                <span class="represents">{l.represents}</span>
              {/if}
            </button>
          </label>
        </li>
      {/each}
    </ul>

    <div class="section-label">
      Messages ({filteredMessages.length} / {graph.messages.length})
    </div>
    <ul class="msg-list">
      {#each filteredMessages as m (m.id)}
        <li class="msg status-{m.status}" title={m.guard ? `guard: ${m.guard}` : undefined}>
          <span class="row-no">#{m.row + 1}</span>
          <span class="label">
            {#if m.guard}<span class="guard">[{m.guard}]</span> {/if}{m.label}
          </span>
          {#if m.isReturn}<span class="ret">return</span>{/if}
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
  }
  .search input {
    width: 100%;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.85rem;
    background: var(--bg);
    color: var(--fg);
  }
  .commands {
    display: flex;
    gap: 0.25rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid var(--border);
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
  .section-label {
    padding: 0.4rem 0.75rem 0.2rem;
    font-size: 0.65rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .lifeline-list,
  .msg-list {
    list-style: none;
    margin: 0;
    padding: 0 0 0.25rem;
    overflow-y: auto;
  }
  .lifeline-list {
    flex: 0 0 auto;
    max-height: 40%;
  }
  .msg-list {
    flex: 1 1 auto;
    min-height: 0;
  }
  .row.checkbox {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0 0.75rem;
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
    flex-direction: column;
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
  .name {
    font-size: 0.85rem;
    font-weight: 500;
  }
  .represents {
    font-size: 0.7rem;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
  }
  .msg {
    display: flex;
    gap: 0.5rem;
    align-items: baseline;
    padding: 0.25rem 0.75rem;
    font-size: 0.8rem;
    line-height: 1.3;
  }
  .msg .row-no {
    color: var(--muted);
    font-size: 0.7rem;
    font-family: ui-monospace, SFMono-Regular, monospace;
    min-width: 1.6rem;
  }
  .msg .ret {
    color: var(--muted);
    font-size: 0.65rem;
    text-transform: uppercase;
  }
  .msg.status-added .label {
    color: #166534;
  }
  .msg.status-removed .label {
    color: #991b1b;
    text-decoration: line-through;
  }
  .guard {
    color: #6366f1;
    font-style: italic;
    font-size: 0.75rem;
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
