<script lang="ts">
  // Add a rule, or change one: choose, fill the form, try it on the code of
  // today, then turn it on. Nothing is written before the last step.
  import {
    api,
    type ProjectInfo,
    type RuleDraft,
    type RuleEntry,
    type RuleGallery,
    type RulePreview,
    type RuleRow,
    type XmiInfo,
  } from "../../lib/api";
  import CopyBlock from "./CopyBlock.svelte";
  import RuleForm from "./RuleForm.svelte";
  import Wizard, { type NextAction } from "./Wizard.svelte";
  import { count } from "./text";
  import { closeWizard } from "./wizards.svelte";

  let {
    project,
    xmi,
    type,
    edit,
  }: {
    project: ProjectInfo;
    xmi: XmiInfo | null;
    /** Start on the form of this rule type. */
    type?: string;
    /** Change this rule. Without it the wizard adds a rule. */
    edit?: RuleRow;
  } = $props();

  // The wizard for a change has no "choose" step.
  const STEPS = ["Choose a rule", "Fill it in", "Try it on the code of today", "Done"];
  const steps = edit ? STEPS.slice(1) : STEPS;
  const offset = edit ? 1 : 0;
  let step = $state(0);
  const stage = $derived(step + offset);

  let gallery = $state<RuleGallery | null>(null);
  let entry = $state<RuleEntry | null>(edit ? structuredClone($state.snapshot(edit.entry)) : null);
  let title = $state(edit ? edit.id : "");
  let summary = $state("");
  let names = $state<string[]>([]);
  let editable = $state(true);
  // "Edit as text": the YAML of the entry, for an option that the form does
  // not show.
  let asText = $state(false);
  let text = $state("");
  let preview = $state<RulePreview | null>(null);
  let acceptExisting = $state(true);
  let result = $state("");

  const draft = (): RuleDraft => (asText ? { yaml: text } : { entry: $state.snapshot(entry!) });

  api.ruleGallery().then((g) => {
    gallery = g;
    const starter = type ? g.starters.find((s) => s.type === type) : undefined;
    if (starter && !entry) choose(starter);
    if (edit) summary = g.starters.find((s) => s.type === edit.type)?.summary ?? "";
  });
  api.journey(project.id).then((s) => (editable = s.rules_editable)).catch(() => {});
  // The names of the project, for the name fields: each class, each package,
  // and each package with everything below it.
  if (xmi)
    api.classGraph(xmi.id).then((g) => {
      const packages = new Set(g.nodes.map((n) => n.package).filter(Boolean));
      names = [
        ...[...packages].flatMap((p) => [`${p}.**`, p]),
        ...g.nodes.filter((n) => n.kind !== "external").map((n) => n.qualifiedName),
      ];
    }).catch(() => {});

  function choose(starter: RuleGallery["starters"][number]) {
    // The gallery is reactive state. A snapshot is a plain copy of the entry.
    entry = $state.snapshot(starter.entry);
    title = starter.title;
    summary = starter.summary;
    asText = false;
    step = 1 - offset;
  }

  async function toggleText() {
    if (asText) entry = (await api.ruleEntry({ yaml: text })).entry;
    else text = (await api.ruleEntry({ entry: $state.snapshot(entry!) })).yaml;
    asText = !asText;
  }

  const next = $derived.by<NextAction | null>(() => {
    if (stage === 0) return { label: "Next", disabled: !entry };
    if (stage === 1)
      return {
        label: "Try it",
        run: async () => {
          preview = await api.previewRule(project.id, draft(), edit?.id ?? "");
        },
      };
    if (stage === 2)
      return {
        label: edit ? "Save the rule" : "Turn on the rule",
        disabled: !editable || !!preview?.skipped,
        run: async () => {
          if (edit) {
            await api.replaceRule(project.id, edit.id, draft());
            result = `The rule is saved. It reports ${count(preview?.open ?? 0, "open issue")}.`;
          } else {
            const accept = acceptExisting && (preview?.open ?? 0) > 0;
            const added = await api.addRule(project.id, draft(), accept);
            result =
              `The rule ${added.id} is on.` +
              (added.accepted
                ? ` ${count(added.accepted, "issue")} of today ${added.accepted === 1 ? "is" : "are"} accepted. The check fails only for new ones.`
                : "");
          }
        },
      };
    return null;
  });
</script>

<Wizard
  title={edit ? `Change the rule ${edit.id}` : "Add a rule"}
  {steps}
  bind:step
  {next}
  onclose={() => closeWizard(stage === 3)}
