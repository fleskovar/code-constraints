<script lang="ts">
  import Modal from "./Modal.svelte";

  interface Props {
    open: boolean;
    sourceLabel: string;
    targetLabel: string;
    onpick: (kind: "inheritance" | "association") => void;
    onclose: () => void;
  }

  let { open, sourceLabel, targetLabel, onpick, onclose }: Props = $props();
</script>

<Modal {open} title="Connect classes" width="440px" {onclose}>
  <p class="muted">
    From <code>{sourceLabel}</code> to <code>{targetLabel}</code>. Pick a relationship.
  </p>
  <div class="opts">
    <button type="button" onclick={() => onpick("inheritance")}>
      <strong>Inheritance</strong>
      <span class="hint">{sourceLabel} extends/implements {targetLabel}</span>
    </button>
    <button type="button" onclick={() => onpick("association")}>
      <strong>Association</strong>
      <span class="hint">{sourceLabel} relates to {targetLabel}</span>
    </button>
  </div>

  {#snippet footer()}
    <button type="button" onclick={onclose}>Cancel</button>
  {/snippet}
</Modal>

<style>
  .muted {
    color: var(--muted, #64748b);
    margin: 0 0 0.75rem;
    font-size: 0.9rem;
  }
  code {
    background: var(--bg, #f1f5f9);
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
    font-size: 0.85em;
  }
  .opts {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .opts button {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    text-align: left;
    padding: 0.6rem 0.8rem;
    background: var(--surface, #fff);
    border: 1px solid var(--border, #cbd5e1);
    border-radius: 6px;
    cursor: pointer;
    gap: 0.15rem;
  }
  .opts button:hover {
    background: var(--hover, #f8fafc);
    border-color: var(--accent, #2563eb);
  }
  .hint {
    font-size: 0.8rem;
    color: var(--muted, #64748b);
  }
  footer button {
    background: var(--surface, #fff);
    border: 1px solid var(--border, #cbd5e1);
    border-radius: 4px;
    padding: 0.3rem 0.6rem;
    font-size: 0.85rem;
    cursor: pointer;
  }
</style>
