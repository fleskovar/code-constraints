<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    title,
    defaultOpen = true,
    indent = false,
    children,
    action,
  }: {
    title: string;
    defaultOpen?: boolean;
    /** Pad the header horizontally to 0.75rem when the parent container doesn't. */
    indent?: boolean;
    children: Snippet;
    action?: Snippet;
  } = $props();

  let open = $state(defaultOpen);
</script>

<div class="section">
  <div class="section-header" class:indent>
    <button
      type="button"
      class="toggle"
      aria-expanded={open}
      title={open ? "Collapse" : "Expand"}
      onclick={() => (open = !open)}
    >
      <span class="caret">{open ? "▾" : "▸"}</span>
      <span class="title">{title}</span>
    </button>
    {#if action}
      <span class="action">{@render action()}</span>
    {/if}
  </div>
  {#if open}
    {@render children()}
  {/if}
</div>

<style>
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
    margin-bottom: 0.3rem;
  }
  .section-header.indent {
    padding: 0 0.75rem;
  }
  .toggle {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 0.3rem;
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 0;
    text-align: left;
    font-size: 0.7rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .toggle:hover .title {
    color: var(--fg);
  }
  .caret {
    flex-shrink: 0;
    width: 0.8rem;
    font-size: 0.7rem;
    line-height: 1;
    color: var(--muted);
  }
  .title {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .action {
    flex-shrink: 0;
  }
</style>
