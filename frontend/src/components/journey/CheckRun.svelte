<script lang="ts" module>
  // The last two runs of each project, and its options. Module state, so a
  // visit to the diagram and back keeps the result and the change since the
  // run before.
  import type { CheckOptions, CheckResult } from "../../lib/api";

  interface Runs {
    options: CheckOptions;
    current: CheckResult | null;
    /** The inputs of `current`. A run with other inputs has no run before. */
    inputs: string;
    previous: CheckResult | null;
  }
  const runs = $state<Record<string, Runs>>({});
</script>

<script lang="ts">
  // `cdec check` in the viewer: the same options, the same report, the same
  // exit code. The result is a list to filter, group and act on: show the
  // class on the diagram, open the file at the line, accept the issue.
  import "./journey.css";
  import { untrack } from "svelte";
  import { api, type ModelChoice, type ProjectInfo, type XmiInfo } from "../../lib/api";
  import {
    changeSince,
    classOf,
    filterRows,
    groupRows,
    issueRows,
    type GroupBy,
    type IssueRow,
    type RowState,
  } from "../../lib/checkRun";
  import { count } from "./text";
  import { projectChanged, wizards } from "./wizards.svelte";

  let {
    project,
    xmi,
    onShowClasses,
  }: {
    project: ProjectInfo;
    /** The parse of the code: the classes of the issues and their nodes. */
    xmi: XmiInfo | null;
    /** Show these classes on the Diagrams page. */
    onShowClasses: (qualifiedNames: string[]) => void;
  } = $props();

  const DEFAULTS: CheckOptions = {
    subject: "code",
    baseline: "reference",
    fail_on: "error",
    rules_files: [],
    bypass_locks: false,
    bypass_reason: "",
  };
  // svelte-ignore state_referenced_locally
  runs[project.id] ??= { options: { ...DEFAULTS }, current: null, inputs: "", previous: null };
  const mine = $derived(runs[project.id]);
  const result = $derived(mine.current);

  let running = $state(false);
  let error = $state("");
  let notice = $state("");
  let models = $state<ModelChoice[]>([]);
  let moreOptions = $state(false);
  let view = $state<"issues" | "text">("issues");

  // What changes the set of issues. The severity to fail on does not.
  const inputsOf = (o: CheckOptions) =>
    JSON.stringify([o.subject, o.baseline, o.rules_files, o.bypass_locks]);

  async function run() {
    const target = mine;
    const options = $state.snapshot(target.options);
    running = true;
    error = "";
    notice = "";
    try {
      const done = await api.runCheck(project.id, options);
      const inputs = inputsOf(options);
      target.previous = target.current && target.inputs === inputs ? target.current : null;
      target.current = done;
      target.inputs = inputs;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      running = false;
    }
  }
  $effect(() => {
    // A visit runs the check. So does a change of the project: an accepted
    // issue, a finished wizard.
    void wizards.done;
    void project.id;
    untrack(() => void run());
  });
  $effect(() => {
    void wizards.done;
    api.models(project.id).then((m) => (models = m)).catch(() => {});
  });

  // ---------- the classes of the code, for the diagram and the editor ----------

  let nodeByClass = $state(new Map<string, { id: string; file: string }>());
  $effect(() => {
    if (!xmi) return;
    api
      .classGraph(xmi.id)
      .then((g) => {
        nodeByClass = new Map(
          g.nodes
            .filter((n) => n.kind !== "external")
            .map((n) => [n.qualifiedName, { id: n.id, file: n.location?.file ?? "" }]),
        );
      })
      .catch(() => {});
  });
  const classOfRow = (r: IssueRow) => classOf(r.violation.qualified_name, nodeByClass.keys());

  async function openInEditor(r: IssueRow) {
    const cls = classOfRow(r);
    const node = cls ? nodeByClass.get(cls) : undefined;
    if (!xmi || !node) return;
    // The line of the issue is right only in the file of its class.
    const loc = r.violation.location;
    const line = loc && sameFile(loc.file, node.file) ? loc.start_line : 0;
    try {
      await api.nodeDesktopAction(xmi.id, node.id, "open", line);
    } catch (e) {
      error = (e as Error).message;
    }
  }
  const sameFile = (a: string, b: string) =>
    a.replaceAll("\\", "/").replace(/^\.\//, "") === b.replaceAll("\\", "/").replace(/^\.\//, "");

  // ---------- filter and group ----------

  let query = $state("");
  let severities = $state(new Set(["error", "warning"]));
  let states = $state(new Set<RowState>(["open", "bypassed"]));
  let groupBy = $state<GroupBy>("rule");
  let expanded = $state<string | null>(null);

  const rows = $derived(result ? issueRows(result, mine.previous) : []);
  const shown = $derived(filterRows(rows, { query, severities, states }));
  const groups = $derived(groupRows(shown, groupBy));
  const delta = $derived(mine.previous && result ? changeSince(mine.previous, result) : null);
  const openRows = $derived(rows.filter((r) => r.state === "open"));
  const quiet = $derived(
    result
      ? result.rules.filter(
          (rule) =>
            rule.severity !== "off" &&
            !rows.some((r) => r.violation.rule_id === rule.id) &&
            !result.report.skipped.some((s) => s.rule_id === rule.id),
        )
      : [],
  );
  const toggle = <T,>(set: Set<T>, item: T): Set<T> => {
    const next = new Set(set);
    if (!next.delete(item)) next.add(item);
    return next;
  };

  // ---------- actions ----------

  async function accept(list: IssueRow[]) {
    const keys = [...new Set(list.filter((r) => r.state === "open" && r.violation.waivable).map((r) => r.violation.key))];
    if (keys.length === 0) return;
    const reason = prompt(
      keys.length === 1
        ? "Why is this issue accepted? rules.yaml records the reason."
        : `Why are these ${keys.length} issues accepted? rules.yaml records the reason.`,
    );
    if (reason === null) return;
    try {
      const done = await api.acceptIssues(project.id, keys, reason);
      notice = `Accepted ${count(done.allowed, "issue")}.`;
      projectChanged(); // runs the check again, and the other pages load again
    } catch (e) {
      error = (e as Error).message;
    }
  }

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      notice = `Copied ${what}.`;
    } catch {
      notice = "";
    }
  }

  function downloadJson() {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result.report, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "cdec-check.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const STATE_LABEL: Record<RowState, string> = {
    open: "open",
    accepted: "accepted",
    bypassed: "lock bypassed",
  };
  const time = (iso: string) => new Date(iso).toLocaleTimeString();
