<script lang="ts">
  import Modal from "../editor/Modal.svelte";
  import { api, type ClassGraph, type ClassGraphNode, type XmiInfo } from "../../lib/api";
  import { layerClassesPanel, closeLayerClasses } from "../../lib/state/layerClasses.svelte";
  import { layerName, rulePresentation } from "../../lib/rules";
  import {
    diagramState,
    isVisible,
    setVisible,
    setVisibleSet,
  } from "../../lib/state/diagram.svelte";

  let { xmi }: { xmi: XmiInfo } = $props();

  let graph = $state<ClassGraph | null>(null);
  let loadedFor = $state<string | null>(null);
  let error = $state("");

  $effect(() => {
    if (!layerClassesPanel.open) return;
    if (loadedFor === xmi.id && graph) return;
    error = "";
    api
      .classGraph(xmi.id)
      .then((g) => {
        graph = g;
        loadedFor = xmi.id;
      })
      .catch((e: Error) => (error = e.message));
  });

  const layerColor = rulePresentation("layer").color;

  const layerNodes = $derived.by((): ClassGraphNode[] => {
    if (!graph || !layerClassesPanel.layerName) return [];
    return graph.nodes.filter((n) => {
      const r = n.rules.find((x) => x.name === "layer");
      return r ? layerName(r) === layerClassesPanel.layerName : false;
    });
  });

  const visibleCount = $derived(layerNodes.filter((n) => isVisible(n.id)).length);

  function toggleNodeVisible(id: string, on: boolean) {
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

<Modal
  open={layerClassesPanel.open}
  title="Layer: {layerClassesPanel.layerName ?? ''}"
  width="420px"
  onclose={closeLayerClasses}
>
  {#if error}
    <p class="msg error">{error}</p>
  {:else if !graph}
    <p class="msg muted">Loading…</p>
  {:else if layerNodes.length === 0}
    <p class="msg muted">No classes found in this layer.</p>
  {:else}
    <p class="summary">
      <span class="badge" style="background:{layerColor}">layer: {layerClassesPanel.layerName}</span>
      <span class="counts">{visibleCount} visible · {layerNodes.length - visibleCount} hidden</span>
    </p>
    <ul class="class-list">
      {#each layerNodes as node (node.id)}
        {@const visible = isVisible(node.id)}
        <li class:hidden={!visible}>
          <label class="row" title="{node.qualifiedName} — {visible ? 'visible' : 'hidden'} on canvas">
            <input
              type="checkbox"
              checked={visible}
              onchange={(e) => toggleNodeVisible(node.id, (e.currentTarget as HTMLInputElement).checked)}
            />
            <span class="vis-dot" class:on={visible} title={visible ? 'Visible' : 'Hidden'}></span>
            <span class="class-name">{node.name}</span>
            {#if node.package}
              <span class="pkg">{node.package}</span>
            {/if}
          </label>
        </li>
      {/each}
    </ul>
  {/if}
</Modal>

<style>
  .msg {
    margin: 0 0 0.5rem;
    font-size: 0.875rem;
  }
  .error { color: #c63a3a; }
  .muted { color: var(--muted, #64748b); }

  .summary {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 0 0 0.75rem;
  }
  .badge {
    color: #fff;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 4px;
  }
  .counts {
    font-size: 0.8rem;
    color: var(--muted, #64748b);
  }

  .class-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
    max-height: 55vh;
    overflow-y: auto;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    border-radius: 5px;
    cursor: pointer;
    font-size: 0.875rem;
    background: var(--hover, #f1f5f9);
  }
  .row:hover {
    background: #e2e8f0;
  }

  li.hidden .row {
    opacity: 0.55;
  }

  /* Coloured dot: green = visible, grey = hidden */
  .vis-dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    flex-shrink: 0;
    background: #cbd5e1;
    border: 1.5px solid #94a3b8;
  }
  .vis-dot.on {
    background: #22c55e;
    border-color: #16a34a;
  }

  .class-name {
    flex: 1;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .pkg {
    font-size: 0.7rem;
    color: var(--muted, #64748b);
    font-family: ui-monospace, SFMono-Regular, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 8rem;
  }
</style>
