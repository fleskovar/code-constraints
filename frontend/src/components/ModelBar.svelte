<script lang="ts">
  // Which model the diagram page shows, and which model it compares with.
  // A model is the code, the target, an entry of the timeline, a git revision
  // or a file. The page that owns the bar loads the diagram.
  import "./journey/journey.css";
  import { api, type ModelChoice, type ProjectInfo } from "../lib/api";
  import { wizards } from "./journey/wizards.svelte";

  let {
    project,
    show,
    against,
    busy = false,
    error = "",
    onselect,
  }: {
    project: ProjectInfo;
    /** A model reference, or `given`: a model that another command opened. */
    show: string;
    against: string;
    busy?: boolean;
    error?: string;
    onselect: (show: string, against: string) => void;
  } = $props();

  const GROUPS: [ModelChoice["kind"], string][] = [
    ["code", "The code"],
    ["reference", "The target"],
    ["history", "The timeline"],
    ["file", "Files"],
    ["git", "Git revisions"],
  ];

  let models = $state<ModelChoice[]>([]);
  let uploadError = $state("");

  const load = () => api.models(project.id).then((m) => (models = m)).catch(() => {});
  $effect(() => {
    void project.id;
    void wizards.done; // a wizard recorded an entry, or changed the reference
    void load();
  });

  async function addFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    uploadError = "";
    try {
      const added = await api.uploadModel(project.id, file);
      await load();
      // A file that the user adds is a model to compare with, most of the time.
      onselect(show === "given" ? "code" : show, added.ref);
    } catch (err) {
      uploadError = (err as Error).message;
    }
  }
</script>

{#snippet options(skip: string)}
  {#each GROUPS as [kind, title] (kind)}
    {@const group = models.filter((m) => m.kind === kind && m.ref !== skip)}
    {#if group.length > 0}
      <optgroup label={title}>
        {#each group as m (m.ref)}<option value={m.ref}>{m.label}</option>{/each}
      </optgroup>
    {/if}
  {/each}
{/snippet}

<div class="jy bar">
  <label class="row">
    <span class="muted">Show</span>
    <select
      aria-label="The model that the diagram shows"
      value={show}
      disabled={busy}
      onchange={(e) => onselect(e.currentTarget.value, against === e.currentTarget.value ? "" : against)}
    >
      {#if show === "given"}<option value="given">The model that was opened</option>{/if}
      {@render options("")}
    </select>
  </label>
  <label class="row">
    <span class="muted">compared with</span>
    <select
      aria-label="The model that the diagram compares with"
      value={against}
      disabled={busy || show === "given"}
      onchange={(e) => onselect(show, e.currentTarget.value)}
    >
      <option value="">nothing</option>
      {@render options(show)}
    </select>
  </label>
  <label class="filebtn" title="A .xmi or .json model file: a snapshot, or a target model">
    Add a model file…
    <input type="file" accept=".xmi,.json" onchange={addFile} />
  </label>
  {#if busy}
    <span class="muted">Loading…</span>
  {:else if against}
    <span class="muted">
      <span class="dot added"></span> only in the shown model
      <span class="dot removed"></span> only in the other model
      <span class="dot changed"></span> changed
    </span>
  {/if}
  {#if error || uploadError}<span class="error" role="alert">{error || uploadError}</span>{/if}
</div>

<style>
  .bar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem 1rem;
    padding: 0.4rem 0.9rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  select {
    max-width: 22rem;
  }
  .filebtn {
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.3rem 0.7rem;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .filebtn:hover,
  .filebtn:focus-within {
    background: var(--hover);
  }
  /* The input stays in the tab order: the label is its visible face. */
  .filebtn input {
    position: absolute;
    width: 1px;
    height: 1px;
    opacity: 0;
  }
  .dot {
    display: inline-block;
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    margin-left: 0.5rem;
  }
  .added {
    background: #22c55e;
  }
  .removed {
    background: #ef4444;
  }
  .changed {
    background: #eab308;
  }
</style>