</script>

{#snippet modelOptions(kinds: ModelChoice["kind"][])}
  {#each models.filter((m) => kinds.includes(m.kind)) as m (m.ref)}
    <option value={m.ref}>{m.label}</option>
  {/each}
{/snippet}

<div class="jy runner">
  <div class="card controls">
    <div class="row">
      <button class="primary run" onclick={run} disabled={running}>
        {running ? "Checking…" : "▶ Run cdec check"}
      </button>
      <label class="row">
        <span class="muted">Fail on</span>
        <select bind:value={mine.options.fail_on} title="The severity that makes the exit code 1">
          <option value="error">error</option>
          <option value="warning">warning</option>
          <option value="none">none (report only)</option>
        </select>
      </label>
      {#if result && result.rule_files.length > 1}
        <span class="row files" title="cdec check --rules-file: run only the rules of these files">
          <span class="muted">Rule files</span>
          {#each result.rule_files as name (name)}
            <label class="row">
              <input
                type="checkbox"
                checked={mine.options.rules_files.length === 0 || mine.options.rules_files.includes(name)}
                onchange={() => {
                  const all = mine.options.rules_files.length === 0 ? result!.rule_files : mine.options.rules_files;
                  const next = all.includes(name) ? all.filter((n) => n !== name) : [...all, name];
                  mine.options.rules_files = next.length === result!.rule_files.length ? [] : next;
                }}
              />
              {name}
            </label>
          {/each}
        </span>
      {/if}
      <span class="spacer"></span>
      <button class="link" onclick={() => (moreOptions = !moreOptions)} aria-expanded={moreOptions}>
        {moreOptions ? "Fewer options" : "More options"}
      </button>
    </div>
    {#if moreOptions}
      <div class="row more">
        <label class="row">
          <span class="muted">Check</span>
          <select aria-label="The model that the rules read" bind:value={mine.options.subject}>
            {@render modelOptions(["code", "reference", "history", "file", "git"])}
            {#if models.length === 0}<option value="code">The code of today</option>{/if}
          </select>
        </label>
        <label class="row">
          <span class="muted">against</span>
          <select aria-label="The model that the diff rules compare with" bind:value={mine.options.baseline}>
            {#if !models.some((m) => m.ref === "reference")}
              <option value="reference">The reference model</option>
            {/if}
            {@render modelOptions(["reference", "history", "file", "git"])}
          </select>
        </label>
        <label class="row" title="Report a changed locked body, but do not fail on it">
          <input type="checkbox" bind:checked={mine.options.bypass_locks} />
          Bypass the locks
        </label>
        {#if mine.options.bypass_locks}
          <input
            type="text"
            class="reason"
            placeholder="Why (required)"
            aria-label="Why the locks are bypassed"
            bind:value={mine.options.bypass_reason}
          />
        {/if}
        <button
          onclick={() => {
            mine.options = { ...DEFAULTS };
          }}>Reset</button
        >
      </div>
      <p class="muted">
        The code of today against the reference is the run of <code>cdec check</code> in CI. Another
        model is a run for you to read: the rules that read source code do not run on a model, and an
        issue is accepted only in the run of CI. Add a model file on the Diagrams page.
      </p>
    {/if}
    {#if result?.command}
      <div class="row command">
        <code title="Run in {result.cwd}">{result.command}</code>
        <button class="small" onclick={() => copy(result!.command, "the command")}>Copy</button>
      </div>
    {:else if result}
      <p class="muted">The command line has no run of a model. This run is in the viewer only.</p>
    {/if}
  </div>

  {#if error}<p class="error" role="alert">{error}</p>{/if}
  {#if notice}<p class="ok" role="status">{notice}</p>{/if}

  {#if result}
    {@const s = result.report.summary}
    <div class="banner" class:pass={result.passed} class:fail={!result.passed} class:stale={running}>
      <strong class="verdict">{result.passed ? "✔ Passed" : "✖ Failed"}</strong>
      <span>exit code {result.exit_code}</span>
      <span class="sep">·</span>
      <button class="chip" class:on={severities.has("error")} onclick={() => (severities = toggle(severities, "error"))}>
        {count(s.errors, "error")}
      </button>
      <button class="chip" class:on={severities.has("warning")} onclick={() => (severities = toggle(severities, "warning"))}>
        {count(s.warnings, "warning")}
      </button>
      <button class="chip" class:on={states.has("accepted")} onclick={() => (states = toggle(states, "accepted"))} title="Show the issues that are in the exceptions list">
        {s.suppressed} accepted
      </button>
      {#if result.report.skipped.length > 0}
        <a class="chip" href="#skipped">{result.report.skipped.length} did not run</a>
      {/if}
      <span class="spacer"></span>
      <span class="muted">{(result.duration_ms / 1000).toFixed(1)} s · {time(result.finished)} · fail on {result.fail_on}</span>
    </div>
    {#if s.bypassed}
      <p class="card bypass">
        <strong>The locks were bypassed.</strong> {count(result.report.bypassed.length, "changed lock")} did not
        fail the run. Reason: {s.bypass_reason}. CI can reject this run: <code>summary.bypassed</code> is true.
      </p>
    {/if}
    {#if delta}
      <p class="delta">
        Since the run before:
        {#if delta.fixed.length + delta.added.length === 0}
          no change.
        {:else}
          <span class="good">{delta.fixed.length} no longer open</span>,
          <span class="bad">{delta.added.length} new</span>.
          {#if delta.fixed.length > 0}
            <span class="muted">
              Fixed or accepted: {[...new Set(delta.fixed.map((v) => v.qualified_name))].join(", ")}
            </span>
          {/if}
        {/if}
      </p>
    {/if}

    <div class="row toolbar">
      <div class="switch" role="group" aria-label="How to show the result">
        <button aria-pressed={view === "issues"} class:active={view === "issues"} onclick={() => (view = "issues")}>
          List
        </button>
        <button aria-pressed={view === "text"} class:active={view === "text"} onclick={() => (view = "text")}>
          Text output
        </button>
      </div>
      {#if view === "issues"}
        <input type="text" class="search" placeholder="Filter: key, rule, class, file, message" aria-label="Filter the issues" bind:value={query} />
        <label class="row">
          <span class="muted">Group by</span>
          <select bind:value={groupBy}>
            <option value="rule">rule</option>
            <option value="element">element</option>
            <option value="file">file</option>
          </select>
        </label>
      {/if}
      <span class="spacer"></span>
      {#if view === "issues" && openRows.length > 0}
        <button
          onclick={() =>
            onShowClasses([...new Set(openRows.map(classOfRow).filter((c): c is string => c !== null))])}
          title="The classes with an open issue, on the class diagram"
        >
          Show the classes on the diagram
        </button>
        {@const acceptable = shown.filter((r) => r.state === "open" && r.violation.waivable)}
        {#if result.acceptable && acceptable.length > 0}
          <button onclick={() => accept(acceptable)} title="A lock is not accepted here: see the Rules page, tab Locks">
            Accept the {count(acceptable.length, "shown issue")}…
          </button>
        {/if}
      {/if}
      <button onclick={downloadJson} title="The report of cdec check --format json">Download JSON</button>
    </div>

    {#if view === "text"}
      <div class="text">
        <button class="small copy" onclick={() => copy(result!.human, "the report")}>Copy</button>
        <pre>{result.human}</pre>
      </div>
    {:else}
      {#if shown.length === 0}
        <p class="card muted">
          {rows.length === 0 ? "No issue. Every rule that ran passes." : "No issue matches the filter."}
        </p>
      {/if}
      {#each groups as [name, list] (name)}
        <section class="card group">
          <header class="row">
            <strong>{name}</strong>
            <span class="muted">{count(list.length, "issue")}</span>
            {#if groupBy === "rule"}
              {@const rule = result.rules.find((r) => r.id === name)}
              {#if rule}<span class="muted">· {rule.type} · {rule.severity}</span>{/if}
            {/if}
          </header>
          <ul class="issues">
            {#each list as r, i (i + "|" + r.violation.key)}
              {@const v = r.violation}
              {@const cls = classOfRow(r)}
              {@const lines = v.message.split("\n")}
              <li class={r.state} class:new={r.isNew}>
                <span class="sev {v.severity}" title={v.severity}>{v.severity === "error" ? "✖" : "▲"}</span>
                <div class="body">
                  <div class="row head">
                    <button class="key" title="Copy the key" onclick={() => copy(v.key, v.key)}>{v.key}</button>
                    {#if groupBy !== "element"}<strong>{v.qualified_name}</strong>{/if}
                    {#if groupBy !== "rule"}<span class="muted">{v.rule_id}</span>{/if}
                    {#if v.location && groupBy !== "file"}
                      <span class="muted">{v.location.file}:{v.location.start_line}</span>
                    {:else if v.location}
                      <span class="muted">line {v.location.start_line}</span>
                    {/if}
                    {#if r.isNew}<span class="badge bad">new</span>{/if}
                    {#if r.state !== "open"}<span class="badge">{STATE_LABEL[r.state]}</span>{/if}
                    {#if !v.waivable}<span class="badge warn" title="A lock is accepted on the Rules page, tab Locks">lock</span>{/if}
                  </div>
                  <p class="msg">{lines[0]}</p>
                  {#if lines.length > 1}
                    {#if expanded === v.key + i}
                      <p class="msg more">{lines.slice(1).join("\n")}</p>
                    {/if}
                    <button class="link small" onclick={() => (expanded = expanded === v.key + i ? null : v.key + i)}>
                      {expanded === v.key + i ? "Less" : "More"}
                    </button>
                  {/if}
                </div>
                <div class="actions">
                  {#if cls}
                    <button class="small" onclick={() => onShowClasses([cls])} title="Show {cls} on the class diagram">Diagram</button>
                    <button class="small" onclick={() => openInEditor(r)} title="Open the file in the editor">Editor</button>
                  {/if}
                  {#if r.state === "open" && v.waivable && result.acceptable}
                    <button class="small" onclick={() => accept([r])}>Accept…</button>
                  {/if}
                </div>
              </li>
            {/each}
          </ul>
        </section>
      {/each}

      {#if quiet.length > 0}
        <p class="muted">
          <span class="good">✔</span> No issue from {quiet.map((r) => r.id).join(", ")}.
        </p>
      {/if}
      {#if result.report.skipped.length > 0}
        <section id="skipped" class="card skipped">
          <strong>Did not run</strong>
          <ul>
            {#each result.report.skipped as s (s.rule_id)}
              <li><code>{s.rule_id}</code> {s.reason}</li>
            {/each}
          </ul>
        </section>
      {/if}
    {/if}
  {:else if running}
    <p class="muted">Checking the code…</p>
  {/if}
</div>

<style>
  .runner {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .controls {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .run {
    padding: 0.45rem 1rem;
    font-size: 0.95rem;
  }
  .spacer {
    flex: 1;
  }
  .files {
    gap: 0.6rem;
  }
  .reason {
    min-width: 14rem;
  }
  .more select {
    max-width: 20rem;
  }
  .jy button.link {
    border: 0;
    background: none;
    color: var(--accent);
    padding: 0.1rem 0.2rem;
  }
  .jy button.small {
    padding: 0.1rem 0.45rem;
    font-size: 0.78rem;
  }
  .command code {
    flex: 1;
    min-width: 0;
    overflow-x: auto;
    white-space: nowrap;
    padding: 0.25rem 0.5rem;
  }
  .banner {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem 0.6rem;
    padding: 0.6rem 0.9rem;
    border-radius: 6px;
    border: 1px solid var(--border);
    transition: opacity 0.2s;
  }
  .banner.pass {
    background: #f0fdf4;
    border-color: #86efac;
  }
  .banner.fail {
    background: #fef2f2;
    border-color: #fca5a5;
  }
  .banner.stale {
    opacity: 0.55;
  }
  .verdict {
    font-size: 1.1rem;
  }
  .pass .verdict {
    color: #166534;
  }
  .fail .verdict {
    color: #991b1b;
  }
  .sep {
    color: var(--muted);
  }
  .jy .chip {
    border-radius: 999px;
    padding: 0.05rem 0.6rem;
    font-size: 0.8rem;
    background: var(--surface);
    color: var(--muted);
    text-decoration: line-through;
  }
  .jy .chip.on {
    color: var(--fg);
    text-decoration: none;
    border-color: var(--fg);
  }
  a.chip {
    border: 1px solid var(--border);
    color: var(--fg);
    text-decoration: none;
  }
  .bypass {
    border-color: #f59e0b;
    background: #fffbeb;
  }
  .delta .good,
  .good {
    color: #166534;
    font-weight: 600;
  }
  .delta .bad {
    color: #991b1b;
    font-weight: 600;
  }
  .toolbar {
    gap: 0.6rem;
  }
  .switch {
    display: flex;
  }
  .switch button:first-child {
    border-radius: 4px 0 0 4px;
  }
  .switch button:last-child {
    border-radius: 0 4px 4px 0;
    margin-left: -1px;
  }
  .jy .switch button.active {
    background: var(--accent);
    border-color: var(--accent);
    color: white;
  }
  .search {
    min-width: 18rem;
  }
  .text {
    position: relative;
  }
  .text pre {
    max-height: 60vh;
    overflow: auto;
    white-space: pre-wrap;
    padding-right: 4rem;
  }
  .copy {
    position: absolute;
    top: 0.6rem;
    right: 0.6rem;
  }
  .group header {
    gap: 0.4rem;
    margin-bottom: 0.2rem;
  }
  .issues {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .issues li {
    display: flex;
    gap: 0.6rem;
    align-items: flex-start;
    padding: 0.45rem 0.3rem;
    border-top: 1px solid var(--border);
  }
  .issues li.accepted {
    opacity: 0.6;
  }
  .issues li.new {
    background: #fff7ed;
  }
  .sev {
    width: 1rem;
    text-align: center;
    padding-top: 0.1rem;
  }
  .sev.error {
    color: #dc2626;
  }
  .sev.warning {
    color: #d97706;
  }
  .body {
    flex: 1;
    min-width: 0;
  }
  .head {
    gap: 0.45rem;
  }
  .jy .key {
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 0.78rem;
    padding: 0 0.35rem;
    background: var(--hover);
    border: 0;
  }
  .msg {
    margin: 0.15rem 0 0;
    overflow-wrap: anywhere;
  }
  .msg.more {
    white-space: pre-line;
    color: var(--muted);
  }
  .actions {
    display: flex;
    gap: 0.25rem;
    flex-shrink: 0;
  }
  .skipped ul {
    margin: 0.3rem 0 0;
    padding-left: 1.1rem;
  }
</style>
