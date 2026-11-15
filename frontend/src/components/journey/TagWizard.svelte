<script lang="ts">
  // Put a constraint tag on a class or a method. cdec does not change source
  // code, so the wizard gives the exact line for the language, opens the file,
  // and then reads the code again to confirm that the tag is there.
  import {
    api,
    type ClassGraphNode,
    type JourneyStatus,
    type ProjectInfo,
    type TagSpec,
    type XmiInfo,
  } from "../../lib/api";
  import CopyBlock from "./CopyBlock.svelte";
  import Wizard, { type NextAction } from "./Wizard.svelte";
  import { closeWizard, openWizard } from "./wizards.svelte";

  let {
    project,
    xmi,
    tag: presetTag,
    onParsed,
  }: {
    project: ProjectInfo;
    xmi: XmiInfo;
    tag?: string;
    /** The code was parsed again: the diagram shows the new model. */
    onParsed: (x: XmiInfo) => void;
  } = $props();

  const steps = ["Choose the element", "Choose the tag", "Write it in the code", "Make it binding"];
  let step = $state(0);

  let classes = $state<ClassGraphNode[]>([]);
  let tags = $state<TagSpec[]>([]);
  let supported = $state(true);
  let status = $state<JourneyStatus | null>(null);
  let search = $state("");
  let node = $state<ClassGraphNode | null>(null);
  // "" is the class. Any other value is the name of one of its methods.
  let method = $state("");
  let tagId = $state(presetTag ?? "");
  let values = $state<Record<string, string>>({});
  let snippet = $state<{ tag: string; import: string } | null>(null);
  let notice = $state("");

  api.classGraph(xmi.id).then((g) => (classes = g.nodes.filter((n) => n.kind !== "external")));
  api.tags(project.lang).then((t) => {
    tags = t.tags;
    supported = t.supported;
  });
  const loadStatus = () => api.journey(project.id).then((s) => (status = s));
  void loadStatus();

  const shown = $derived(
    classes
      .filter((c) => c.qualifiedName.toLowerCase().includes(search.trim().toLowerCase()))
      .slice(0, 60),
  );
  const usable = $derived(tags.filter((t) => t.targets.includes(method ? "operation" : "class")));
  const spec = $derived(usable.find((t) => t.id === tagId));

  const PARAM_HELP: Record<string, string> = {
    name: "The name of the layer, for example domain.",
    allow: "Type names that are allowed, with commas between them. Optional.",
    creates: "The type names that only this element may construct, with commas between them.",
    reason: "Why the implementation is frozen. Optional.",
    owner: "Who may approve a change. Optional.",
  };

  // The model spells a tag with `-` or with `_`, by language.
  const same = (a: string, b: string) => a.replace(/_/g, "-") === b.replace(/_/g, "-");

  async function confirmTag() {
    const parsed = await api.parse(project.id);
    const graph = await api.classGraph(parsed.id);
    const now = graph.nodes.find((n) => n.qualifiedName === node!.qualifiedName);
    const rules = method
      ? (now?.operations.find((o) => o.name === method)?.rules ?? [])
      : (now?.rules ?? []);
    if (!rules.some((r) => same(r.name, tagId)))
      throw new Error(
        "cdec does not see the tag yet. Save the file. Make sure that the import line is in " +
          "the same file, and that no empty line is between the tag and the declaration.",
      );
    onParsed(parsed);
    await loadStatus();
  }

  const next = $derived.by<NextAction | null>(() => {
    if (step === 0) return { label: "Next", disabled: !node };
    if (step === 1)
      return {
        label: "Next",
        disabled: !spec || (spec.id === "layer" && !values.name?.trim()),
        run: async () => {
          snippet = await api.tagSnippet(project.lang, tagId, $state.snapshot(values));
        },
      };
    if (step === 2) return { label: "I wrote the tag. Check it", run: confirmTag };
    return null;
  });

  async function copyShim() {
    const done = await api.copyShims(project.id);
    notice = `Wrote ${done.written.join(", ")}. Keep it where your code can import it.`;
    await loadStatus();
  }

  const openFile = () =>
    api
      .nodeDesktopAction(xmi.id, node!.id, "open")
      .catch((e: Error) => (notice = e.message));
</script>

