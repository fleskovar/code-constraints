<script lang="ts">
  // Make the code of today the reference model (`cdec check
  // --automatic-exceptions reference`). The wizard shows first what the
  // reference loses and gains, because this step removes the drift that the
  // reference was there to find. An open goal closes.
  import { api, type Change, type JourneyStatus, type ProjectInfo, type XmiInfo } from "../../lib/api";
  import Wizard, { type NextAction } from "./Wizard.svelte";
  import { count } from "./text";
  import { closeWizard } from "./wizards.svelte";

  let {
    project,
    onShow,
  }: {
    project: ProjectInfo;
    /** Show the comparison of the code with the reference on the diagram. */
    onShow: () => void;
  } = $props();

  const steps = ["See what changes", "Name the checkpoint", "Done"];
  let step = $state(0);
  let status = $state<JourneyStatus | null>(null);
  let comparison = $state<XmiInfo | null>(null);
  let changes = $state<Change[] | null>(null);
  let loadError = $state("");
  let title = $state("");
  let note = $state("");
  let result = $state("");

  api.journey(project.id).then((s) => (status = s)).catch(() => {});
  api
    .referenceCompare(project.id)
    .then(async (x) => {
      comparison = x;
      changes = await api.changes(x.id);
    })
    .catch((e: Error) => (loadError = e.message));

  // The code is the old side of the comparison. `added` is in the reference
  // only, `removed` is in the code only.
  const of = (kind: Change["kind"]) => changes?.filter((c) => c.kind === kind) ?? [];

  const next = $derived.by<NextAction | null>(() => {
    if (step === 0) return { label: "Next", disabled: !changes || changes.length === 0 };
    if (step === 1)
      return {
        label: "Make the code the reference",
        disabled: !title.trim(),
        run: async () => {
          const done = await api.referenceSnapshot(project.id, title, note);
          result = `${done.path} now holds the ${count(done.classes, "class", "classes")} of the code.`;
        },
      };
    return null;
  });
</script>

{#snippet names(list: Change[])}
  <ul class="names">
    {#each list.slice(0, 12) as c (c.classId)}<li><code>{c.classQname}</code></li>{/each}
    {#if list.length > 12}<li class="muted">and {list.length - 12} more</li>{/if}
  </ul>
{/snippet}

<Wizard title="Accept the code as the reference" {steps} bind:step {next} onclose={() => closeWizard(step === 2)}>
  {#if step === 0}
    <p class="muted">
      The reference model is what <code>cdec check</code> compares the code with. This wizard
      replaces it with the code as it is now. Do this when a change is complete and approved.
    </p>
    {#if status?.goal}
      <p class="card">
        The goal <strong>{status.goal.title}</strong> is open. It closes: after this step the
        reference is the code, not the goal.
      </p>
    {/if}
    {#if loadError}
      <p class="error">{loadError}</p>
    {:else if !changes}
      <p class="muted">Comparing the code with the reference…</p>
    {:else if changes.length === 0}
      <p class="ok"><strong>The code matches the reference.</strong> There is nothing to accept.</p>
    {:else}
      {#if of("removed").length > 0}
        <p><strong>{count(of("removed").length, "class", "classes")} join the reference.</strong> They are in the code and not in the reference.</p>
        {@render names(of("removed"))}
      {/if}
      {#if of("added").length > 0}
        <p><strong>{count(of("added").length, "class", "classes")} leave the reference.</strong> The reference has them and the code does not.</p>
        {@render names(of("added"))}
      {/if}
      {#if of("changed").length > 0}
        <p><strong>{count(of("changed").length, "class", "classes")} change</strong> to the members that the code has.</p>
        {@render names(of("changed"))}
      {/if}
      <button onclick={() => (onShow(), closeWizard())}>
        Show this on the diagram
      </button>
    {/if}
  {:else if step === 1}
    <p class="muted">The history records this moment as a checkpoint. Give it a name and the reason.</p>
    <label class="column">
      Name
      <input type="text" placeholder="Billing split is complete" bind:value={title} />
    </label>
    <label class="column">
      Why
      <textarea rows="3" placeholder="Who approved the change, and what it completes." bind:value={note}></textarea>
    </label>
  {:else}
    <p class="ok"><strong>The code is the reference now.</strong> {result}</p>
    <p class="muted">Commit <code>.cdec/reference.xmi</code> and <code>.cdec/history/</code> with the change.</p>
  {/if}
</Wizard>

<style>
  .names {
    margin: 0.2rem 0 0.7rem;
    padding-left: 1.2rem;
  }
  .column {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    margin: 0.6rem 0;
  }
</style>
