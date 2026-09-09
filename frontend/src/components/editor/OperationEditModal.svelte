<script lang="ts">
  import type { OperationDraft, ParameterDraft, Visibility } from "../../lib/api";
  import Modal from "./Modal.svelte";

  interface Props {
    open: boolean;
    initial: OperationDraft;
    classQnames: string[];
    onsave: (next: OperationDraft) => void;
    onclose: () => void;
  }

  let { open, initial, classQnames, onsave, onclose }: Props = $props();

  let name = $state(initial.name);
  let returnType = $state(initial.return_type);
  let visibility = $state<Visibility>(initial.visibility);
  let isStatic = $state(initial.is_static);
  let isAbstract = $state(initial.is_abstract);
  let description = $state(initial.description ?? "");
  let params = $state<ParameterDraft[]>(initial.parameters.map((p) => ({ ...p })));

  $effect(() => {
    if (open) {
      name = initial.name;
      returnType = initial.return_type;
      visibility = initial.visibility;
      isStatic = initial.is_static;
      isAbstract = initial.is_abstract;
      description = initial.description ?? "";
      params = initial.parameters.map((p) => ({ ...p }));
    }
  });

  function addParam() {
    params = [...params, { name: "arg", type: "", default: null }];
  }
  function removeParam(i: number) {
    params = params.filter((_, j) => j !== i);
  }

  function save() {
    onsave({
      name: name.trim() || "method",
      parameters: params.map((p) => ({
        name: p.name.trim() || "arg",
        type: p.type.trim(),
        default: p.default && p.default.trim() ? p.default : null,
      })),
      return_type: returnType.trim(),
      visibility,
      is_static: isStatic,
      is_abstract: isAbstract,
      description: description.trim() ? description : null,
      status: initial.status,
    });
  }
</script>

<Modal {open} title="Operation" width="560px" {onclose}>
  <div class="grid">
    <label>
      Name
      <input bind:value={name} placeholder="method" />
    </label>
    <label>
      Return type
      <input bind:value={returnType} placeholder="(optional)" list="op-types" />
    </label>
  </div>

  <datalist id="op-types">
    {#each classQnames as q}
      <option value={q}></option>
    {/each}
  </datalist>

  <fieldset>
    <legend>Visibility</legend>
    <div class="opts">
      {#each ["public", "protected", "private", "package"] as v}
        <label>
          <input type="radio" name="op-vis" value={v} bind:group={visibility} />
          {v}
        </label>
      {/each}
    </div>
  </fieldset>

  <fieldset>
    <legend>Modifiers</legend>
    <label class="check"><input type="checkbox" bind:checked={isStatic} /> static</label>
    <label class="check"><input type="checkbox" bind:checked={isAbstract} /> abstract</label>
  </fieldset>

  <fieldset>
    <legend>Parameters</legend>
    {#if params.length}
      <ul class="params">
        {#each params as p, i}
          <li>
            <input bind:value={p.name} placeholder="name" class="pname" />
            <span class="sep">:</span>
            <input
              bind:value={p.type}
              placeholder="type"
              list="op-types"
              class="ptype"
            />
            <input
              value={p.default ?? ""}
              oninput={(e) => (p.default = (e.currentTarget as HTMLInputElement).value || null)}
              placeholder="default (optional)"
              class="pdef"
            />
            <button type="button" class="danger" onclick={() => removeParam(i)}>×</button>
          </li>
        {/each}
      </ul>
    {/if}
    <button type="button" onclick={addParam}>+ Add parameter</button>
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
  .params {
    list-style: none;
    padding: 0;
    margin: 0 0 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .params li {
    display: grid;
    grid-template-columns: 1fr auto 1fr 1fr auto;
    gap: 0.3rem;
    align-items: center;
  }
  .sep {
    color: var(--muted, #64748b);
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
    padding: 0.2rem 0.4rem;
  }
</style>
