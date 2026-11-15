<script lang="ts">
  // The timeline of the project: where it started, each goal, each checkpoint
  // and each rule change, in order, and the code of today at the end. One
  // step is one frame on the same canvas as every other diagram. Node
  // positions have stable ids, so a class stays in its place from frame to
  // frame.
  import "./journey.css";
  import { onDestroy } from "svelte";
  import { api, type HistoryEntry, type ProjectInfo, type XmiInfo } from "../../lib/api";
  import DiagramViewer from "../DiagramViewer.svelte";
  import { count } from "./text";
  import { openWizard, wizards } from "./wizards.svelte";

  let {
    project,
    onSetUp,
    onShow,
  }: {
    project: ProjectInfo;
    onSetUp: () => void;
    /** Open two models on the Diagrams page. */
    onShow: (show: string, against: string) => void;
  } = $props();

  // What a frame compares its entry with.
  type Compare = "change" | "goal" | "none";
  const FRAME_MS = 4000;

  let entries = $state<HistoryEntry[]>([]);
  let loaded = $state(false);
  let index = $state(0);
  let compare = $state<Compare>("change");
  let frame = $state<XmiInfo | null>(null);
  let error = $state("");
  let playing = $state(false);
  // "Now": the code of today against the reference. It is not an entry.
  let now = $state(false);

  const current = $derived<HistoryEntry | undefined>(now ? undefined : entries[index]);
  // The state of the code before this entry. A goal is a plan, not a state.
  const before = $derived(
    entries.slice(0, index).reverse().find((e) => e.kind !== "goal"),
  );
  const goal = $derived(entries.find((e) => e.id === current?.goal));
  const previous = $derived(index > 0 ? entries[index - 1] : undefined);

  async function load(selectLast = true) {
    try {
      entries = await api.history(project.id);
      if (selectLast) index = Math.max(0, entries.length - 1);
      error = "";
    } catch (e) {
      error = (e as Error).message;
    }
    loaded = true;
  }
  $effect(() => {
    void project.id;
    void wizards.done; // a wizard recorded an entry
    void load();
  });

  // Build the frame of the selected entry, or of the code of today.
  $effect(() => {
    if (now) {
      let old = false;
      api
        .referenceCompare(project.id)
        .then((x) => !old && ((frame = x), (error = "")))
        .catch((e: Error) => !old && (error = e.message));
      return () => (old = true);
    }
    const entry = current;
    if (!entry) return;
    // "goal": the entry is the code and the goal is the target, so green is
    // what the code must still build.
    const [shown, against] =
      compare === "goal" && goal
        ? [goal.id, entry.id]
        : compare === "change" && before
          ? [entry.id, before.id]
          : [entry.id, ""];
    let stale = false;
    api
      .historyFrame(project.id, shown, against)
      .then((x) => {
        if (!stale) {
          frame = x;
          error = "";
        }
      })
      .catch((e: Error) => !stale && (error = e.message));
    return () => (stale = true);
  });

  // ---------- move along the timeline ----------

  let timer: ReturnType<typeof setInterval> | undefined;
  function stop() {
    clearInterval(timer);
    playing = false;
  }
  function play() {
    if (entries.length < 2) return;
    if (now || index >= entries.length - 1) index = 0;
    now = false;
    playing = true;
    timer = setInterval(() => {
      if (index >= entries.length - 1) stop();
      else index += 1;
    }, FRAME_MS);
  }
  // The steps are the entries, then the code of today.
  const position = $derived(now ? entries.length : index);
  function goTo(step: number) {
    stop();
    const last = entries.length; // the index of "now"
    const to = Math.min(last, Math.max(0, step));
    now = to === last;
    if (!now) index = to;
  }
  onDestroy(stop);

  function onTrackKey(e: KeyboardEvent) {
    const by = { ArrowLeft: -1, ArrowRight: 1 }[e.key];
    if (by === undefined) return;
    e.preventDefault();
    goTo(position + by);
  }
  // Keep the selected step in view on a long timeline.
  let track = $state<HTMLElement>();
  $effect(() => {
    void position;
    track?.querySelector('[aria-current="step"]')?.scrollIntoView({ inline: "nearest", block: "nearest" });
  });

  // ---------- record a checkpoint ----------

  let recordOpen = $state(false);
  let title = $state("");
  let note = $state("");
  let recording = $state(false);

  async function record() {
    recording = true;
    error = "";
    try {
      await api.recordCheckpoint(project.id, title, note);
      title = "";
      note = "";
      recordOpen = false;
      now = false;
      await load();
    } catch (e) {
      error = (e as Error).message;
    } finally {
      recording = false;
    }
  }

  // ---------- what one entry says ----------

  const KIND_LABEL: Record<HistoryEntry["kind"], string> = {
    start: "Start",
    goal: "Goal",
    checkpoint: "Checkpoint",
    rules: "Rules",
  };

  function distanceText(d: Record<string, number>): string {
    const total = (d.to_build ?? 0) + (d.to_change ?? 0) + (d.unplanned ?? 0);
    if (total === 0) return "The code matches the goal.";
    return `To the goal: ${d.to_build ?? 0} to build, ${d.to_change ?? 0} to change, ${d.unplanned ?? 0} not in the plan.`;
  }

  // The rules that came and went since the entry before.
  const ruleChanges = $derived.by(() => {
    if (!current || !previous) return [];
    const was = new Map(previous.rules.map((r) => [r.id, r.severity]));
    const has = new Map(current.rules.map((r) => [r.id, r.severity]));
    const out: string[] = [];
    for (const [id, severity] of has) {
      if (!was.has(id)) out.push(`+ rule ${id} (${severity})`);
      else if (was.get(id) !== severity) out.push(`~ rule ${id}: ${was.get(id)} → ${severity}`);
    }
    for (const id of was.keys()) if (!has.has(id)) out.push(`− rule ${id}`);
    const exceptions = (current.stats.exceptions ?? 0) - (previous.stats.exceptions ?? 0);
    if (exceptions !== 0)
      out.push(`${exceptions > 0 ? "+" : "−"} ${count(Math.abs(exceptions), "accepted issue")}`);
    return out;
  });
