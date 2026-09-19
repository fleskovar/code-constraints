<script lang="ts">
  import {
    diagramState,
    showAll,
    hideAll,
    focusOn,
    reveal,
    collapseReveal,
    canCollapse,
    requestRelayout,
    type RevealVia,
  } from "../lib/state/diagram.svelte";
  import { openLayers } from "../lib/state/layers.svelte";
  import { openEdgeFocus } from "../lib/state/edgeFocus.svelte";
  import { api, type XmiInfo } from "../lib/api";

  // Only class/package diagrams expose graph navigation; activity/sequence pass
  // "other" and the toolbar renders nothing.
  let { kind, xmi }: { kind: "class" | "package" | "other"; xmi: XmiInfo } =
    $props();

  // What Show all / Hide all act on. "all" = the classes (and, for Show all,
  // every line); the edge kinds only toggle those lines and keep the classes.
  let scope = $state<RevealVia>("all");

  function setAll(on: boolean) {
    if (kind !== "class" || scope === "all") {
      if (on) {
        showAll();
        diagramState.showInheritanceEdges = true;
        diagramState.showReferenceEdges = true;
      } else hideAll();
    } else if (scope === "inheritance") diagramState.showInheritanceEdges = on;
    else diagramState.showReferenceEdges = on;
  }

  const scopeLabel = $derived(
    kind !== "class" || scope === "all"
      ? "every element"
      : scope === "inheritance"
        ? "every inheritance line"
        : "every reference line",
  );

  const hasSelection = $derived(diagramState.selectedClassId !== null);
  const hasEdgeSelection = $derived(diagramState.selectedEdgeId !== null);

  // A native <details> does not close on an outside click, so close it here.
  let displayMenu = $state<HTMLDetailsElement | null>(null);
  function closeMenuOnOutsideClick(e: MouseEvent) {
    if (displayMenu?.open && !displayMenu.contains(e.target as Node))
      displayMenu.open = false;
  }

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

<svelte:window onclick={closeMenuOnOutsideClick} />

{#if kind === "class" || kind === "package"}
  <div class="diagram-tools">
    {#if kind === "class"}
      <div class="group">
        <details class="menu" bind:this={displayMenu}>
          <summary title="Choose what the class nodes show">Display ▾</summary>
          <div class="menu-body">
            <label
              title="Level-of-detail: as you zoom out, simplify nodes to headers, then hide edges, then hide derived classes. Turn off to always show full detail."
            >
              <input type="checkbox" bind:checked={diagramState.lodEnabled} />
              Level of detail (LOD)
            </label>
            <label>
              <input type="checkbox" bind:checked={diagramState.showAttributes} />
              Attributes
            </label>
            <label>
              <input type="checkbox" bind:checked={diagramState.showOperations} />
              Methods
            </label>
            <label>
              <input type="checkbox" bind:checked={diagramState.showInheritanceEdges} />
              Inheritance lines
            </label>
            <label>
              <input type="checkbox" bind:checked={diagramState.showReferenceEdges} />
              Reference lines
            </label>
          </div>
        </details>
      </div>
    {/if}
    <div class="group">
      {#if kind === "class"}
        <select
          class="scope"
          bind:value={scope}
          title="What Show all / Hide all act on: the classes, or only one kind of relationship line"
        >
          <option value="all">Everything</option>
          <option value="inheritance">Inheritance</option>
          <option value="association">References</option>
        </select>
      {/if}
      <button onclick={() => setAll(true)} title="Show {scopeLabel}">Show all</button>
      <button onclick={() => setAll(false)} title="Hide {scopeLabel}">Hide all</button>
    </div>
    <div class="group">
      <button
        onclick={() => focusOn(diagramState.selectedClassId!)}
        disabled={!hasSelection}
        title="Show only the selected element, then reveal neighbours step by step"
      >
        Focus
      </button>
      {#if kind === "class"}
        <label class="via" title="Which relationships upstream / downstream follow">
          via
          <select bind:value={diagramState.revealVia}>
            <option value="all">All</option>
            <option value="inheritance">Inheritance</option>
            <option value="association">References</option>
          </select>
        </label>
      {/if}
      <span class="split">
        <button
          onclick={() => reveal("up", diagramState.currentEdges)}
          disabled={!hasSelection}
          title="Reveal one more ring of upstream neighbours (things that depend on the visible elements)"
        >
          ↑ upstream
        </button>
        <button
          class="hide"
          onclick={() => collapseReveal("up")}
          disabled={!canCollapse("up")}
          aria-label="Hide upstream ring"
          title="Hide the most recently revealed upstream ring"
        >
          −
        </button>
      </span>
      <span class="split">
        <button
          onclick={() => reveal("down", diagramState.currentEdges)}
          disabled={!hasSelection}
          title="Reveal one more ring of downstream neighbours (things the visible elements depend on)"
        >
          ↓ downstream
        </button>
        <button
          class="hide"
          onclick={() => collapseReveal("down")}
          disabled={!canCollapse("down")}
          aria-label="Hide downstream ring"
          title="Hide the most recently revealed downstream ring"
        >
          −
        </button>
      </span>
      <button
        onclick={() => collapseReveal()}
        disabled={!canCollapse()}
        title="Hide the most recently revealed ring, in either direction"
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
  .via {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--muted);
  }
  .via select,
  select.scope {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.15rem 0.3rem;
    font-size: 0.8rem;
    color: var(--fg);
  }
  /* Reveal + hide pair drawn as one joined control. */
  .split {
    display: inline-flex;
  }
  .split button:first-child {
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
  }
  .diagram-tools .split button.hide {
    border-left: none;
    border-top-left-radius: 0;
    border-bottom-left-radius: 0;
    padding: 0.2rem 0.45rem;
  }
  .diagram-tools button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .menu {
    position: relative;
  }
  .menu summary {
    list-style: none;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.2rem 0.55rem;
    font-size: 0.8rem;
    cursor: pointer;
    color: var(--fg);
    white-space: nowrap;
    user-select: none;
  }
  .menu summary::-webkit-details-marker {
    display: none;
  }
  .menu summary:hover,
  .menu[open] summary {
    background: var(--hover);
  }
  .menu-body {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 20;
    min-width: 12rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 0.5rem 0.65rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    font-size: 0.8rem;
  }
  .menu-body label {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    cursor: pointer;
    white-space: nowrap;
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
