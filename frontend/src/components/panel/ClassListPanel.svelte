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
    setVisible,
    setVisibleSet,
    isVisible,
  } from "../../lib/state/diagram.svelte";
  import { layerName, rulePresentation } from "../../lib/rules";
  import { openLayers } from "../../lib/state/layers.svelte";
  import SavedViewsPanel from "./SavedViewsPanel.svelte";
  import CollapsibleSection from "./CollapsibleSection.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  let graph = $state<ClassGraph | null>(null);
  let error = $state("");
  let query = $state("");

  $effect(() => {
    const xmiId = xmi.id;
    error = "";
    graph = null;
    api
      .classGraph(xmiId)
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
    graph ? new Map(graph.nodes.map((n) => [n.id, n])) : new Map<string, ClassGraphNode>(),
  );

  const related = $derived.by(() => {
    if (!graph || !diagramState.selectedClassId) return [];
    return relatedClasses(diagramState.selectedClassId, graph.edges)
      .map((r) => ({ ...r, node: byId.get(r.id) }))
      .filter((r) => r.node);
  });

  // Group node ids by architectural layer (from `@layer("name")` tags). Nodes
  // with no layer tag fall into a synthetic "(no layer)" bucket so they can be
  // toggled too. The whole section hides when no class carries a layer.
  const LAYER_OF = (n: ClassGraphNode): string | null => {
    const r = n.rules.find((x) => x.name === "layer");
    return r ? layerName(r) || "(unnamed)" : null;
  };
  const NO_LAYER = "(no layer)";
  const layers = $derived.by(() => {
    if (!graph)
      return [] as { name: string; ids: string[]; nodes: ClassGraphNode[] }[];
    const buckets = new Map<string, ClassGraphNode[]>();
    let anyLayered = false;
    for (const n of graph.nodes) {
      const l = LAYER_OF(n);
      if (l) anyLayered = true;
      const key = l ?? NO_LAYER;
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key)!.push(n);
    }
    if (!anyLayered) return [];
    return [...buckets.entries()]
      .map(([name, nodes]) => ({
        name,
        nodes: [...nodes].sort((a, b) => a.name.localeCompare(b.name)),
        ids: nodes.map((n) => n.id),
      }))
      .sort((a, b) =>
        a.name === NO_LAYER ? 1 : b.name === NO_LAYER ? -1 : a.name.localeCompare(b.name),
      );
  });

  const layerColor = rulePresentation("layer").color;

  // Which layers are expanded in the tree. Keyed by layer name.
  let expanded = $state<Record<string, boolean>>({});

  function toggleExpand(name: string) {
    expanded[name] = !expanded[name];
  }

  function layerAllVisible(ids: string[]): boolean {
    return ids.every((id) => isVisible(id));
  }

  function layerSomeVisible(ids: string[]): boolean {
    return ids.some((id) => isVisible(id));
  }

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

  function toggleLayer(ids: string[], on: boolean) {
    if (!graph) return;
    const cur =
      diagramState.visibleClassIds === null
        ? new Set(graph.nodes.map((n) => n.id))
        : new Set(diagramState.visibleClassIds);
    for (const id of ids) {
      if (on) cur.add(id);
      else cur.delete(id);
    }
    setVisibleSet(cur);
  }

  function onlyLayer(ids: string[]) {
    setVisibleSet(ids);
  }
</script>

