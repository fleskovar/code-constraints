<script lang="ts">
  import type { Snippet } from "svelte";

  // A toolbar dropdown on a native <details>. Checkbox items keep it open so
  // several can be toggled; a button item runs its action and closes it.
  let {
    label,
    title = "",
    align = "left",
    children,
  }: {
    label: string;
    title?: string;
    /** Which edge of the summary the menu lines up with. */
    align?: "left" | "right";
    children: Snippet;
  } = $props();

  let menu = $state<HTMLDetailsElement | null>(null);

  // A native <details> does not close on an outside click, so close it here.
  function onWindowClick(e: MouseEvent) {
    if (!menu?.open) return;
    const target = e.target as HTMLElement;
    if (!menu.contains(target) || target.closest(".menu-body button"))
      menu.open = false;
  }
</script>

<svelte:window onclick={onWindowClick} />

<details class="menu" bind:this={menu}>
  <summary {title}>{label} ▾</summary>
  <div class="menu-body" class:right={align === "right"}>
    {@render children()}
  </div>
</details>

<style>
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
  .menu-body.right {
    left: auto;
    right: 0;
  }
  .menu-body :global(label) {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .menu-body :global(button) {
    display: block;
    width: 100%;
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 0.3rem 0.4rem;
    text-align: left;
    font: inherit;
    color: var(--fg);
    cursor: pointer;
    white-space: nowrap;
  }
  .menu-body :global(button:hover:not(:disabled)) {
    background: var(--hover);
  }
  .menu-body :global(button:disabled) {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .menu-body :global(.menu-note) {
    display: block;
    color: var(--muted);
    font-size: 0.72rem;
    padding: 0 0.4rem;
    white-space: normal;
  }
  .menu-body :global(hr) {
    width: 100%;
    border: none;
    border-top: 1px solid var(--border);
    margin: 0.15rem 0;
  }
</style>
