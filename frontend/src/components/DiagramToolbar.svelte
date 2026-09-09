<script lang="ts">
  import {
    diagramState,
    showAll,
    hideAll,
    focusOn,
    reveal,
    collapseReveal,
    requestRelayout,
    toggleLod,
  } from "../lib/state/diagram.svelte";
  import { openLayers } from "../lib/state/layers.svelte";
  import { openEdgeFocus } from "../lib/state/edgeFocus.svelte";
  import { api, type XmiInfo } from "../lib/api";

  // Only class/package diagrams expose graph navigation; activity/sequence pass
  // "other" and the toolbar renders nothing.
  let { kind, xmi }: { kind: "class" | "package" | "other"; xmi: XmiInfo } =
    $props();

  const hasSelection = $derived(diagramState.selectedClassId !== null);
  const hasEdgeSelection = $derived(diagramState.selectedEdgeId !== null);
  const canCollapse = $derived(diagramState.revealStack.length > 0);

  let savingRef = $state(false);
  let refStatus = $state<{ kind: "ok" | "error"; msg: string } | null>(null);

  async function setAsReference() {
    savingRef = true;
    refStatus = null;
    try {
      const res = await fetch(`/api/xmi/${xmi.id}/source`);
      if (!res.ok) throw new Error(`fetch source: ${res.status}`);
      const blob = await res.blob();
      await api.setReference(xmi.project_id, blob);
      refStatus = { kind: "ok", msg: "Saved as reference" };
    } catch (e) {
      refStatus = { kind: "error", msg: (e as Error).message };
    } finally {
      savingRef = false;
      setTimeout(() => (refStatus = null), 4000);
    }
  }
</script>

{#if kind === "class" || kind === "package"}
  <div class="diagram-tools">
    {#if kind === "class"}
      <div class="group">
        <button
          class="toggle"
          class:on={diagramState.lodEnabled}
          onclick={toggleLod}
          title="Level-of-detail: as you zoom out, simplify nodes to headers, then hide edges, then hide derived classes. Toggle off to always show full detail."
          aria-pressed={diagramState.lodEnabled}
        >
          LOD {diagramState.lodEnabled ? "on" : "off"}
        </button>
      </div>
    {/if}
    <div class="group">
      <button onclick={showAll} title="Show every element">Show all</button>
      <button onclick={hideAll} title="Hide every element">Hide all</button>
    </div>
    <div class="group">
      <button
        onclick={() => focusOn(diagramState.selectedClassId!)}
        disabled={!hasSelection}
        title="Show only the selected element, then reveal neighbours step by step"
      >
        Focus
      </button>
      <button
        onclick={() => reveal("up", diagramState.currentEdges)}
        disabled={!hasSelection}
        title="Reveal one more ring of upstream neighbours (things that depend on the visible elements)"
      >
        ↑ upstream
      </button>
      <button
        onclick={() => reveal("down", diagramState.currentEdges)}
        disabled={!hasSelection}
        title="Reveal one more ring of downstream neighbours (things the visible elements depend on)"
      >
        ↓ downstream
      </button>
      <button
        onclick={collapseReveal}
        disabled={!canCollapse}
        title="Hide the most recently revealed ring"
      >
        Collapse
      </button>
    </div>
    {#if kind === "class"}
      <div class="group">
        <button
          onclick={() => openEdgeFocus(diagramState.selectedEdgeId!)}
          disabled={!hasEdgeSelection}
          title="Show the two classes joined by the selected edge, side by side (shortcut: f)"
        >
          Focus edge (f)
        </button>
      </div>
    {/if}
    <div class="group">
      <button
        onclick={requestRelayout}
        title="Re-run auto-layout over the currently-visible elements"
      >
        Compact
      </button>
      {#if kind === "class"}
        <button
          class="accent"
          onclick={() => openLayers(null)}
          title="Show the architectural layers and their allowed dependencies (rules.yaml)"
        >
          Layers &amp; rules
        </button>
      {/if}
    </div>
    {#if kind === "class"}
      <div class="group">
        <button
          class="accent"
          onclick={setAsReference}
          disabled={savingRef}
          title="Save the current diagram as this project's reference architecture (.cdec/reference.xmi)"
        >
          {savingRef ? "Saving…" : "Set as reference"}
        </button>
        {#if refStatus}
          <span class="ref-status {refStatus.kind}">{refStatus.msg}</span>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .diagram-tools {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .group {
    display: flex;
    gap: 0.25rem;
    align-items: center;
  }
  .group + .group {
    border-left: 1px solid var(--border);
    padding-left: 0.6rem;
  }
  .diagram-tools button {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.2rem 0.55rem;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--fg);
    white-space: nowrap;
  }
  .diagram-tools button:hover:not(:disabled) {
    background: var(--hover);
  }
  .diagram-tools button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .diagram-tools button.toggle.on {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
    font-weight: 600;
  }
  .diagram-tools button.accent {
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 600;
  }
  .diagram-tools button.accent:hover:not(:disabled) {
    background: var(--accent);
    color: #fff;
  }
  .ref-status {
    font-size: 0.75rem;
    white-space: nowrap;
  }
  .ref-status.ok {
    color: #166534;
  }
  .ref-status.error {
    color: #c63a3a;
  }
</style>