<div class="panel">
  {#if error}
    <p class="error">{error}</p>
  {:else if !graph}
    <p class="muted">Loading…</p>
  {:else}
    {#if layers.length}
      <div class="layers">
        <CollapsibleSection title="Layers" indent>
          {#snippet action()}
            <button
              type="button"
              class="deps-link"
              title="Show the allowed dependencies between layers (rules.yaml)"
              onclick={() => openLayers(null)}>rules ↗</button
            >
          {/snippet}
        <ul class="layer-tree">
          {#each layers as l (l.name)}
            {@const allVis = layerAllVisible(l.ids)}
            {@const someVis = layerSomeVisible(l.ids)}
            <li>
              <div class="layer-row">
                <button
                  type="button"
                  class="caret"
                  aria-expanded={!!expanded[l.name]}
                  title={expanded[l.name] ? "Collapse" : "Expand"}
                  onclick={() => toggleExpand(l.name)}>{expanded[l.name] ? "▾" : "▸"}</button
                >
                <input
                  type="checkbox"
                  checked={allVis}
                  indeterminate={someVis && !allVis}
                  title="Show / hide all classes in {l.name}"
                  onchange={(e) =>
                    toggleLayer(l.ids, (e.currentTarget as HTMLInputElement).checked)}
                />
                <span
                  class="swatch"
                  style="background:{l.name === NO_LAYER ? '#cbd5e1' : layerColor}"
                ></span>
                <button
                  type="button"
                  class="layer-name-btn"
                  title="Expand / collapse {l.name}"
                  onclick={() => toggleExpand(l.name)}
                >
                  <span class="layer-name">{l.name}</span>
                </button>
                <span class="layer-count">{l.ids.length}</span>
                <button
                  type="button"
                  class="only"
                  title="Show only this layer"
                  onclick={() => onlyLayer(l.ids)}>only</button
                >
              </div>
              {#if expanded[l.name]}
                <ul class="layer-children">
                  {#each l.nodes as node (node.id)}
                    <li>
                      <label class="class-row" title={node.qualifiedName}>
                        <input
                          type="checkbox"
                          checked={isVisible(node.id)}
                          onchange={(e) =>
                            toggleVisible(
                              node.id,
                              (e.currentTarget as HTMLInputElement).checked,
                            )}
                        />
                        <button
                          type="button"
                          class="class-name-btn"
                          class:active={diagramState.selectedClassId === node.id}
                          onclick={() => select(node.id)}>{node.name}</button
                        >
                      </label>
                    </li>
                  {/each}
                </ul>
              {/if}
            </li>
          {/each}
        </ul>
        </CollapsibleSection>
      </div>
    {/if}

    {#if related.length}
      <div class="related">
        <CollapsibleSection
          title="Related to {byId.get(diagramState.selectedClassId!)?.name}"
          indent
        >
          <ul>
            {#each related as r (r.id)}
              <li>
                <button class="row" onclick={() => select(r.id)} title={r.node!.qualifiedName}>
                  <span class="badge {r.kind} {r.direction}">
                    {r.kind === "inheritance" ? "⇧" : "→"}
                  </span>
                  <span class="name">{r.node!.name}</span>
                  <span class="pkg">{r.node!.package}</span>
                </button>
              </li>
            {/each}
          </ul>
        </CollapsibleSection>
      </div>
    {/if}

    <SavedViewsPanel {graph} {xmi} />
    <div class="classes">
      <CollapsibleSection title="Classes" indent>
        <div class="search">
          <input
            type="search"
            placeholder="Search classes…"
            bind:value={query}
            autocomplete="off"
          />
          {#if graph}
            <span class="count">{filtered.length} / {graph.nodes.length}</span>
          {/if}
        </div>
        <ul class="class-list">
          {#each filtered as cls (cls.id)}
        <li>
          <label class="row checkbox" title={cls.qualifiedName}>
            <input
              type="checkbox"
              checked={isVisible(cls.id)}
              onchange={(e) =>
                toggleVisible(cls.id, (e.currentTarget as HTMLInputElement).checked)}
            />
            <button
              type="button"
              class="row-button"
              class:active={diagramState.selectedClassId === cls.id}
              onclick={() => select(cls.id)}
            >
              <span class="name">{cls.name}</span>
              {#if cls.package}
                <span class="pkg">{cls.package}</span>
              {/if}
            </button>
          </label>
        </li>
      {/each}
        </ul>
      </CollapsibleSection>
    </div>
  {/if}
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    flex: 0 0 auto;
  }
  .search {
    padding: 0 0.75rem 0.4rem;
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
  .layers {
    border-bottom: 1px solid var(--border);
    padding: 0.4rem 0;
    flex: 0 0 auto;
  }
  .classes {
    flex: 0 0 auto;
    padding-top: 0.4rem;
  }
  .deps-link {
    background: transparent;
    border: none;
    color: var(--accent);
    cursor: pointer;
    font-size: 0.7rem;
    letter-spacing: 0;
    text-transform: none;
    padding: 0;
  }
  .deps-link:hover {
    text-decoration: underline;
  }
  .layers ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .layer-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.2rem 0.75rem;
    font-size: 0.85rem;
  }
  .layer-row:hover {
    background: var(--hover);
  }
  .layer-row input[type="checkbox"] {
    flex-shrink: 0;
  }
  .caret {
    flex-shrink: 0;
    width: 1rem;
    background: transparent;
    border: none;
    cursor: pointer;
    color: var(--muted);
    font-size: 0.7rem;
    padding: 0;
    line-height: 1;
  }
  .caret:hover {
    color: var(--fg);
  }
  .layer-name-btn {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: none;
    text-align: left;
    cursor: pointer;
    color: var(--fg);
    font: inherit;
    padding: 0;
  }
  .layer-children {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .class-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    /* indent under the caret + checkbox of the layer row */
    padding: 0.12rem 0.75rem 0.12rem 2.1rem;
    cursor: pointer;
    font-size: 0.82rem;
  }
  .class-row:hover {
    background: var(--hover);
  }
  .class-row input[type="checkbox"] {
    flex-shrink: 0;
  }
  .class-name-btn {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: none;
    text-align: left;
    cursor: pointer;
    color: var(--fg);
    font: inherit;
    padding: 0.1rem 0.2rem;
    border-radius: 4px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .class-name-btn:hover {
    background: var(--surface);
  }
  .class-name-btn.active {
    background: var(--accent);
    color: white;
  }
  .swatch {
    width: 0.7rem;
    height: 0.7rem;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .layer-name {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .layer-count {
    font-size: 0.7rem;
    color: var(--muted);
    background: var(--hover);
    border-radius: 8px;
    padding: 0 0.4rem;
  }
  .only {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0 0.35rem;
    font-size: 0.7rem;
    cursor: pointer;
    color: var(--muted);
  }
  .only:hover {
    background: var(--surface);
    color: var(--fg);
  }
  .related {
    border-bottom: 1px solid var(--border);
    padding: 0.4rem 0;
    background: #fbfbfb;
    flex: 0 0 auto;
  }
  .related ul,
  .class-list {
    list-style: none;
    margin: 0;
    padding: 0.25rem 0;
  }
  .class-list {
    flex: 0 0 auto;
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
  }
  .row-button:hover {
    background: var(--hover);
  }
  .row-button.active {
    background: var(--accent);
    color: white;
  }
  .row-button.active .pkg {
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
    display: block;
  }
  .pkg {
    font-size: 0.7rem;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, monospace;
    margin-left: 0.4rem;
  }
  .badge {
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
  .error {
    color: #c63a3a;
    padding: 0.75rem;
  }
  .muted {
    color: var(--muted);
    padding: 0.75rem;
  }
</style>