</script>

<div class="jy history">
  <div class="strip">
    <div class="row controls">
      <h2>Timeline</h2>
      <button onclick={() => goTo(position - 1)} disabled={position === 0} aria-label="Previous step">◀</button>
      {#if playing}
        <button class="primary" onclick={stop}>Pause</button>
      {:else}
        <button class="primary" onclick={play} disabled={entries.length < 2} title="Show each step in order">▶ Play</button>
      {/if}
      <button
        onclick={() => goTo(position + 1)}
        disabled={position >= entries.length}
        aria-label="Next step">▶</button
      >
      <span class="muted">{entries.length ? `${position + 1} / ${entries.length + 1}` : ""}</span>
      <label class="row">
        <span class="muted">Colours show</span>
        <select bind:value={compare} disabled={now}>
          <option value="change">the change since the state before</option>
          <option value="goal" disabled={!goal}>what is left to reach the goal</option>
          <option value="none">nothing: the model only</option>
        </select>
      </label>
      <span class="spacer"></span>
      {#if entries.length > 0}
        <button onclick={() => (recordOpen = !recordOpen)} aria-expanded={recordOpen}>
          Record a checkpoint…
        </button>
      {/if}
    </div>

    {#if recordOpen}
      <form
        class="record row"
        onsubmit={(e) => {
          e.preventDefault();
          void record();
        }}
      >
        <!-- svelte-ignore a11y_autofocus -->
        <input type="text" placeholder="What changed" aria-label="Title" bind:value={title} autofocus />
        <input class="why" type="text" placeholder="Why (optional)" aria-label="Note" bind:value={note} />
        <button class="primary" type="submit" disabled={recording || !title.trim()}>
          {recording ? "Recording…" : "Record"}
        </button>
        <span class="muted">The model of the code as it is now. It changes no rule.</span>
      </form>
    {/if}

    {#if loaded && entries.length === 0}
      <p class="muted">
        This project has no timeline yet. The setup of the project starts one.
        <button class="primary" onclick={onSetUp}>Set the project up</button>
      </p>
    {:else}
      <!-- One list with arrow keys: the steps are a row, like the tabs of a tab list. -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <ol class="track" bind:this={track} onkeydown={onTrackKey} aria-label="The steps of the project, oldest first">
        {#each entries as entry, i (entry.id)}
          <li>
            <button
              class="step {entry.kind}"
              class:active={!now && i === index}
              aria-current={!now && i === index ? "step" : undefined}
              onclick={() => goTo(i)}
            >
              <span class="dot" aria-hidden="true"></span>
              <span class="row">
                <span class="kind">{KIND_LABEL[entry.kind]}</span>
                <span class="muted">{entry.created.slice(0, 10)}</span>
              </span>
              <strong>{entry.title}</strong>
              <span class="muted">
                {count(entry.stats.classes ?? 0, "class", "classes")} ·
                {count(entry.rules.filter((r) => r.severity !== "off").length, "rule")} ·
                {entry.stats.exceptions ?? 0} accepted
              </span>
            </button>
          </li>
        {/each}
        {#if entries.length > 0}
          <li>
            <button
              class="step now"
              class:active={now}
              aria-current={now ? "step" : undefined}
              onclick={() => goTo(entries.length)}
            >
              <span class="dot" aria-hidden="true"></span>
              <span class="kind">Now</span>
              <strong>The code of today</strong>
              <span class="muted">Against the reference. Not recorded.</span>
            </button>
          </li>
        {/if}
      </ol>
    {/if}
  </div>

  <section class="stage">
    {#if error}<p class="error pad" role="alert">{error}</p>{/if}
    {#if now}
      <header class="caption">
        <div class="row">
          <h3>The code of today</h3>
          <span class="muted">against the reference model</span>
          <span class="spacer"></span>
          <button onclick={() => onShow("reference", "code")}>Open on the Diagrams page</button>
          <button onclick={() => openWizard({ kind: "accept-code" })}>
            Accept the code as the reference…
          </button>
        </div>
        <p class="muted">
          Green: the reference has it and the code must still build it. Red: the code has it and
          the reference does not.
        </p>
      </header>
    {:else if current}
      <header class="caption">
        <div class="row">
          <h3>{current.title}</h3>
          <span class="muted">
            {current.created.replace("T", " ").slice(0, 16)} UTC{current.author ? ` · ${current.author}` : ""}{current.commit
              ? ` · ${current.commit}`
              : ""}{current.reference ? " · became the reference" : ""}
          </span>
          <span class="spacer"></span>
          <button onclick={() => onShow(`history:${current.id}`, "")} title="Show this model alone, edit it, or compare it with any model">
            Open on the Diagrams page
          </button>
          <button onclick={() => onShow("code", `history:${current.id}`)} title="What the code of today has and this step does not">
            Compare with the code of today
          </button>
        </div>
        {#if current.note}<p class="note">{current.note}</p>{/if}
        {#if current.distance && Object.keys(current.distance).length > 0}
          <p><span class="badge goal">{goal?.title ?? "Goal"}</span> {distanceText(current.distance)}</p>
        {/if}
        <p class="row rules-then">
          <span class="muted">Rules at this step:</span>
          {#each current.rules as rule (rule.id)}
            <span class="badge" class:off={rule.severity === "off"} title="{rule.type} · {rule.severity}">
              {rule.id}{rule.severity === "error" ? "" : ` (${rule.severity})`}
            </span>
          {:else}
            <span class="muted">none</span>
          {/each}
          {#if ruleChanges.length > 0}
            <span class="muted">· since the step before: {ruleChanges.join("  ·  ")}</span>
          {/if}
        </p>
      </header>
    {/if}
    {#if frame}
      <div class="viewer"><DiagramViewer xmi={frame} /></div>
    {/if}
  </section>
</div>

<style>
  .history {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .strip {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0.6rem 0.9rem 0.3rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .controls h2 {
    margin: 0 0.5rem 0 0;
  }
  .spacer {
    flex: 1;
  }
  .record .why {
    flex: 1;
    min-width: 12rem;
  }
  /* The steps in a row, on one line that joins the dots. */
  .track {
    list-style: none;
    margin: 0;
    padding: 0.2rem 0 0.5rem;
    display: flex;
    gap: 0.5rem;
    overflow-x: auto;
    background: linear-gradient(var(--border), var(--border)) left 0.9rem / 100% 2px no-repeat;
  }
  .track li {
    flex: 0 0 auto;
  }
  .jy .step {
    width: 13rem;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    align-items: flex-start;
    text-align: left;
    border-color: transparent;
    background: transparent;
    padding: 0.25rem 0.5rem;
  }
  .step strong {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 100%;
  }
  .step .row {
    flex-wrap: nowrap;
    gap: 0.35rem;
  }
  /* The line of the track stays visible behind the selected step. */
  .jy .step.active {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 7%, transparent);
  }
  .dot {
    width: 0.8rem;
    height: 0.8rem;
    border-radius: 50%;
    background: var(--muted);
    border: 2px solid var(--surface);
    box-shadow: 0 0 0 1px var(--muted);
    flex-shrink: 0;
  }
  .kind {
    font-size: 0.75rem;
    font-weight: 600;
  }
  .goal .dot {
    background: #2563eb;
    box-shadow: 0 0 0 1px #2563eb;
  }
  .checkpoint .dot {
    background: #16a34a;
    box-shadow: 0 0 0 1px #16a34a;
  }
  .rules .dot {
    background: #d97706;
    box-shadow: 0 0 0 1px #d97706;
    border-radius: 2px;
  }
  .now .dot {
    background: var(--surface);
  }
  .stage {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
    min-height: 0;
  }
  .caption {
    padding: 0.5rem 0.9rem;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  .note {
    white-space: pre-line;
  }
  .rules-then {
    gap: 0.3rem;
  }
  .badge.off {
    text-decoration: line-through;
    opacity: 0.6;
  }
  .pad {
    padding: 0 0.9rem;
  }
  .viewer {
    flex: 1;
    min-height: 0;
  }
</style>
