<script lang="ts">
  import {
    api,
    type ClassGraph,
    type ClassGraphNode,
    type XmiInfo,
  } from "../../lib/api";
  import {
    diagramState,
    setSelected,
    setVisible,
    setVisibleSet,
    isVisible,
  } from "../../lib/state/diagram.svelte";
  import { layerName, rulePresentation } from "../../lib/rules";
  import { KIND_ORDER, KIND_PRESENTATION, kindPresentation } from "../../lib/kinds";
  import { buildClassTree, type PkgNode } from "../../lib/classTree";
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

  const byName = (a: ClassGraphNode, b: ClassGraphNode) =>
    a.name.localeCompare(b.name);

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
        nodes: [...nodes].sort(byName),
        ids: nodes.map((n) => n.id),
      }))
      .sort((a, b) =>
        a.name === NO_LAYER ? 1 : b.name === NO_LAYER ? -1 : a.name.localeCompare(b.name),
      );
  });

  const layerColor = rulePresentation("layer").color;

  const tree = $derived(buildClassTree(filtered, KIND_ORDER));

  function bucketLabel(kind: string): string {
    if (kind === "external") return "External";
    const label = KIND_PRESENTATION[kind]?.label ?? kind;
    return label.endsWith("s") ? `${label}es` : `${label}s`;
  }

  // Which tree rows are expanded, keyed by row key. A search expands every row
  // so each match is on screen without extra clicks.
  let expanded = $state<Record<string, boolean>>({});
  const searching = $derived(query.trim() !== "");

  function isOpen(key: string): boolean {
    return searching || !!expanded[key];
  }

  function toggleExpand(key: string) {
    expanded[key] = !expanded[key];
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

  function toggleIds(ids: string[], on: boolean) {
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
</script>

{#snippet groupRow(key: string, label: string, ids: string[], depth: number, swatch: string | null)}
  {@const allVis = ids.every((id) => isVisible(id))}
  {@const someVis = ids.some((id) => isVisible(id))}
  <div class="group-row" style="padding-left:{0.5 + depth * 0.9}rem">
    <button
      type="button"
      class="caret"
      aria-expanded={isOpen(key)}
      title={isOpen(key) ? "Collapse" : "Expand"}
      onclick={() => toggleExpand(key)}>{isOpen(key) ? "▾" : "▸"}</button
    >
    <input
      type="checkbox"
      checked={allVis}
      indeterminate={someVis && !allVis}
      title="Show / hide everything in {label}"
      onchange={(e) => toggleIds(ids, (e.currentTarget as HTMLInputElement).checked)}
    />
    {#if swatch}<span class="swatch" style="background:{swatch}"></span>{/if}
    <button
      type="button"
      class="group-name"
      title={label}
      onclick={() => toggleExpand(key)}>{label}</button
    >
    <span class="count-pill">{ids.length}</span>
    <button
      type="button"
      class="only"
      title="Show only {label}"
      onclick={() => setVisibleSet(ids)}>only</button
    >
  </div>
{/snippet}

{#snippet classRow(node: ClassGraphNode, depth: number)}
  <li>
    <label class="class-row" title={node.qualifiedName} style="padding-left:{0.7 + depth * 0.9}rem">
      <input
        type="checkbox"
        checked={isVisible(node.id)}
        onchange={(e) => toggleVisible(node.id, (e.currentTarget as HTMLInputElement).checked)}
      />
      <button
        type="button"
        class="class-name-btn"
        class:active={diagramState.selectedClassId === node.id}
        onclick={() => select(node.id)}>{node.name}</button
      >
    </label>
  </li>
{/snippet}

{#snippet pkgContents(p: PkgNode, depth: number)}
  {#each p.children as c (c.path)}
    <li>
      {@render groupRow("p:" + c.path, c.label, c.ids, depth, null)}
      {#if isOpen("p:" + c.path)}
        <ul>{@render pkgContents(c, depth + 1)}</ul>
      {/if}
    </li>
  {/each}
  {#each p.buckets as b (b.kind)}
    {@const key = "k:" + p.path + "|" + b.kind}
    <li>
      {@render groupRow(key, bucketLabel(b.kind), b.ids, depth, kindPresentation(b.kind).color)}
      {#if isOpen(key)}
        <ul>
          {#each b.nodes as node (node.id)}
            {@render classRow(node, depth + 1)}
          {/each}
        </ul>
      {/if}
    </li>
  {/each}
{/snippet}

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
          <ul class="tree">
            {#each layers as l (l.name)}
              <li>
                {@render groupRow(
                  "l:" + l.name,
                  l.name,
                  l.ids,
                  0,
                  l.name === NO_LAYER ? "#cbd5e1" : layerColor,
                )}
                {#if isOpen("l:" + l.name)}
                  <ul>
                    {#each l.nodes as node (node.id)}
                      {@render classRow(node, 1)}
                    {/each}
                  </ul>
                {/if}
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
          <span class="count">{filtered.length} / {graph.nodes.length}</span>
        </div>
        <ul class="tree class-tree">
          {@render pkgContents(tree, 0)}
        </ul>
      </CollapsibleSection>
    </div>
  {/if}
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
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
  /* The class tree fills the rest of the sidebar and scrolls on its own, so
     the layers and saved views above it stay in place. */
  .classes {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
    padding-top: 0.4rem;
  }
  .classes > :global(.section) {
    flex: 1 1 auto;
    display: flex;
    flex-direction: column;
  }
  .class-tree {
    flex: 1 1 0;
    min-height: 10rem;
    overflow-y: auto;
    border-top: 1px solid var(--border);
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
  .tree,
  .tree :global(ul) {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .group-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.2rem 0.75rem 0.2rem 0.5rem;
    font-size: 0.85rem;
  }
  .group-row:hover {
    background: var(--hover);
  }
  .group-row input[type="checkbox"] {
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
  .group-name {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: none;
    text-align: left;
    cursor: pointer;
    color: var(--fg);
    font: inherit;
    padding: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .class-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.12rem 0.75rem;
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
  .count-pill {
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
  .error {
    color: #c63a3a;
    padding: 0.75rem;
  }
  .muted {
    color: var(--muted);
    padding: 0.75rem;
  }
</style>
