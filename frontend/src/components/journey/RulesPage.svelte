<script lang="ts">
  // Two pages over one run of the check.
  //
  // `rules`: what the project demands. The rules of rules.yaml, the constraint
  // tags in the code, and the locks.
  // `checks`: `cdec check`, run here (`CheckRun`), and the accepted issues.
  //
  // Each action here is one `cdec` command; the wizards do the longer tasks.
  import "./journey.css";
  import {
    api,
    type ClassGraphRule,
    type LocksOverview,
    type ProjectInfo,
    type RuleRow,
    type RulesOverview,
    type XmiInfo,
  } from "../../lib/api";
  import { ruleParams, rulePresentation } from "../../lib/rules";
  import CheckRun from "./CheckRun.svelte";
  import { count } from "./text";
  import { openWizard, wizards } from "./wizards.svelte";

  let {
    project,
    xmi,
    section,
    onSetUp,
    onGo,
    onShowClasses,
  }: {
    project: ProjectInfo;
    /** The model of the code: the constraint tags come from it. */
    xmi: XmiInfo | null;
    section: "rules" | "checks";
    onSetUp: () => void;
    onGo: (page: "rules" | "checks") => void;
    /** Show these classes on the Diagrams page. */
    onShowClasses: (qualifiedNames: string[]) => void;
  } = $props();

  type Tab = "rules" | "tags" | "locks" | "report" | "accepted";
  let tab = $state<Tab>(section === "rules" ? "rules" : "report");
  let overview = $state<RulesOverview | null>(null);
  let locks = $state<LocksOverview | null>(null);
  let loading = $state(false);
  let error = $state("");
  let notice = $state("");
  let expanded = $state<string | null>(null);

  async function load() {
    loading = true;
    error = "";
    try {
      [overview, locks] = await Promise.all([
        api.rules(project.id),
        api.locks(project.id).catch(() => null),
      ]);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
  $effect(() => {
    // Load again when the project or a finished wizard changes.
    void project.id;
    void wizards.done;
    void load();
  });

  const stale = $derived(overview?.exceptions.filter((e) => e.stale) ?? []);
  const newLocks = $derived(locks?.targets.filter((t) => t.state === "new") ?? []);
  const lockProblems = $derived(
    locks?.targets.filter((t) => t.state !== "ok" && t.state !== "new") ?? [],
  );
  // ---------- the constraint tags in the code ----------

  interface Tagged {
    element: string;
    file: string;
    rule: ClassGraphRule;
  }
  let tagged = $state<Tagged[]>([]);
  $effect(() => {
    if (section !== "rules" || !xmi) return;
    api
      .classGraph(xmi.id)
      .then((g) => {
        tagged = g.nodes.flatMap((n) => {
          const file = n.location ? `${n.location.file}:${n.location.startLine}` : "";
          return [
            ...n.rules.map((rule) => ({ element: n.qualifiedName, file, rule })),
            ...n.operations.flatMap((op) =>
              op.rules.map((rule) => ({ element: `${n.qualifiedName}.${op.name}`, file, rule })),
            ),
          ];
        });
      })
      .catch(() => (tagged = []));
  });
  const tagNames = $derived([...new Set(tagged.map((t) => t.rule.name))].sort());

  // ---------- actions ----------

  // Run one change, then read everything again. An error stays on the page.
  async function change(action: () => Promise<string>) {
    error = "";
    notice = "";
    try {
      notice = await action();
      await load();
    } catch (e) {
      error = (e as Error).message;
    }
  }

  const setSeverity = (ruleId: string, severity: string) =>
    change(async () => {
      await api.setRuleSeverity(project.id, ruleId, severity);
      return `${ruleId}: severity is ${severity}.`;
    });

  function removeRule(rule: RuleRow) {
    if (!confirm(`Remove the rule ${rule.id} from rules.yaml? To stop it for a time, set it to "off".`))
      return;
    void change(async () => {
      await api.removeRule(project.id, rule.id);
      return `The rule ${rule.id} is removed.`;
    });
  }

  const withdraw = (key: string) =>
    change(async () => {
      await api.removeExceptions(project.id, [key]);
      return `${key} is withdrawn. The issue fails the check again.`;
    });

  const prune = () =>
    change(async () => {
      const done = await api.pruneExceptions(project.id);
      return `Removed ${count(done.removed, "stale exception")}.`;
    });

  const recordLocks = () =>
    change(async () => (await api.updateLocks(project.id, false, [])).lines.join(" ") || "Recorded.");

  function acceptLockChange(target: string) {
    if (
      !confirm(
        `Accept the change to the frozen implementation of ${target}?\n\n` +
          "This is the privileged step of the lock: it records the new body as the approved one. " +
          "The change shows in the locks: section of rules.yaml.",
      )
    )
      return;
    void change(async () => (await api.updateLocks(project.id, true, [target])).lines.join(" "));
  }

  const LOCK_STATE: Record<string, string> = {
    ok: "frozen",
    new: "not recorded yet",
    changed: "the body changed",
    missing: "the element is gone",
    removed: "the tag was removed",
    unlocked: "no digest is recorded",
    "algo-mismatch": "recorded by another cdec version",
  };
</script>

{#snippet tabButton(id: Tab, label: string, alert = false)}
  <button role="tab" aria-selected={tab === id} class:active={tab === id} onclick={() => (tab = id)}>
    {label}
    {#if alert}<span class="badge warn">!</span>{/if}
  </button>
{/snippet}

<div class="jy rules">
  <div class="row head">
    {#if section === "rules"}
      <h2>Constraints and rules</h2>
      <button onclick={load} disabled={loading} title="Read the code and the rules again">
        {loading ? "Checking…" : "Check again"}
      </button>
      <span class="spacer"></span>
      <button onclick={() => openWizard({ kind: "tag" })}>Put a constraint on a class…</button>
      <button class="primary" onclick={() => openWizard({ kind: "rule" })}>Add a rule…</button>
    {:else}
      <h2>Checks</h2>
    {/if}
  </div>

  {#if section === "rules"}
    <p class="muted">
      What this project demands of its code. A <strong>rule</strong> is an entry of
      <code>.cdec/rules.yaml</code>. A <strong>constraint tag</strong> is a mark on a class or a
      method in the source code. A <strong>lock</strong> freezes an implementation. The
      <button class="inline" onclick={() => onGo("checks")}>Checks</button> page shows what they
      report.
    </p>
  {:else}
    <p class="muted">
      Run the check of CI here, and act on each issue: show its class on the diagram, open the
      file at the line, or accept the issue with a reason.
    </p>
  {/if}

  {#if notice}<p class="ok" role="status">{notice}</p>{/if}
  {#if error}
    <p class="error" role="alert">{error}</p>
    {#if error.includes("no .cdec/rules.yaml")}
      <button class="primary" onclick={onSetUp}>Set the project up</button>
    {/if}
  {/if}

  {#if overview}
    <div class="tabs" role="tablist">
      {#if section === "rules"}
        {@render tabButton("rules", `Rules (${overview.rules.length})`)}
        {@render tabButton("tags", `Constraints in the code (${tagged.length})`)}
        {@render tabButton(
          "locks",
          `Locks (${locks?.targets.length ?? 0})`,
          lockProblems.length + newLocks.length > 0,
        )}
      {:else}
        {@render tabButton("report", "Run cdec check")}
        {@render tabButton("accepted", `Accepted issues (${overview.exceptions.length})`)}
      {/if}
    </div>

    {#if tab === "rules"}
      {#if overview.rules.length === 0}
        <p class="card muted">
          No rule is on. Select <strong>Add a rule</strong>. The wizard shows what a rule reports
          before it turns the rule on.
        </p>
      {/if}
      {#if !overview.editable}
        <p class="muted">
          The rules of this project are in <code>.cdec/rules/</code>, and cdec does not write
          there. Change a rule in its file.
        </p>
      {/if}
      <ul class="list">
        {#each overview.rules as rule (rule.id)}
          <li class="card">
            <div class="row">
              <button
                class="toggle"
                aria-expanded={expanded === rule.id}
                onclick={() => (expanded = expanded === rule.id ? null : rule.id)}
              >
                {expanded === rule.id ? "▾" : "▸"} <strong>{rule.id}</strong>
              </button>
              <span class="muted">{rule.type}</span>
              <span class="spacer"></span>
              {#if rule.skipped}
                <span class="badge warn" title={rule.skipped}>did not run</span>
              {:else if rule.severity !== "off"}
                <button
                  class="badge link"
                  class:bad={rule.open > 0}
                  class:good={rule.open === 0}
                  title="Open the report of the check"
                  onclick={() => onGo("checks")}>{rule.open} open</button
                >
                {#if rule.accepted > 0}<span class="badge">{rule.accepted} accepted</span>{/if}
              {/if}
              <select
                aria-label="Severity of {rule.id}"
                value={rule.severity}
                disabled={!overview.editable}
                title="error fails the check. warning reports only. off does not run."
                onchange={(e) => setSeverity(rule.id, e.currentTarget.value)}
              >
                <option value="error">error</option>
                <option value="warning">warning</option>
                <option value="off">off</option>
              </select>
            </div>
            {#if rule.skipped}<p class="muted">Did not run: {rule.skipped}</p>{/if}
            {#if expanded === rule.id}
              <pre>{rule.yaml}</pre>
              {#if overview.editable}
                <div class="row">
                  <button onclick={() => openWizard({ kind: "edit-rule", rule })}>Change…</button>
                  <button onclick={() => removeRule(rule)}>Remove</button>
                </div>
              {/if}
            {/if}
          </li>
        {/each}
      </ul>
      <p class="muted">
        A change to a rule on this page is an entry of the timeline. The timeline shows which
        rules were on at each step.
      </p>
    {:else if tab === "tags"}
      <p class="muted">
        A constraint tag is in the source code, on the class or the method that it protects. A
        tag is checked by a rule: <code>tag-conformance</code> for the body of the code,
        <code>layer-dependencies</code> for the layers, <code>frozen-rules</code> for a tag that
        somebody removes. cdec does not change source code: the wizard gives the line to paste.
      </p>
      {#if tagged.length === 0}
        <p class="card muted">
          No class and no method has a constraint tag. Select
          <strong>Put a constraint on a class</strong>.
        </p>
      {/if}
      {#each tagNames as name (name)}
        {@const look = rulePresentation(name)}
        {@const mine = tagged.filter((t) => t.rule.name === name)}
        <div class="card tag-group">
          <div class="row">
            <span class="tag" style:background={look.color}>{look.label}</span>
            <strong>{name}</strong>
            <span class="muted">{look.summary}</span>
            <span class="spacer"></span>
            <span class="muted">{count(mine.length, "element")}</span>
          </div>
          <ul class="issues plain">
            {#each mine as t, i (i + "|" + t.element)}
              <li>
                <span class="where">
                  <strong>{t.element}</strong>
                  {#if ruleParams(t.rule)}<code>{ruleParams(t.rule)}</code>{/if}
                  {#if t.file}<span class="muted"> · {t.file}</span>{/if}
                </span>
              </li>
            {/each}
          </ul>
        </div>
      {/each}
    {:else if tab === "locks" && locks}
      <p class="muted">
        A lock freezes the implementation of a class or a function. The check fails when the
        body changes at all. A lock is a <code>locked</code> tag in the code, plus a digest in
        <code>rules.yaml</code>.
      </p>
      {#if !locks.supported}
        <p class="card">{locks.reason}</p>
      {:else}
        <div class="row">
          <button onclick={() => openWizard({ kind: "tag", tag: "locked" })}>Lock an element…</button>
          {#if !locks.rule}
            <button class="primary" onclick={() => openWizard({ kind: "rule", type: "implementation-locks" })}>
              Turn on the lock rule…
            </button>
          {:else if newLocks.length > 0}
            <button class="primary" onclick={recordLocks}>
              Record the {count(newLocks.length, "new lock")}
            </button>
          {/if}
        </div>
        {#if !locks.rule}
          <p class="card muted">
            No <code>implementation-locks</code> rule is on, so the check does not look at the
            locks.
          </p>
        {/if}
        {#if locks.targets.length === 0}
          <p class="card muted">Nothing is locked.</p>
        {/if}
        <ul class="issues plain">
          {#each locks.targets as lock (lock.target)}
            <li>
              <span class="badge" class:good={lock.state === "ok"} class:warn={lock.state === "new"} class:bad={lock.state !== "ok" && lock.state !== "new"}>
                {LOCK_STATE[lock.state] ?? lock.state}
              </span>
              <span class="where">
                <strong>{lock.target}</strong>
                <span class="muted"> · {lock.kind}{lock.file ? ` · ${lock.file}${lock.line ? `:${lock.line}` : ""}` : ""}</span>
                {#if lock.reason}<br />{lock.reason}{/if}
                {#if lock.message}<br /><span class="muted">{lock.message}</span>{/if}
                {#if lock.locked_at}
                  <br /><span class="muted">Recorded {lock.locked_at.slice(0, 10)}{lock.locked_by ? ` by ${lock.locked_by}` : ""}</span>
                {/if}
              </span>
              {#if locks.rule && lock.state !== "ok" && lock.state !== "new"}
                <button onclick={() => acceptLockChange(lock.target)}>Accept this change…</button>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    {:else if tab === "report"}
      <CheckRun {project} {xmi} {onShowClasses} />
    {:else if tab === "accepted"}
      <p class="muted">
        Each accepted issue is one entry of the <code>exceptions:</code> list. A shorter list is
        progress. A stale entry covers an issue that does not occur any more: remove it, or it
        accepts the next issue of the same kind.
      </p>
      {#if stale.length > 0}
        <button onclick={prune}>Remove the {count(stale.length, "stale entry", "stale entries")}</button>
      {/if}
      {#if overview.exceptions.length === 0}
        <p class="card muted">No issue is accepted.</p>
      {/if}
      <ul class="issues plain">
        {#each overview.exceptions as item (item.key)}
          <li>
            <code>{item.key}</code>
            <span class="where">
              <strong>{item.qualified_name}</strong>
              <span class="muted"> · {item.rule}{item.detail ? ` · ${item.detail}` : ""}</span>
              {#if item.stale}<span class="badge warn">stale</span>{/if}
              <br />{item.reason || "No reason was given."}
              <span class="muted">
                {item.added_by ? ` · ${item.added_by}` : ""}{item.added ? ` · ${item.added.slice(0, 10)}` : ""}
              </span>
            </span>
            <button onclick={() => withdraw(item.key)}>Withdraw</button>
          </li>
        {/each}
      </ul>
    {/if}
  {:else if loading}
    <p class="muted">Checking the code…</p>
  {/if}
</div>

<style>
  .rules {
    max-width: 62rem;
    margin: 0 auto;
    padding: 1.25rem;
  }
  .head h2 {
    margin: 0;
  }
  .spacer {
    flex: 1;
  }
  .jy button.inline {
    border: 0;
    background: none;
    padding: 0;
    color: var(--accent);
    font: inherit;
    text-decoration: underline;
  }
  .jy button.badge.link {
    border: 0;
    cursor: pointer;
  }
  .tabs {
    display: flex;
    gap: 0.25rem;
    border-bottom: 1px solid var(--border);
    margin: 0.75rem 0;
  }
  .tabs button {
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
  }
  .tabs button.active {
    border-bottom-color: var(--accent);
    font-weight: 600;
  }
  .list {
    list-style: none;
    margin: 0.75rem 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .toggle {
    border: none;
    background: transparent;
    padding: 0.1rem 0.2rem;
    font-size: 0.9rem;
  }
  .tag-group {
    margin-bottom: 0.5rem;
  }
  .tag {
    color: white;
    border-radius: 3px;
    padding: 0 0.4rem;
    font-size: 0.75rem;
  }
  .issues {
    list-style: none;
    margin: 0.5rem 0 0;
    padding: 0;
    max-height: 22rem;
    overflow-y: auto;
  }
  .issues.plain {
    max-height: none;
  }
  .issues li {
    display: flex;
    gap: 0.6rem;
    align-items: flex-start;
    padding: 0.4rem 0;
    border-top: 1px solid var(--border);
    font-size: 0.85rem;
  }
  .where {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
    white-space: pre-line;
  }
</style>