>
  {#if stage === 0}
    <p class="muted">
      Choose what the rule must protect. The next steps fill it in and show what it reports,
      before anything is written.
    </p>
    {#if gallery}
      {#each gallery.groups as group (group.id)}
        <h3 class="group">{group.title} <span class="muted">— {group.summary}</span></h3>
        <div class="gallery">
          {#each gallery.starters.filter((s) => s.group === group.id) as starter (starter.type)}
            <button class="card starter" onclick={() => choose(starter)}>
              <strong>{starter.title}</strong>
              <span class="muted">{starter.summary}</span>
              <span class="row">
                <code>{starter.type}</code>
                {#if starter.needs_reference}
                  <span class="badge" title="The rule compares the code with .cdec/reference.xmi">
                    uses the reference
                  </span>
                {/if}
              </span>
            </button>
          {/each}
        </div>
      {/each}
    {:else}
      <p class="muted">Loading…</p>
    {/if}
  {:else if stage === 1 && entry}
    <div class="row">
      <h3>{title}</h3>
      <span class="spacer"></span>
      <button onclick={toggleText}>{asText ? "Back to the form" : "Edit as text"}</button>
    </div>
    <p class="muted">{summary}</p>
    {#if asText}
      <textarea rows="14" spellcheck="false" aria-label="Rule entry (YAML)" bind:value={text}></textarea>
      <p class="muted">The entry as it goes into <code>.cdec/rules.yaml</code>.</p>
    {:else}
      <RuleForm bind:entry {names} />
    {/if}
  {:else if stage === 2 && preview}
    {#if preview.skipped}
      <p class="error">The rule cannot run: {preview.skipped}</p>
    {:else}
      <p>
        <strong>This rule reports {count(preview.open, "issue")} in the code of today.</strong>
        {#if preview.accepted > 0}({preview.accepted} more are accepted already.){/if}
      </p>
      {#if !editable}
        <p class="muted">
          The rules of this project are in <code>.cdec/rules/</code>, and cdec does not write
          there. Copy the entry into one of those files:
        </p>
        {#await api.ruleEntry(draft()) then both}<CopyBlock text={both.yaml} />{/await}
      {:else if preview.open > 0 && !edit}
        <label class="choice">
          <input type="radio" bind:group={acceptExisting} value={true} />
          <span>
            <strong>Accept these {preview.open}.</strong> They go into the
            <code>exceptions:</code> list. The check fails only for new ones, and the list is the
            work that is left.
          </span>
        </label>
        <label class="choice">
          <input type="radio" bind:group={acceptExisting} value={false} />
          <span><strong>Let them fail.</strong> The check fails until the code is fixed.</span>
        </label>
      {:else if preview.open > 0}
        <p class="muted">You can accept the open issues on the Rules page after you save.</p>
      {/if}
      {#if preview.issues.length > 0}
        <ul class="issues">
          {#each preview.issues as issue, i (i + "|" + issue.key)}
            <li>
              <code>{issue.key}</code>
              <span>
                <strong>{issue.qualified_name}</strong>
                {#if issue.file}<span class="muted"> · {issue.file}{issue.line ? `:${issue.line}` : ""}</span>{/if}
                <br />{issue.message}
              </span>
            </li>
          {/each}
        </ul>
        {#if preview.open > preview.issues.length}
          <p class="muted">The first {preview.issues.length} of {preview.open}.</p>
        {/if}
      {/if}
    {/if}
  {:else if stage === 3}
    <p class="ok"><strong>{result}</strong></p>
    <p class="muted">
      The rule is in <code>.cdec/rules.yaml</code>. Commit the file. <code>cdec check</code> runs
      the rule from now on.
    </p>
  {/if}
</Wizard>

<style>
  .group {
    margin: 0.9rem 0 0.4rem;
  }
  .group .muted {
    font-weight: 400;
  }
  .gallery {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
    gap: 0.6rem;
  }
  .starter {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    text-align: left;
  }
  .spacer {
    flex: 1;
  }
  .choice {
    display: flex;
    gap: 0.5rem;
    align-items: flex-start;
    margin: 0.4rem 0;
  }
  .issues {
    list-style: none;
    margin: 0.6rem 0 0;
    padding: 0;
  }
  .issues li {
    display: flex;
    gap: 0.6rem;
    padding: 0.35rem 0;
    border-top: 1px solid var(--border);
    font-size: 0.85rem;
    white-space: pre-line;
  }
</style>
