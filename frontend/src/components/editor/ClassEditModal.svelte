<script lang="ts">
  import type {
    AttributeDraft,
    ClassDraft,
    ClassKind,
    OperationDraft,
  } from "../../lib/api";
  import {
    allClassQnames,
    defaultAttribute,
    defaultOperation,
  } from "../../lib/state/editor.svelte";
  import Modal from "./Modal.svelte";
  import AttributeEditModal from "./AttributeEditModal.svelte";
  import OperationEditModal from "./OperationEditModal.svelte";

  interface Props {
    open: boolean;
    initial: ClassDraft;
    /** True if this is editing an existing class (controls Delete visibility). */
    isExisting: boolean;
    onsave: (next: ClassDraft) => void;
    ondelete?: () => void;
    onclose: () => void;
  }

  let { open, initial, isExisting, onsave, ondelete, onclose }: Props = $props();

  let name = $state(initial.name);
  let qname = $state(initial.qualified_name);
  let pkg = $state(packageOf(initial.qualified_name));
  let kind = $state<ClassKind>(initial.kind);
  let bases = $state<string[]>([...initial.bases]);
  let description = $state(initial.description ?? "");
  let attributes = $state<AttributeDraft[]>(initial.attributes.map(copyAttr));
  let operations = $state<OperationDraft[]>(initial.operations.map(copyOp));
  let baseInput = $state("");
  let attrEdit = $state<{ index: number; value: AttributeDraft } | null>(null);
  let opEdit = $state<{ index: number; value: OperationDraft } | null>(null);
  let userEditedQname = $state(false);

  $effect(() => {
    // When the dialog opens with a new class, re-sync local state from `initial`.
    if (open) {
      name = initial.name;
      qname = initial.qualified_name;
      pkg = packageOf(initial.qualified_name);
      kind = initial.kind;
      bases = [...initial.bases];
      description = initial.description ?? "";
      attributes = initial.attributes.map(copyAttr);
      operations = initial.operations.map(copyOp);
      baseInput = "";
      userEditedQname = false;
    }
  });

  // Auto-suggest qualified_name from package + name until the user edits it
  // directly.
  $effect(() => {
    if (!userEditedQname) {
      qname = pkg ? `${pkg}.${name}` : name;
    }
  });

  function packageOf(qn: string): string {
    const i = qn.lastIndexOf(".");
    return i >= 0 ? qn.slice(0, i) : "";
  }

  function copyAttr(a: AttributeDraft): AttributeDraft {
    return { ...a };
  }
  function copyOp(o: OperationDraft): OperationDraft {
    return { ...o, parameters: o.parameters.map((p) => ({ ...p })) };
  }

  const otherClassQnames = $derived(
    allClassQnames().filter((q) => q !== initial.qualified_name),
  );

  function addBase() {
    const v = baseInput.trim();
    if (v && !bases.includes(v)) {
      bases = [...bases, v];
    }
    baseInput = "";
  }
  function removeBase(b: string) {
    bases = bases.filter((x) => x !== b);
  }

  function addAttr() {
    attrEdit = { index: -1, value: defaultAttribute() };
  }
  function editAttr(i: number) {
    attrEdit = { index: i, value: copyAttr(attributes[i]) };
  }
  function saveAttr(value: AttributeDraft) {
    if (!attrEdit) return;
    if (attrEdit.index < 0) attributes = [...attributes, value];
    else
      attributes = attributes.map((a, i) => (i === attrEdit!.index ? value : a));
    attrEdit = null;
  }
  function deleteAttr(i: number) {
    attributes = attributes.filter((_, j) => j !== i);
  }

  function addOp() {
    opEdit = { index: -1, value: defaultOperation() };
  }
  function editOp(i: number) {
    opEdit = { index: i, value: copyOp(operations[i]) };
  }
  function saveOp(value: OperationDraft) {
    if (!opEdit) return;
    if (opEdit.index < 0) operations = [...operations, value];
    else operations = operations.map((o, i) => (i === opEdit!.index ? value : o));
    opEdit = null;
  }
  function deleteOp(i: number) {
    operations = operations.filter((_, j) => j !== i);
  }

  function save() {
    onsave({
      name: name.trim() || "Untitled",
      qualified_name: qname.trim() || name.trim() || "Untitled",
      kind,
      attributes,
      operations,
      bases,
      location: initial.location,
      layout: initial.layout,
      description: description.trim() ? description : null,
      status: initial.status,
    });
  }

  function visSymbol(v: string): string {
    return v === "private" ? "-" : v === "protected" ? "#" : v === "package" ? "~" : "+";
  }
</script>

