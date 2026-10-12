<script lang="ts">
  import { onMount } from "svelte";
  import {
    api,
    type GitInfo,
    type Lang,
    type ProjectInfo,
    type RecentPath,
    type WorkspaceView,
    type XmiInfo,
  } from "../lib/api";

  export type HomeIntent =
    | { kind: "parse"; project: ProjectInfo; xmi: XmiInfo; view?: WorkspaceView }
    | { kind: "diff_custom"; project: ProjectInfo }
    | { kind: "quick_diff"; project: ProjectInfo; xmi: XmiInfo }
    | { kind: "xmi_diff"; project: ProjectInfo; xmi: XmiInfo }
    | { kind: "editor" };

  let { onLaunch }: { onLaunch: (intent: HomeIntent) => void } = $props();

  const LANG_LABELS: Record<Lang, string> = {
    python: "Python",
    csharp: "C#",
    typescript: "TypeScript",
    svelte: "Svelte 5",
    odin: "Odin",
    lua: "Lua",
    julia: "Julia",
  };

  // What a view row needs to know about its path.
  type PathRef = Pick<RecentPath, "id" | "path" | "lang">;

  let path = $state("");
  let lang = $state<Lang>("python");
  let busyAction = $state<
    "parse" | "quickdiff" | "diffcustom" | "xmidiff" | "vsxmi" | null
  >(null);
  let error = $state("");
  let xmiOld = $state<File | null>(null);
  let xmiNew = $state<File | null>(null);
  let referenceXmi = $state<File | null>(null);
  let gitInfo = $state<GitInfo | null>(null);
  let gitLookupInflight = $state(false);

  // ---------- recent paths and their views (the server keeps them in .cdec_cache) ----------

  let recents = $state<RecentPath[]>([]);
  let recentsLoaded = $state(false);
  let recentsError = $state("");
  // The path + language in the form, once the server knows it as a project.
  let current = $state<ProjectInfo | null>(null);
  const currentViews = $derived(recents.find((r) => r.id === current?.id)?.views ?? []);

  async function loadRecents() {
    try {
      recents = await api.workspace();
      recentsError = "";
    } catch (e) {
      // The list is a convenience. The form below works without it.
      recentsError = (e as Error).message;
    }
    recentsLoaded = true;
  }
  onMount(loadRecents);

  async function forget(id: string) {
    await api.forgetRecent(id).catch(() => {});
    await loadRecents();
  }

  // ---------- language suggestion ----------

  // Suggest the language when the path changes. A choice the user makes in
  // the dropdown stays until the path changes again.
  let detected = $state<Lang | null>(null);
  // A path whose language is known already (a recent entry) gets no suggestion.
  let knownLangPath = "";
  $effect(() => {
    const p = path.trim();
    detected = null;
    if (!p || p === knownLangPath) return;
    const timer = setTimeout(async () => {
      try {
        const found = await api.detectLanguage(p);
        if (p !== path.trim() || !found.lang) return; // the user typed on
        detected = found.lang;
        lang = found.lang;
      } catch {
        // No suggestion. The dropdown keeps its value.
      }
    }, 400);
    return () => clearTimeout(timer);
  });

  // Whenever path changes (and is non-empty), register the project quietly
  // and fetch its git-info, so the UI can show HEAD/parent and enable or
  // disable the quick-diff card before the user clicks.
  async function refreshGitInfo() {
    error = "";
    gitInfo = null;
    current = null;
    if (!path.trim()) return;
    gitLookupInflight = true;
    try {
      const project = await api.registerProject(path.trim(), lang);
      current = project;
      gitInfo = await api.gitInfo(project.id);
    } catch (e) {
      // Quietly swallow — the user might still be typing the path. The card
      // re-tries on the next refresh trigger.
      gitInfo = null;
    } finally {
      gitLookupInflight = false;
    }
  }

  // Debounce: re-check git info ~400ms after the path stops changing.
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  $effect(() => {
    const _ = path; // track
    const __ = lang; // track
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(refreshGitInfo, 400);
  });

  // Parse a path and open one of its views. Without a view id the server
  // creates the next `Untitled N`. The viewer saves the view while the user
  // works, so nothing here asks for a name.
  async function openView(target: Pick<PathRef, "path" | "lang">, viewId: string | null) {
    busyAction = "parse";
    error = "";
    try {
      const project = await api.registerProject(target.path, target.lang);
      const xmi = await api.parse(project.id);
      const view = viewId
        ? await api.openWorkspaceView(project.id, viewId)
        : await api.createWorkspaceView(project.id);
      onLaunch({ kind: "parse", project, xmi, view });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busyAction = null;
    }
  }

  const doParse = () => openView({ path: path.trim(), lang }, null);

  // ---------- rename / delete a view from the lists ----------

  let renaming = $state<{ viewId: string; value: string } | null>(null);

  // The registry of the server is in memory, so a path from an earlier run is
  // registered again before a call that names its project.
  async function onView(target: PathRef, action: (projectId: string) => Promise<unknown>) {
    error = "";
    try {
      await action((await api.registerProject(target.path, target.lang)).id);
    } catch (e) {
      error = (e as Error).message;
    }
    await loadRecents();
  }

  async function submitRename(target: PathRef) {
    const r = renaming;
    renaming = null;
    const name = r?.value.trim();
    if (!r || !name) return;
    await onView(target, (pid) => api.saveWorkspaceView(pid, r.viewId, { name }));
  }

  const deleteView = (target: PathRef, viewId: string, name: string) =>
    confirm(`Delete the view "${name}"?`) &&
    onView(target, (pid) => api.deleteWorkspaceView(pid, viewId));

  async function doDiffCustom() {
    busyAction = "diffcustom";
    error = "";
    try {
      const project = await api.registerProject(path.trim(), lang);
      void api.touchRecent(project.id).catch(() => {});
      onLaunch({ kind: "diff_custom", project });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busyAction = null;
    }
  }

  async function doQuickDiff() {
    busyAction = "quickdiff";
    error = "";
    try {
      const project = await api.registerProject(path.trim(), lang);
      void api.touchRecent(project.id).catch(() => {});
      const xmi = await api.quickDiff(project.id);
      onLaunch({ kind: "quick_diff", project, xmi });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busyAction = null;
    }
  }

  async function doDiffVsXmi() {
    if (!path.trim() || !referenceXmi) return;
    busyAction = "vsxmi";
    error = "";
    try {
      const xmi = await api.diffSourceVsXmi(path.trim(), lang, referenceXmi);
      const project = await api.projectInfo(xmi.project_id);
      if (!project) {
        throw new Error(
          `backend lost the synthetic project ${xmi.project_id}`,
        );
      }
      onLaunch({ kind: "xmi_diff", project, xmi });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busyAction = null;
    }
  }

  function pickReference(e: Event) {
    const t = e.currentTarget as HTMLInputElement;
    referenceXmi = t.files && t.files[0] ? t.files[0] : null;
  }

  async function doXmiDiff() {
    if (!xmiOld || !xmiNew) return;
    busyAction = "xmidiff";
    error = "";
    try {
      const xmi = await api.diffXmiFiles(xmiOld, xmiNew);
      // Backend registers a synthetic ProjectInfo for the resulting XMI.
      const project = await api.projectInfo(xmi.project_id);
      if (!project) {
        throw new Error(
          `backend lost the synthetic project ${xmi.project_id}`,
        );
      }
      onLaunch({ kind: "xmi_diff", project, xmi });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busyAction = null;
    }
  }

  function pickOld(e: Event) {
    const t = e.currentTarget as HTMLInputElement;
    xmiOld = t.files && t.files[0] ? t.files[0] : null;
  }

  function pickNew(e: Event) {
    const t = e.currentTarget as HTMLInputElement;
    xmiNew = t.files && t.files[0] ? t.files[0] : null;
  }

  // Put a recent path in the form. Its language is known, so do not suggest one.
  function useRecent(r: PathRef) {
    knownLangPath = r.path;
    path = r.path;
    lang = r.lang;
  }

  function quickDiffRecent(r: PathRef) {
    useRecent(r);
    return doQuickDiff();
  }

  const quickDiffAvailable = $derived(
    !!gitInfo && gitInfo.is_git && !!gitInfo.parent_sha,
  );

  const diffCustomAvailable = $derived(
    !!gitInfo && gitInfo.is_git,
  );

  function fmtAgo(ts: number): string {
    const s = Math.max(1, Math.floor((Date.now() - ts) / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }
</script>

{#snippet viewList(target: PathRef, views: RecentPath["views"], canOpen: boolean)}
  <ul class="views">
    {#each views as v (v.id)}
      <li>
        {#if renaming?.viewId === v.id}
          <!-- svelte-ignore a11y_autofocus -->
          <input
            class="rename"
            aria-label="View name"
            bind:value={renaming.value}
            autofocus
            onkeydown={(e) => {
              if (e.key === "Enter") submitRename(target);
              if (e.key === "Escape") renaming = null;
            }}
            onblur={() => submitRename(target)}
          />
        {:else}
          <!-- The whole row opens the view. Rename and delete stay next to it:
               a button inside a button is not valid. -->
          <button
            class="open-row"
            disabled={!canOpen || busyAction !== null}
            onclick={() => openView(target, v.id)}
            title="Open “{v.name}”: parse the path and continue this view"
          >
            <span class="view-name">{v.name}</span>
            <span class="muted">{fmtAgo(v.last_used * 1000)}</span>
            <span class="open-hint" aria-hidden="true">Open</span>
          </button>
          <button
            class="ghost"
            title="Rename"
            aria-label="Rename {v.name}"
            onclick={() => (renaming = { viewId: v.id, value: v.name })}>✎</button
          >
          <button
            class="ghost"
            title="Delete"
            aria-label="Delete {v.name}"
            onclick={() => deleteView(target, v.id, v.name)}>✕</button
          >
        {/if}
      </li>
    {/each}
  </ul>
{/snippet}

<div class="home">
  <div class="hero">
    <h1>code-constraints</h1>
    <p class="tagline">
      Parse a codebase, render UML diagrams, diff revisions. The GUI mirrors
      the <code>cdec</code> CLI verbs.
    </p>
  </div>

  <!-- First on the page: most visits continue a path that is here already. -->
  <section class="recents">
    <h2>Recent paths</h2>
    {#if recentsError}
      <p class="error">The list of recent paths is not available: {recentsError}</p>
    {:else if !recentsLoaded}
      <p class="muted">Loading…</p>
    {:else if recents.length === 0}
      <p class="muted empty">
        No path yet. Enter one below and select <strong>Parse &amp; view</strong>. The viewer
        lists it here with its views the next time you start <code>cdec ui</code> in this
        folder.
      </p>
    {:else}
      <ul class="paths">
        {#each recents as r (r.id)}
          <li>
            <div class="recent-head">
              <div class="recent-meta">
                <button
                  class="path"
                  title="{r.path} — put this path in the form below"
                  onclick={() => useRecent(r)}>{r.path}</button
                >
                <span class="lang-tag">{r.lang}</span>
                {#if !r.exists}<span class="warn-inline">folder not found</span>{/if}
                <span class="muted">{fmtAgo(r.last_used * 1000)}</span>
              </div>
              <div class="recent-actions">
                <button
                  disabled={!r.exists || busyAction !== null}
                  onclick={() => openView(r, null)}
                  title="Parse the path and open a new untitled view">New view</button
                >
                <button
                  disabled={!r.exists || busyAction !== null}
                  onclick={() => quickDiffRecent(r)}
                >
                  Quick diff
                </button>
                <button
                  class="ghost"
                  onclick={() => forget(r.id)}
                  title="Remove from the list. The views stay on the disk."
                  aria-label="Remove {r.path} from the list">×</button
                >
              </div>
            </div>
            {#if r.views.length > 0}
              {@render viewList(r, r.views, r.exists)}
            {:else}
              <p class="muted no-views">No views yet.</p>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <section class="picker">
    <h2>Project</h2>
    <label class="row">
      <span class="lbl">Path</span>
      <input
        type="text"
        bind:value={path}
        placeholder="C:/path/to/code  or  /path/to/code"
        autocomplete="off"
      />
    </label>
    <label class="row">
      <span class="lbl">Language</span>
      <span class="lang-row">
        <select bind:value={lang}>
          {#each Object.entries(LANG_LABELS) as [value, label] (value)}
            <option {value}>{label}</option>
          {/each}
        </select>
        {#if detected}
          <span class="muted" title="Found from the files in this path. Change it if it is wrong.">
            {detected === lang ? "detected" : `detected: ${LANG_LABELS[detected]}`}
          </span>
        {/if}
      </span>
    </label>

    {#if path.trim()}
      <div class="git-status" class:tracked={gitInfo?.is_git} class:not-tracked={gitInfo && !gitInfo.is_git}>
        {#if gitLookupInflight}
          <span class="muted">Checking git status…</span>
        {:else if gitInfo === null}
          <span class="muted">No project registered yet.</span>
        {:else if !gitInfo.is_git}
          <span class="warn">⚠ Path is not inside a git repository — quick-diff disabled.</span>
        {:else}
          <div class="git-line">
            <span class="git-tag">git</span>
            <strong>{gitInfo.branch ?? "(detached)"}</strong>
            <code>{gitInfo.head_short}</code>
            <span class="subject">{gitInfo.head_subject}</span>
            {#if gitInfo.is_dirty}
              <span class="dirty" title="Working tree has uncommitted changes">⚠ dirty</span>
            {/if}
          </div>
          {#if gitInfo.parent_short}
            <div class="git-line muted">
              <span class="git-tag">prev</span>
              <code>{gitInfo.parent_short}</code>
              <span class="subject">{gitInfo.parent_subject}</span>
            </div>
          {:else}
            <div class="git-line muted">
              <span class="warn">first commit — no previous to diff against.</span>
            </div>
          {/if}
        {/if}
      </div>
    {/if}

    {#if current && currentViews.length > 0}
      <div class="path-views">
        <h3>Views of this path</h3>
        {@render viewList(current, currentViews, true)}
      </div>
    {/if}
  </section>

  <section class="commands">
    <h2>Run</h2>
    <div class="cards">
      <button
        class="card"
        disabled={!path.trim() || busyAction !== null}
        onclick={doParse}
      >
        <div class="card-title">Parse &amp; view</div>
        <code class="cli">cdec parse {path || "<path>"} --lang {lang}</code>
        <div class="card-desc">
          Parse the source tree and open the interactive viewer on a new view.
          The viewer saves the view while you work.
        </div>
        <div class="card-action">
          {busyAction === "parse" ? "Parsing…" : "New view"}
        </div>
      </button>

      <button
        class="card"
        disabled={!diffCustomAvailable || busyAction !== null}
        onclick={doDiffCustom}
        title={diffCustomAvailable ? "" : "Path must be inside a git repository"}
      >
        <div class="card-title">Diff revisions</div>
        <code class="cli">cdec diff {"<old>"} {"<new>"} --lang {lang}</code>
        <div class="card-desc">
          Compare any two git refs side-by-side with diff highlighting.
        </div>
        <div class="card-action">
          {busyAction === "diffcustom" ? "Opening…" : "Choose refs"}
        </div>
      </button>

      <button
        class="card"
        disabled={busyAction !== null}
        onclick={() => onLaunch({ kind: "editor" })}
        title="Open the editor to draw a new class diagram"
      >
        <div class="card-title">Create new diagram</div>
        <code class="cli">— editor —</code>
        <div class="card-desc">
          Open a blank canvas. Add classes, attributes, operations, and
          inheritance / association relationships. Save the result as XMI.
        </div>
        <div class="card-action">Open editor</div>
      </button>

      <button
        class="card highlight"
        disabled={!quickDiffAvailable || busyAction !== null}
        onclick={doQuickDiff}
        title={quickDiffAvailable
          ? `Diff ${gitInfo?.parent_short} → ${gitInfo?.head_short}`
          : "Need a git repo with at least 2 commits"}
      >
        <div class="card-title">Quick diff vs previous commit</div>
        <code class="cli">cdec diff HEAD~1 HEAD --lang {lang}</code>
        <div class="card-desc">
          {#if quickDiffAvailable}
            Diff <code>{gitInfo?.parent_short}</code> → <code>{gitInfo?.head_short}</code>.
            {#if gitInfo?.is_dirty}<br /><span class="warn-inline">⚠ working tree is dirty; uncommitted changes are not included.</span>{/if}
          {:else}
            Path must be inside a git repo with at least two commits.
          {/if}
        </div>
        <div class="card-action">
          {busyAction === "quickdiff" ? "Diffing…" : "Run"}
        </div>
      </button>
    </div>
  </section>

  <section class="xmi-diff">
    <h2>Diff source vs reference XMI</h2>
    <p class="hint">
      Parse the path above and diff it against an older XMI snapshot from
      your drive. Useful when the older version isn't in git.
      <span class="cli-hint">
        CLI: <code>cdec diff-vs-xmi reference.xmi {path || "<path>"} --lang {lang} --out diff.xmi</code>
      </span>
    </p>
    <div class="xmi-pickers vs-xmi">
      <label class="picker-box">
        <span class="lbl">Reference XMI (old)</span>
        <input type="file" accept=".xmi,application/xml" onchange={pickReference} />
        {#if referenceXmi}
          <span class="filename" title={referenceXmi.name}>
            {referenceXmi.name} <span class="muted">({Math.round(referenceXmi.size / 1024)} kB)</span>
          </span>
        {/if}
      </label>
      <button
        class="xmi-run"
        onclick={doDiffVsXmi}
        disabled={!path.trim() || !referenceXmi || busyAction !== null}
        title={!path.trim() ? "Fill in the Path field above" : ""}
      >
        {busyAction === "vsxmi" ? "Diffing…" : "Run diff vs XMI"}
      </button>
    </div>
  </section>

  <section class="xmi-diff">
    <h2>Compare two XMI files</h2>
    <p class="hint">
      Skip parsing — pick two existing <code>.xmi</code> files and produce an
      annotated diff. Both must declare the same source language.
      <span class="cli-hint">CLI: <code>cdec diff-xmi old.xmi new.xmi --out diff.xmi</code></span>
    </p>
    <div class="xmi-pickers">
      <label class="picker-box">
        <span class="lbl">Old XMI</span>
        <input type="file" accept=".xmi,application/xml" onchange={pickOld} />
        {#if xmiOld}
          <span class="filename" title={xmiOld.name}>
            {xmiOld.name} <span class="muted">({Math.round(xmiOld.size / 1024)} kB)</span>
          </span>
        {/if}
      </label>
      <label class="picker-box">
        <span class="lbl">New XMI</span>
        <input type="file" accept=".xmi,application/xml" onchange={pickNew} />
        {#if xmiNew}
          <span class="filename" title={xmiNew.name}>
            {xmiNew.name} <span class="muted">({Math.round(xmiNew.size / 1024)} kB)</span>
          </span>
        {/if}
      </label>
      <button
        class="xmi-run"
        onclick={doXmiDiff}
        disabled={!xmiOld || !xmiNew || busyAction !== null}
      >
        {busyAction === "xmidiff" ? "Diffing…" : "Run diff"}
      </button>
    </div>
  </section>

</div>

<style>
  .home {
    max-width: 880px;
    margin: 0 auto;
    padding: 2rem 1.5rem 4rem;
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }
  .hero h1 {
    margin: 0 0 0.3rem;
    font-size: 1.6rem;
  }
  .tagline {
    margin: 0;
    color: var(--muted);
    font-size: 0.95rem;
  }
  .tagline code {
    background: var(--hover);
    padding: 0 0.3rem;
    border-radius: 3px;
    font-size: 0.85em;
  }
  section h2 {
    margin: 0 0 0.6rem;
    font-size: 0.75rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .picker .row {
    display: grid;
    grid-template-columns: 6.5rem 1fr;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  .lbl {
    font-size: 0.85rem;
    color: var(--muted);
  }
  .picker input,
  .picker select {
    padding: 0.5rem 0.65rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 0.95rem;
    background: var(--bg);
    color: var(--fg);
    width: 100%;
    box-sizing: border-box;
  }
  .git-status {
    margin-top: 0.5rem;
    padding: 0.55rem 0.75rem;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--surface);
    font-size: 0.85rem;
  }
  .git-status.tracked {
    border-left: 3px solid #16a34a;
  }
  .git-status.not-tracked {
    border-left: 3px solid #ca8a04;
  }
  .git-line {
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .git-line + .git-line {
    margin-top: 0.3rem;
  }
  .git-tag {
    font-size: 0.65rem;
    text-transform: uppercase;
    background: var(--hover);
    padding: 0.05rem 0.4rem;
    border-radius: 3px;
    color: var(--muted);
  }
  .git-status code {
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 0.82rem;
    color: var(--fg);
  }
  .subject {
    color: var(--muted);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .dirty {
    background: #fef3c7;
    color: #92400e;
    padding: 0.05rem 0.35rem;
    border-radius: 3px;
    font-size: 0.7rem;
  }
  .warn,
  .warn-inline {
    color: #b45309;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 0.75rem;
  }
  .card {
    text-align: left;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.9rem 1rem;
    cursor: pointer;
    color: var(--fg);
    transition: border-color 0.12s, transform 0.05s;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    min-height: 130px;
  }
  .card:hover:not(:disabled) {
    border-color: var(--accent);
  }
  .card:active:not(:disabled) {
    transform: translateY(1px);
  }
  .card:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .card.highlight {
    background: linear-gradient(180deg, var(--surface) 0%, #f0f9ff 100%);
  }
  .card-title {
    font-weight: 600;
    font-size: 0.95rem;
  }
  .cli {
    font-size: 0.72rem;
    font-family: ui-monospace, SFMono-Regular, monospace;
    color: var(--muted);
    background: var(--hover);
    padding: 0.2rem 0.4rem;
    border-radius: 3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    align-self: flex-start;
    max-width: 100%;
  }
  .card-desc {
    font-size: 0.8rem;
    color: var(--muted);
    flex: 1;
  }
  .card-desc code {
    background: var(--hover);
    padding: 0 0.25rem;
    border-radius: 2px;
    font-size: 0.85em;
  }
  .card-action {
    align-self: flex-end;
    background: var(--accent);
    color: white;
    padding: 0.25rem 0.7rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
  }
  .card:disabled .card-action {
    background: var(--muted);
  }

  .xmi-diff .hint {
    margin: 0 0 0.6rem;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .xmi-diff .hint code {
    background: var(--hover);
    padding: 0 0.3rem;
    border-radius: 3px;
    font-size: 0.85em;
  }
  .cli-hint {
    display: block;
    margin-top: 0.2rem;
    font-size: 0.78rem;
  }
  .xmi-pickers {
    display: grid;
    grid-template-columns: 1fr 1fr auto;
    gap: 0.6rem;
    align-items: end;
  }
  .xmi-pickers.vs-xmi {
    grid-template-columns: 1fr auto;
  }
  .picker-box {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    padding: 0.55rem 0.7rem;
    border: 1px dashed var(--border);
    border-radius: 6px;
    background: var(--surface);
    cursor: pointer;
  }
  .picker-box .lbl {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .picker-box input[type="file"] {
    font-size: 0.8rem;
    background: transparent;
    border: none;
    color: var(--fg);
    padding: 0;
  }
  .picker-box .filename {
    font-size: 0.78rem;
    font-family: ui-monospace, SFMono-Regular, monospace;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .xmi-run {
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 6px;
    padding: 0.55rem 1rem;
    cursor: pointer;
    font-weight: 600;
    height: 2.4rem;
    align-self: end;
  }
  .xmi-run:disabled {
    background: var(--muted);
    cursor: not-allowed;
  }

  .lang-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .path-views h3 {
    margin: 0.8rem 0 0.3rem;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--muted);
  }
  .recents ul.paths {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .recents ul.paths > li {
    padding: 0.45rem 0.7rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
  }
  .recent-head {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .recent-meta {
    flex: 1;
    display: flex;
    align-items: baseline;
    gap: 0.5rem;
    min-width: 0;
  }
  .recent-meta .path {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: ui-monospace, SFMono-Regular, monospace;
    font-size: 0.8rem;
    text-align: left;
    background: none;
    border: none;
    padding: 0;
    color: var(--fg);
    cursor: pointer;
  }
  .recent-meta .path:hover {
    text-decoration: underline;
  }
  /* The views of one path, most recently used first. */
  ul.views {
    list-style: none;
    margin: 0.35rem 0 0;
    padding: 0 0 0 0.9rem;
    border-left: 2px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  ul.views li {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.82rem;
  }
  ul.views .view-name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  ul.views input.rename {
    flex: 1;
    font: inherit;
    padding: 0.1rem 0.3rem;
    border: 1px solid var(--accent);
    border-radius: 4px;
  }
  ul.views button {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.15rem 0.5rem;
    cursor: pointer;
    color: var(--fg);
    font-size: 0.76rem;
  }
  ul.views button:hover:not(:disabled) {
    background: var(--hover);
  }
  ul.views button.ghost {
    border-color: transparent;
    color: var(--muted);
    padding: 0.15rem 0.3rem;
  }
  /* The row itself is the button that opens the view. */
  ul.views button.open-row {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.5rem;
    border-color: transparent;
    font-size: inherit;
    text-align: left;
  }
  ul.views button.open-row:hover:not(:disabled),
  ul.views button.open-row:focus-visible {
    background: var(--hover);
    border-color: var(--border);
  }
  /* The hint shows where a click on the row leads. */
  ul.views .open-hint {
    font-size: 0.72rem;
    color: var(--accent);
    opacity: 0;
  }
  ul.views button.open-row:hover:not(:disabled) .open-hint,
  ul.views button.open-row:focus-visible .open-hint {
    opacity: 1;
  }
  ul.views button:disabled,
  .recent-actions button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .no-views {
    margin: 0.3rem 0 0 0.9rem;
  }
  .recents .empty {
    margin: 0;
    font-size: 0.85rem;
    line-height: 1.5;
  }
  .recents .empty code {
    background: var(--hover);
    padding: 0 0.3rem;
    border-radius: 3px;
  }
  .lang-tag {
    background: var(--hover);
    padding: 0.05rem 0.4rem;
    border-radius: 3px;
    font-size: 0.7rem;
  }
  .muted {
    color: var(--muted);
    font-size: 0.75rem;
  }
  .recent-actions {
    display: flex;
    gap: 0.3rem;
  }
  .recent-actions button {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.25rem 0.55rem;
    cursor: pointer;
    color: var(--fg);
    font-size: 0.78rem;
  }
  .recent-actions button:hover {
    background: var(--hover);
  }
  .recent-actions button.ghost {
    border-color: transparent;
    color: var(--muted);
    padding: 0.25rem 0.45rem;
  }
  .error {
    color: #c63a3a;
    margin: 0;
    font-size: 0.85rem;
  }
</style>