<Wizard title="Put a constraint on a class" {steps} bind:step {next} onclose={() => closeWizard(step === 3)}>
  {#if !supported}
    <p class="error">
      {project.lang} has no constraint tags. Use the rules in <code>.cdec/rules.yaml</code> for
      this language: select Add a rule.
    </p>
  {:else if step === 0}
    <p class="muted">
      A tag is a line in the source code, on a class or on a method. It states one constraint,
      and the diagram shows it as a badge.
    </p>
    <input type="text" class="wide" placeholder="Search the classes" aria-label="Search the classes" bind:value={search} />
    <ul class="pick">
      {#each shown as c (c.id)}
        <li>
          <button class:active={node?.id === c.id} onclick={() => ((node = c), (method = ""))}>
            <strong>{c.name}</strong> <span class="muted">{c.qualifiedName}</span>
          </button>
        </li>
      {/each}
    </ul>
    {#if node}
      <label class="line">
        The tag goes on
        <select bind:value={method}>
          <option value="">the class {node.name}</option>
          {#each [...new Set(node.operations.map((o) => o.name))] as name (name)}
            <option value={name}>the method {name}</option>
          {/each}
        </select>
      </label>
    {/if}
  {:else if step === 1}
    <ul class="pick">
      {#each usable as t (t.id)}
        <li>
          <button class:active={tagId === t.id} onclick={() => ((tagId = t.id), (values = {}))}>
            <strong>{t.id}</strong> <span class="muted">{t.summary}</span>
          </button>
        </li>
      {/each}
    </ul>
    {#if spec}
      {#each spec.params as param (param)}
        <label class="line column">
          <code>{param}</code>
          <input type="text" bind:value={values[param]} />
          <span class="muted">{PARAM_HELP[param] ?? ""}</span>
        </label>
      {/each}
    {/if}
  {:else if step === 2 && snippet && node}
    <p>
      Open <code>{node.location?.file ?? "the file"}</code>{node.location ? `, line ${node.location.startLine}` : ""}.
      <button onclick={openFile}>Open the file in the editor</button>
    </p>
    {#if snippet.import}
      <p><strong>1.</strong> Put this import at the top of the file, if it is not there:</p>
      <CopyBlock text={snippet.import} />
    {/if}
    <p>
      <strong>{snippet.import ? "2." : "1."}</strong> Put this line directly above the declaration
      of {method ? `the method ${method}` : `the class ${node.name}`}:
    </p>
    <CopyBlock text={snippet.tag} />
    {#if status?.shim && !status.shim_present}
      <p class="card">
        The project does not have the shim file <code>{status.shim}</code>. The tags come from
        it and do nothing at run time.
        <button onclick={copyShim}>Copy the shim file into the project</button>
      </p>
    {/if}
    {#if notice}<p class="muted" role="status">{notice}</p>{/if}
    <p class="muted">Save the file, then continue. cdec reads the code again and looks for the tag.</p>
  {:else if step === 3 && spec}
    <p class="ok"><strong>cdec sees the tag {spec.id} on {method || node?.name}.</strong></p>
    {#if status?.rule_types.includes(spec.enforced_by)}
      <p>The rule <code>{spec.enforced_by}</code> is on, so the check enforces the tag.</p>
    {:else}
      <p>
        The tag does nothing until a <code>{spec.enforced_by}</code> rule is on.
        <button
          class="primary"
          onclick={() => {
            closeWizard(true);
            openWizard({ kind: "rule", type: spec.enforced_by });
          }}>Turn on {spec.enforced_by}</button
        >
      </p>
    {/if}
    {#if spec.id === "locked"}
      <p class="muted">
        Then record the digest of the locked body: Rules page, Locks, “Record the new locks”.
      </p>
    {/if}
    {#if !status?.rule_types.includes("frozen-rules")}
      <p class="muted">
        A developer can delete a tag to make a check pass. The rule <code>frozen-rules</code>
        fails when a tag of the reference model disappears.
      </p>
    {/if}
  {/if}
</Wizard>

<style>
  .wide {
    width: 100%;
    box-sizing: border-box;
  }
  .pick {
    list-style: none;
    margin: 0.5rem 0;
    padding: 0;
    max-height: 16rem;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .pick button {
    width: 100%;
    text-align: left;
  }
  .pick button.active {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .line {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin: 0.5rem 0;
  }
  .line.column {
    flex-direction: column;
    align-items: stretch;
    gap: 0.2rem;
  }
</style>
