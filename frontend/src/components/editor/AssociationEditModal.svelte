<script lang="ts">
  import type { AssociationDraft } from "../../lib/api";
  import Modal from "./Modal.svelte";

  interface Props {
    open: boolean;
    initial: AssociationDraft;
    classQnames: string[];
    isExisting: boolean;
    onsave: (next: AssociationDraft) => void;
    ondelete?: () => void;
    onclose: () => void;
  }

  let { open, initial, classQnames, isExisting, onsave, ondelete, onclose }: Props =
    $props();

  let source = $state(initial.source);
  let target = $state(initial.target);
  let name = $state(initial.name ?? "");
  let sourceMult = $state(initial.source_multiplicity ?? "");
  let targetMult = $state(initial.target_multiplicity ?? "");
  let sourceRole = $state(initial.source_role ?? "");
  let targetRole = $state(initial.target_role ?? "");

  $effect(() => {
    if (open) {
      source = initial.source;
      target = initial.target;
      name = initial.name ?? "";
      sourceMult = initial.source_multiplicity ?? "";
      targetMult = initial.target_multiplicity ?? "";
      sourceRole = initial.source_role ?? "";
      targetRole = initial.target_role ?? "";
    }
  });

  function save() {
    onsave({
      source: source.trim(),
      target: target.trim(),
      name: name.trim() || null,
      source_multiplicity: sourceMult.trim() || null,
      target_multiplicity: targetMult.trim() || null,
      source_role: sourceRole.trim() || null,
      target_role: targetRole.trim() || null,
      status: initial.status,
    });
  }
</script>

<Modal {open} title={isExisting ? "Edit association" : "New association"} width="560px" {onclose}>
  <div class="grid">
    <label>
      Source
      <input bind:value={source} list="assoc-classes" placeholder="qualified.name" />
    </label>
    <label>
      Target
      <input bind:value={target} list="assoc-classes" placeholder="qualified.name" />
    </label>
    <datalist id="assoc-classes">
      {#each classQnames as q}
        <option value={q}></option>
      {/each}
    </datalist>
    <label class="span2">
      Name (optional)
      <input bind:value={name} placeholder="owns / uses / ..." />
    </label>
    <label>
      Source multiplicity
      <input bind:value={sourceMult} placeholder="0..1 | 1 | *" />
    </label>
    <label>
      Target multiplicity
      <input bind:value={targetMult} placeholder="0..1 | 1 | *" />
    </label>
    <label>
      Source role
      <input bind:value={sourceRole} placeholder="(optional)" />
    </label>
    <label>
      Target role
      <input bind:value={targetRole} placeholder="(optional)" />
    </label>
  </div>

  {#snippet footer()}
    {#if isExisting && ondelete}
      <button type="button" class="danger" onclick={ondelete}>Delete association</button>
      <span style="flex: 1"></span>
    {/if}
    <button type="button" onclick={onclose}>Cancel</button>
    <button type="button" class="primary" onclick={save}>Save</button>
  {/snippet}
</Modal>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem 1rem;
  }
  .span2 {
    grid-column: span 2;
  }
  label {
    display: flex;
    flex-direction: column;
    font-size: 0.85rem;
    color: var(--muted, #475569);
    gap: 0.25rem;
  }
  input:not([type]),
  input[type="text"] {
    padding: 0.4rem 0.55rem;
    font-size: 0.9rem;
    border: 1px solid var(--border, #cbd5e1);
    border-radius: 4px;
    background: white;
    color: var(--fg, #0f172a);
  }
  button {
    background: var(--surface, #fff);
    border: 1px solid var(--border, #cbd5e1);
    border-radius: 4px;
    padding: 0.3rem 0.6rem;
    font-size: 0.85rem;
    cursor: pointer;
  }
  button.primary {
    background: var(--accent, #2563eb);
    border-color: var(--accent, #2563eb);
    color: white;
  }
  button.danger {
    color: #b91c1c;
    border-color: #fca5a5;
  }
</style>
