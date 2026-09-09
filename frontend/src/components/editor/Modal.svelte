<script lang="ts">
  // Minimal dialog primitive. Backdrop click + Esc close.
  // No focus-trap library: the first input inside is focused on mount, which
  // is enough for the small forms in this editor.

  interface Props {
    open: boolean;
    title: string;
    width?: string;
    onclose: () => void;
    children?: import("svelte").Snippet;
    footer?: import("svelte").Snippet;
  }

  let { open, title, width = "520px", onclose, children, footer }: Props = $props();

  function onKey(e: KeyboardEvent) {
    if (e.key === "Escape") onclose();
  }
</script>

<svelte:window onkeydown={onKey} />

{#if open}
  <div
    class="backdrop"
    onclick={onclose}
    role="presentation"
  ></div>
  <div
    class="dialog"
    style:width={width}
    role="dialog"
    aria-modal="true"
    aria-label={title}
  >
    <header>
      <h2>{title}</h2>
      <button class="close" aria-label="Close" onclick={onclose}>×</button>
    </header>
    <div class="body">
      {@render children?.()}
    </div>
    {#if footer}
      <footer>
        {@render footer()}
      </footer>
    {/if}
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.45);
    z-index: 50;
  }
  .dialog {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 51;
    background: var(--surface, white);
    color: var(--fg, #0f172a);
    border-radius: 8px;
    box-shadow: 0 20px 50px rgba(15, 23, 42, 0.35);
    max-width: 92vw;
    max-height: 88vh;
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border, #e2e8f0);
  }
  header h2 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }
  .close {
    background: transparent;
    border: none;
    font-size: 1.4rem;
    cursor: pointer;
    line-height: 1;
    color: var(--muted, #64748b);
  }
  .close:hover {
    color: var(--fg, #0f172a);
  }
  .body {
    padding: 1rem;
    overflow: auto;
  }
  footer {
    padding: 0.75rem 1rem;
    border-top: 1px solid var(--border, #e2e8f0);
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }
</style>
