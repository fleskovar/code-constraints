<script lang="ts">
  import type { AttributeDraft, Visibility } from "../../lib/api";
  import Modal from "./Modal.svelte";

  interface Props {
    open: boolean;
    initial: AttributeDraft;
    classQnames: string[];
    onsave: (next: AttributeDraft) => void;
    onclose: () => void;
  }

  let { open, initial, classQnames, onsave, onclose }: Props = $props();

  let name = $state(initial.name);
  let type = $state(initial.type);
  let visibility = $state<Visibility>(initial.visibility);
  let isStatic = $state(initial.is_static);
  let isReadonly = $state(initial.is_readonly);
  let defaultValue = $state(initial.default ?? "");
  let description = $state(initial.description ?? "");

  $effect(() => {
    if (open) {
      name = initial.name;
      type = initial.type;
      visibility = initial.visibility;
      isStatic = initial.is_static;
      isReadonly = initial.is_readonly;
      defaultValue = initial.default ?? "";
      description = initial.description ?? "";
    }
  });

  function save() {
    onsave({
      name: name.trim() || "field",
      type: type.trim(),
      visibility,
      is_static: isStatic,
      is_readonly: isReadonly,
      default: defaultValue.trim() ? defaultValue : null,
      description: description.trim() ? description : null,
      status: initial.status,
    });
  }
</script>

<Modal {open} title="Attribute" width="460px" {onclose}>
  <div class="grid">
    <label>
      Name
      <input bind:value={name} placeholder="field" />
    </label>
    <label>
      Type
      <input bind:value={type} placeholder="str | int | MyClass" list="attr-types" />
      <datalist id="attr-types">
        {#each classQnames as q}
          <option value={q}></option>
        {/each}
      </datalist>
    </label>
    <label class="span2">
      Default value
      <input bind:value={defaultValue} placeholder="(optional)" />
    </label>
  </div>
  <fieldset>
    <legend>Visibility</legend>
    <div class="opts">
      {#each ["public", "protected", "private", "package"] as v}
        <label>
          <input type="radio" name="vis" value={v} bind:group={visibility} />
          {v}
        </label>
      {/each}
    </div>
  </fieldset>
  <fieldset>
    <legend>Modifiers</legend>
    <label class="check"><input type="checkbox" bind:checked={isStatic} /> static</label>
    <label class="check"><input type="checkbox" bind:checked={isReadonly} /> readonly</label>
  </fieldset>
  <label class="description-label">
    Description
    <textarea bind:value={description} rows="3" placeholder="Optional natural-language description"></textarea>
  </label>
  {#snippet footer()}
    <button type="button" onclick={onclose}>Cancel</button>
    <button type="button" class="primary" onclick={save}>Save</button>
  {/snippet}
</Modal>

<style>
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem 1rem;
    margin-bottom: 0.75rem;
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
  label.check {
    flex-direction: row;
    align-items: center;
    gap: 0.4rem;
    color: var(--fg, #0f172a);
    margin-right: 1rem;
  }
  input:not([type]),
  input[type="text"],
  textarea {
    padding: 0.4rem 0.55rem;
    font-size: 0.9rem;
    border: 1px solid var(--border, #cbd5e1);
    border-radius: 4px;
    background: white;
    color: var(--fg, #0f172a);
    font-family: inherit;
    resize: vertical;
  }
  .description-label {
    margin-bottom: 0.75rem;
  }
  fieldset {
    border: 1px solid var(--border, #e2e8f0);
    border-radius: 6px;
    padding: 0.5rem 0.75rem 0.75rem;
    margin-bottom: 0.75rem;
  }
  legend {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted, #64748b);
    padding: 0 0.25rem;
  }
  .opts {
    display: flex;
    gap: 0.5rem 1rem;
    flex-wrap: wrap;
  }
  .opts label {
    flex-direction: row;
    text-transform: capitalize;
    color: var(--fg, #0f172a);
    gap: 0.25rem;
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
</style>
