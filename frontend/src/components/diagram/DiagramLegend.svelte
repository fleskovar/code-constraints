<script lang="ts">
  import { KIND_ORDER, KIND_PRESENTATION } from "../../lib/kinds";
  import { diagramState, toggleLegend } from "../../lib/state/diagram.svelte";

  // Don't let clicks on the legend pan the canvas.
  function stop(e: Event) {
    e.stopPropagation();
  }
</script>

<div class="legend" onpointerdown={stop} role="presentation">
  {#if diagramState.legendOpen}
    <div class="head">
      <span class="title">Kinds</span>
      <button
        type="button"
        class="toggle"
        title="Hide legend"
        onclick={toggleLegend}>✕</button
      >
    </div>
    <ul>
      {#each KIND_ORDER as k (k)}
        <li>
          <span class="swatch" style="background:{KIND_PRESENTATION[k].color}"></span>
          <span class="label">{KIND_PRESENTATION[k].label}</span>
        </li>
      {/each}
    </ul>
  {:else}
    <button
      type="button"
      class="pill"
      title="Show kind legend"
      onclick={toggleLegend}>Legend ▸</button
    >
  {/if}
</div>

<style>
  .legend {
    position: absolute;
    left: 12px;
    bottom: 12px;
    z-index: 5;
    background: rgba(255, 255, 255, 0.95);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 6px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12);
    font-size: 0.75rem;
    color: var(--fg, #1a1a1a);
    user-select: none;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.3rem 0.5rem;
    border-bottom: 1px solid var(--border, #e5e7eb);
  }
  .title {
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.65rem;
    color: var(--muted, #6b7280);
  }
  .toggle {
    background: transparent;
    border: none;
    cursor: pointer;
    color: var(--muted, #6b7280);
    font-size: 0.8rem;
    line-height: 1;
    padding: 0;
  }
  .toggle:hover {
    color: var(--fg, #1a1a1a);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0.4rem 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  li {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .swatch {
    width: 0.8rem;
    height: 0.8rem;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .pill {
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 0.3rem 0.6rem;
    font-size: 0.75rem;
    color: var(--fg, #1a1a1a);
    font-weight: 500;
  }
  .pill:hover {
    color: var(--accent, #2563eb);
  }
</style>
