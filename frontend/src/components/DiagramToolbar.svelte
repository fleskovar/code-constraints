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
  import { openEdgeFocus } from "../lib/state/edgeFocus.svelte";
  import ToolbarMenu from "./ToolbarMenu.svelte";

  // Canvas tools for view mode, grouped by task: what is visible, how to walk
  // the graph, and the layout. Project actions live in the Architecture menu.
  // Only class/package diagrams have them; activity/sequence render nothing.
  let { kind }: { kind: "class" | "package" | "other" } = $props();

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
  // A reveal grows from the selection, and `a` selects without a single
  // selected element.
  const canReveal = $derived(hasSelection || diagramState.highlightedNodeIds.size > 0);
  const hasEdgeSelection = $derived(diagramState.selectedEdgeId !== null);
</script>

{#if kind === "class" || kind === "package"}
  <div class="diagram-tools">
    <div class="group" role="group" aria-label="Visibility">
      <span class="group-label" aria-hidden="true">Visibility</span>
      {#if kind === "class"}
        <ToolbarMenu label="Display" title="Choose what the class nodes and lines show">
          <label
            title="Level of detail: as you zoom out, simplify nodes to headers, then hide lines, then hide derived classes. Turn off to always show full detail."
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
        </ToolbarMenu>
        <select
          class="scope"
          bind:value={scope}
          aria-label="Show all / Hide all act on"
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
    <div class="group" role="group" aria-label="Explore">
      <span class="group-label" aria-hidden="true">Explore</span>
      <button
        onclick={() => focusOn(diagramState.selectedClassId!)}
        disabled={!hasSelection}
        title="Hide everything except the selected element, then reveal its neighbours step by step"
      >
        Isolate
      </button>
      {#if kind === "class"}
        <label class="via" title="Which relationships upstream / downstream follow">
          follow
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
          disabled={!canReveal}
          title={kind === "class"
            ? "Reveal one more ring above the selected classes: their base classes, and the classes that reference them"
            : "Reveal one more ring of upstream neighbours (things that depend on the selected elements)"}
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
          disabled={!canReveal}
          title={kind === "class"
            ? "Reveal one more ring below the selected classes: the classes derived from them, and the classes they reference"
            : "Reveal one more ring of downstream neighbours (things the selected elements depend on)"}
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
        title="Undo the most recent reveal, in either direction"
      >
        Step back
      </button>
      {#if kind === "class"}
        <button
          onclick={() => openEdgeFocus(diagramState.selectedEdgeId!)}
          disabled={!hasEdgeSelection}
          title="Open the two classes joined by the selected line side by side, with the members that create it highlighted (shortcut: f)"
        >
          Inspect edge (f)
        </button>
      {/if}
    </div>
    <div class="group" role="group" aria-label="Layout">
      <span class="group-label" aria-hidden="true">Layout</span>
      <button
        onclick={requestRelayout}
        title="Re-run the auto-layout over the visible elements"
      >
        Re-layout
      </button>
    </div>
    <span
      class="keys"
      title="Keyboard: f fits the view on the selection. a selects every visible element. h hides the selection. Space moves to the search box."
    >
      <kbd>f</kbd> focus <kbd>a</kbd> select all <kbd>h</kbd> hide <kbd>Space</kbd> search
    </span>
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
  .keys {
    font-size: 0.7rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .keys kbd {
    font: inherit;
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 0 0.25rem;
    margin-left: 0.35rem;
    background: var(--surface);
    color: var(--fg);
  }
  .group-label {
    font-size: 0.65rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
    margin-right: 0.15rem;
  }
</style>