<Modal {open} title={isExisting ? "Edit class" : "New class"} width="640px" {onclose}>
  <div class="grid">
    <label>
      Name
      <input bind:value={name} placeholder="MyClass" />
    </label>
    <label>
      Package
      <input bind:value={pkg} placeholder="com.example (optional)" list="pkg-list" />
    </label>
    <label class="span2">
      Qualified name
      <input
        bind:value={qname}
        oninput={() => (userEditedQname = true)}
      />
    </label>
  </div>

  <label class="description-label">
    Description
    <textarea bind:value={description} rows="3" placeholder="Optional natural-language description"></textarea>
  </label>

  <fieldset>
    <legend>Kind</legend>
    <div class="kind-row">
      {#each ["class", "abstract", "interface", "struct", "enum", "record", "static"] as k}
        <label class="kind-opt">
          <input type="radio" name="kind" value={k} bind:group={kind} />
          {k}
        </label>
      {/each}
    </div>
  </fieldset>

  <fieldset>
    <legend>Bases / implements</legend>
    {#if bases.length}
      <ul class="chips">
        {#each bases as b}
          <li>
            <span>{b}</span>
            <button type="button" onclick={() => removeBase(b)} aria-label="Remove">×</button>
          </li>
        {/each}
      </ul>
    {/if}
    <div class="add-base">
      <input
        bind:value={baseInput}
        placeholder="Qualified name of base class/interface"
        list="base-list"
        onkeydown={(e) => e.key === "Enter" && (e.preventDefault(), addBase())}
      />
      <button type="button" onclick={addBase}>Add base</button>
      <datalist id="base-list">
        {#each otherClassQnames as q}
          <option value={q}></option>
        {/each}
      </datalist>
    </div>
  </fieldset>

  <fieldset>
    <legend>Attributes</legend>
    {#if attributes.length}
      <ul class="rows">
        {#each attributes as a, i}
          <li>
            <code class="member-row">
              <span class="vis">{visSymbol(a.visibility)}</span>
              <span class="mname">{a.name}</span>{#if a.type}<span class="mtype"
                  >: {a.type}</span
                >{/if}
            </code>
            <span class="row-actions">
              <button type="button" onclick={() => editAttr(i)}>Edit</button>
              <button type="button" class="danger" onclick={() => deleteAttr(i)}>Remove</button>
            </span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">No attributes.</p>
    {/if}
    <button type="button" onclick={addAttr}>+ Add attribute</button>
  </fieldset>

  <fieldset>
    <legend>Operations</legend>
    {#if operations.length}
      <ul class="rows">
        {#each operations as o, i}
          <li>
            <code class="member-row">
              <span class="vis">{visSymbol(o.visibility)}</span>
              <span class="mname">{o.name}</span>(<span class="params"
                >{o.parameters.map((p) => `${p.name}${p.type ? ": " + p.type : ""}`).join(", ")}</span
              >){#if o.return_type}<span class="mtype">: {o.return_type}</span>{/if}
            </code>
            <span class="row-actions">
              <button type="button" onclick={() => editOp(i)}>Edit</button>
              <button type="button" class="danger" onclick={() => deleteOp(i)}>Remove</button>
            </span>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="muted">No operations.</p>
    {/if}
    <button type="button" onclick={addOp}>+ Add operation</button>
  </fieldset>

  {#snippet footer()}
    {#if isExisting && ondelete}
      <button type="button" class="danger" onclick={ondelete}>Delete class</button>
      <span style="flex: 1"></span>
    {/if}
    <button type="button" onclick={onclose}>Cancel</button>
    <button type="button" class="primary" onclick={save}>Save</button>
  {/snippet}
</Modal>

{#if attrEdit}
  <AttributeEditModal
    open
    initial={attrEdit.value}
    classQnames={otherClassQnames}
    onsave={saveAttr}
    onclose={() => (attrEdit = null)}
  />
{/if}

{#if opEdit}
  <OperationEditModal
    open
    initial={opEdit.value}
    classQnames={otherClassQnames}
    onsave={saveOp}
    onclose={() => (opEdit = null)}
  />
{/if}

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
  input[type="text"],
  input:not([type]),
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
  .kind-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
    align-items: center;
  }
  .kind-opt {
    flex-direction: row;
    color: var(--fg, #0f172a);
    gap: 0.25rem;
    text-transform: capitalize;
  }
  .chips {
    list-style: none;
    padding: 0;
    margin: 0 0 0.5rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .chips li {
    background: #e0f2fe;
    color: #075985;
    border-radius: 999px;
    padding: 0.15rem 0.5rem 0.15rem 0.7rem;
    font-size: 0.8rem;
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
  }
  .chips button {
    background: transparent;
    border: none;
    cursor: pointer;
    color: #075985;
    font-size: 1rem;
    line-height: 1;
  }
  .add-base {
    display: flex;
    gap: 0.4rem;
  }
  .add-base input {
    flex: 1;
  }
  .rows {
    list-style: none;
    padding: 0;
    margin: 0 0 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .rows li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.25rem 0.5rem;
    background: var(--bg, #f8fafc);
    border-radius: 4px;
  }
  .member-row {
    font-size: 0.85rem;
    color: var(--fg, #0f172a);
  }
  .vis {
    color: var(--muted, #64748b);
    margin-right: 0.25rem;
  }
  .mtype {
    color: var(--muted, #475569);
  }
  .row-actions {
    display: flex;
    gap: 0.3rem;
  }
  button {
    background: var(--surface, #fff);
    border: 1px solid var(--border, #cbd5e1);
    border-radius: 4px;
    padding: 0.3rem 0.6rem;
    font-size: 0.85rem;
    cursor: pointer;
  }
  button:hover {
    background: var(--hover, #f1f5f9);
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
  button.danger:hover {
    background: #fef2f2;
  }
  .muted {
    color: var(--muted, #64748b);
    margin: 0 0 0.5rem;
    font-size: 0.85rem;
  }
</style>
