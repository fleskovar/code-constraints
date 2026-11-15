<script lang="ts">
  // A form for one rule entry. The fields come from the entry: a text value
  // is a text field, a list is a list of fields, a mapping of lists is a small
  // table. A new rule type needs no code here. A field for a class or a
  // package name suggests the names of the project.
  import type { RuleEntry } from "../../lib/api";

  let {
    entry = $bindable(),
    names,
  }: { entry: RuleEntry; names: string[] } = $props();

  // What a key means, in the words of the rules catalogue.
  const HINTS: Record<string, string> = {
    from: "The side that must not use the other. Name patterns: * matches any text, pkg.** is a package and all below it.",
    to: "What the `from` side must not use.",
    ignore: "Names that this rule does not check.",
    classes: "The classes that the rule applies to.",
    kinds: "attribute, operation, or both.",
    members: "Member names or signatures. Empty: all members.",
    bases: "A new class must extend one of these.",
    base: "The base class or interface. A pattern is allowed: *Repository.",
    name_pattern: "A regular expression. The whole class name must match.",
    limit: "The highest number of other classes that one class may reference.",
    entry_points: "Classes that nothing references on purpose: the start of the program.",
    framework_bases: "Base classes of a framework. Their subclasses count as used.",
    allow: "Each layer, and the layers that it may reference. A layer with an empty list may reference no other layer.",
    rules: "The tags to check. Empty: all tags.",
    targets: "Elements to lock with no tag in the code.",
    include_docstrings: "A change of a docstring counts as a change of the implementation.",
    categories: "The kinds of deviation to report. Empty: all kinds.",
    reference: "The reference model. Empty: .cdec/reference.xmi.",
  };
  const FIXED = new Set(["id", "type", "severity", "message", "scope"]);
  const optionKeys = $derived(Object.keys(entry).filter((k) => !FIXED.has(k)));

  const isList = (v: unknown): v is string[] => Array.isArray(v);
  const isMap = (v: unknown): v is Record<string, string[]> =>
    typeof v === "object" && v !== null && !Array.isArray(v) && Object.values(v).every(isList);

  let newLayer = $state("");
  function addLayer(key: string) {
    const name = newLayer.trim();
    if (!name) return;
    (entry[key] as Record<string, string[]>)[name] = [];
    newLayer = "";
  }
  const splitNames = (text: string) =>
    text.split(",").map((s) => s.trim()).filter(Boolean);
</script>

<datalist id="rule-form-names">
  {#each names as name (name)}<option value={name}></option>{/each}
</datalist>

<div class="form">
  <label>
    <span class="key">Name of the rule</span>
    <input type="text" bind:value={entry.id} />
    <span class="muted">The report shows the issues under this name. Use words that say the law.</span>
  </label>
  <label>
    <span class="key">When it fails</span>
    <select bind:value={entry.severity}>
      <option value="error">error: the check fails</option>
      <option value="warning">warning: the check reports it</option>
    </select>
  </label>

  {#each optionKeys as key (key)}
    {@const value = entry[key]}
    <div class="field">
      <span class="key"><code>{key}</code></span>
      {#if HINTS[key]}<span class="muted">{HINTS[key]}</span>{/if}
      {#if isList(value)}
        {#each value as _item, i (i)}
          <span class="row">
            <input type="text" list="rule-form-names" aria-label="{key} {i + 1}" bind:value={value[i]} />
            <button onclick={() => value.splice(i, 1)} aria-label="Remove">×</button>
          </span>
        {/each}
        <button class="add" onclick={() => value.push("")}>+ Add</button>
      {:else if isMap(value)}
        {#each Object.keys(value) as layer (layer)}
          <span class="row">
            <code class="layer">{layer}</code>
            <span class="muted">may reference</span>
            <input
              type="text"
              aria-label="Layers that {layer} may reference"
              placeholder="nothing"
              value={value[layer].join(", ")}
              onchange={(e) => (value[layer] = splitNames(e.currentTarget.value))}
            />
            <button onclick={() => delete value[layer]} aria-label="Remove {layer}">×</button>
          </span>
        {/each}
        <span class="row">
          <input type="text" placeholder="new layer" aria-label="New layer" bind:value={newLayer} />
          <button class="add" onclick={() => addLayer(key)}>+ Add a layer</button>
        </span>
      {:else if typeof value === "number"}
        <input type="number" aria-label={key} bind:value={entry[key]} />
      {:else if typeof value === "boolean"}
        <input type="checkbox" aria-label={key} bind:checked={entry[key] as boolean} />
      {:else if typeof value === "string"}
        <input type="text" list="rule-form-names" aria-label={key} bind:value={entry[key]} />
      {:else}
        <span class="muted">This option has parts of its own. Select “Edit as text” to change it.</span>
      {/if}
    </div>
  {/each}

  <label>
    <span class="key">Message</span>
    <textarea
      rows="3"
      placeholder="Why the rule exists, and what a developer does about it."
      value={(entry.message as string) ?? ""}
      oninput={(e) => {
        if (e.currentTarget.value) entry.message = e.currentTarget.value;
        else delete entry.message;
      }}
    ></textarea>
    <span class="muted">A developer reads this when the rule fails. Empty: the standard text.</span>
  </label>
</div>

<style>
  .form {
    display: flex;
    flex-direction: column;
    gap: 0.8rem;
  }
  label,
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .key {
    font-weight: 600;
  }
  .row input[type="text"] {
    flex: 1;
    min-width: 12rem;
  }
  .add {
    align-self: flex-start;
  }
  .layer {
    min-width: 6rem;
  }
  input[type="number"] {
    width: 8rem;
  }
  input[type="checkbox"] {
    align-self: flex-start;
  }
</style>
