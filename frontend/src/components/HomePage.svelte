<script lang="ts">
  // The first page of `cdec ui`. It answers one question: what do you open?
  // A folder with code (this folder, a recent one, any other one), or a model
  // file. Every other task starts from the open project.
  import "./journey/journey.css";
  import { onMount } from "svelte";
  import {
    api,
    type Lang,
    type ProjectInfo,
    type RecentPath,
    type StartInfo,
    type WorkspaceView,
    type XmiInfo,
  } from "../lib/api";
  import FolderBrowser from "./FolderBrowser.svelte";

  export type HomeIntent =
    | {
        kind: "parse";
        project: ProjectInfo;
        xmi: XmiInfo;
        view?: WorkspaceView;
        /** The first page: the project page for a folder, the diagram for a view. */
        landing: "project" | "diagram";
      }
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
  let busy = $state(false);
  let error = $state("");
  let browsing = $state(false);
  let start = $state<StartInfo | null>(null);

  // ---------- recent paths and their views (the server keeps them in .cdec_cache) ----------

  let recents = $state<RecentPath[]>([]);
  let recentsLoaded = $state(false);

  async function loadRecents() {
    // The list is a convenience. The rest of the page works without it.
    recents = await api.workspace().catch(() => []);
    recentsLoaded = true;
  }
  onMount(() => {
    void loadRecents();
    // The folder that `cdec ui` ran in. A remote client does not get it.
    api.start().then((s) => (start = s)).catch(() => {});
  });

  async function forget(id: string) {
    await api.forgetRecent(id).catch(() => {});
    await loadRecents();
  }

  // ---------- language suggestion ----------

  // Suggest the language when the path changes. A choice the user makes in
  // the dropdown stays until the path changes again.
  let detected = $state<Lang | null>(null);
  let isFolder = $state(false);
  $effect(() => {
    const p = path.trim();
    detected = null;
    isFolder = false;
    if (!p) return;
    const timer = setTimeout(async () => {
      try {
        const found = await api.detectLanguage(p);
        if (p !== path.trim()) return; // the user typed on
        isFolder = found.is_dir;
        if (!found.lang) return;
        detected = found.lang;
        lang = found.lang;
      } catch {
        // No suggestion. The dropdown keeps its value.
      }
    }, 400);
    return () => clearTimeout(timer);
  });

  // ---------- open a folder ----------

  // Parse a path and open one of its views: the named one, a new one, or the
  // view that was used last. The viewer saves the view while the user works,
  // so nothing here asks for a name.
  async function open(target: Pick<PathRef, "path" | "lang">, viewId: string | "new" | "last") {
    busy = true;
    error = "";
    try {
      const project = await api.registerProject(target.path, target.lang);
      const xmi = await api.parse(project.id);
      const last = viewId === "last" ? (await api.workspaceViews(project.id))[0]?.id : undefined;
      const id = viewId === "last" ? last : viewId === "new" ? undefined : viewId;
      const view = id
        ? await api.openWorkspaceView(project.id, id)
        : await api.createWorkspaceView(project.id);
      const landing = viewId === "last" ? "project" : "diagram";
      onLaunch({ kind: "parse", project, xmi, view, landing });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  // ---------- rename / delete a view from the list ----------

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

  // ---------- open a model file ----------

  let modelFile = $state<File | null>(null);
  let otherFile = $state<File | null>(null);
  const pick = (e: Event) => (e.currentTarget as HTMLInputElement).files?.[0] ?? null;

  // One file opens as a diagram. With a second file, the diagram shows what
  // the first file has and the second one does not.
  async function openModel() {
    if (!modelFile) return;
    busy = true;
    error = "";
    try {
      const xmi = otherFile
        ? await api.diffXmiFiles(otherFile, modelFile)
        : await api.openModelFile(modelFile);
      const project = await api.projectInfo(xmi.project_id);
      if (!project) throw new Error("the server does not know the opened model any more");
      onLaunch({ kind: "xmi_diff", project, xmi });
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  function fmtAgo(ts: number): string {
    const s = Math.max(1, Math.floor((Date.now() - ts) / 1000));
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }
</script>

<div class="jy home">
  <div class="hero">
    <h1>code-constraints</h1>
    <p class="muted">
      Open a folder with code, or an empty folder for a new design. The project page then leads
      to the diagrams, the rules, the checks and the timeline.
    </p>
  </div>

  {#if error}<p class="error" role="alert">{error}</p>{/if}

  {#if start}
    <section class="card here">
      <div class="grow">
        <h2>This folder</h2>
        <p>
          <code title={start.cwd}>{start.cwd}</code>
          {#if start.configured}
            <span class="badge goal">cdec project</span>
          {:else}
            <span class="badge">no .cdec folder yet</span>
          {/if}
          {#if start.lang}<span class="badge">{LANG_LABELS[start.lang]}</span>{/if}
        </p>
        <p class="muted">
          {#if start.configured}
            The viewer started in a cdec project. Its source folder is <code>{start.path}</code>.
          {:else if start.lang}
            The viewer started in this folder. The project page sets it up.
          {:else}
            The viewer started in this folder. It found no source code here: choose the language
            below, or open another folder.
          {/if}
        </p>
      </div>
      {#if start.lang}
        <button
          class="primary big"
          disabled={busy}
          onclick={() => open({ path: start!.path, lang: start!.lang! }, "last")}
        >
          {busy ? "Opening…" : "Open this folder"}
        </button>
      {:else}
        <button class="big" onclick={() => (path = start!.path)}>Use this path below</button>
      {/if}
    </section>
  {/if}

  <section>
    <h2>Open a folder</h2>
    <div class="card form">
      <div class="row">
        <input
          class="grow"
          type="text"
          bind:value={path}
          aria-label="Path of the folder"
          placeholder="C:/path/to/code  or  /path/to/code"
          autocomplete="off"
        />
        <button onclick={() => (browsing = true)}>Browse…</button>
      </div>
      <div class="row">
        <label class="row">
          <span class="muted">Language</span>
          <select bind:value={lang}>
            {#each Object.entries(LANG_LABELS) as [value, label] (value)}
              <option {value}>{label}</option>
            {/each}
          </select>
        </label>
        {#if detected}
          <span class="muted" title="Found from the files in this path. Change it if it is wrong.">
            {detected === lang ? "detected" : `detected: ${LANG_LABELS[detected]}`}
          </span>
        {:else if path.trim() && isFolder}
          <span class="muted">No source code found: choose the language of the new design.</span>
        {/if}
        <span class="grow"></span>
        <button
          class="primary"
          disabled={!path.trim() || busy}
          onclick={() => open({ path: path.trim(), lang }, "last")}
        >
          {busy ? "Opening…" : "Open the folder"}
        </button>
      </div>
    </div>
  </section>

  <section>
    <h2>Recent folders</h2>
    {#if !recentsLoaded}
      <p class="muted">Loading…</p>
    {:else if recents.length === 0}
      <p class="muted">No folder yet. A folder that you open shows here the next time.</p>
    {:else}
      <ul class="recents">
        {#each recents as r (r.id)}
          <li class="card">
            <div class="row">
              <button
                class="link"
                disabled={!r.exists || busy}
                title="Open {r.path} on the view that was used last"
                onclick={() => open(r, "last")}>{r.path}</button
              >
              <span class="badge">{LANG_LABELS[r.lang]}</span>
              {#if !r.exists}<span class="badge warn">folder not found</span>{/if}
              <span class="muted">{fmtAgo(r.last_used * 1000)}</span>
              <span class="grow"></span>
              <button
                disabled={!r.exists || busy}
                onclick={() => open(r, "new")}
                title="Open the folder on a new, empty view">New view</button
              >
              <button
                onclick={() => forget(r.id)}
                title="Remove from the list. The views stay on the disk."
                aria-label="Remove {r.path} from the list">×</button
              >
            </div>
            {#if r.views.length > 0}
              <ul class="views">
                {#each r.views as v (v.id)}
                  <li class="row">
                    {#if renaming?.viewId === v.id}
                      <!-- svelte-ignore a11y_autofocus -->
                      <input
                        type="text"
                        aria-label="View name"
                        bind:value={renaming.value}
                        autofocus
                        onkeydown={(e) => {
                          if (e.key === "Enter") submitRename(r);
                          if (e.key === "Escape") renaming = null;
                        }}
                        onblur={() => submitRename(r)}
                      />
                    {:else}
                      <button
                        class="link"
                        disabled={!r.exists || busy}
                        onclick={() => open(r, v.id)}
                        title="Open “{v.name}”: parse the folder and continue this view"
                        >{v.name}</button
                      >
                      <span class="muted">{fmtAgo(v.last_used * 1000)}</span>
                      <button
                        class="quiet"
                        aria-label="Rename {v.name}"
                        title="Rename"
                        onclick={() => (renaming = { viewId: v.id, value: v.name })}>✎</button
                      >
                      <button
                        class="quiet"
                        aria-label="Delete {v.name}"
                        title="Delete"
                        onclick={() => deleteView(r, v.id, v.name)}>✕</button
                      >
                    {/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section>
    <h2>Open a model file</h2>
    <div class="card form">
      <p class="muted">
        A model file is a saved diagram: a snapshot from <code>cdec parse --out</code>, an entry
        of <code>.cdec/history/</code>, or a target model. It is a <code>.xmi</code> or a
        <code>.json</code> file. To compare a file with the code, open the folder first: the
        diagram page compares any two models.
      </p>
      <div class="row">
        <label class="file">
          <span class="muted">Model</span>
          <input type="file" accept=".xmi,.json" onchange={(e) => (modelFile = pick(e))} />
        </label>
        <label class="file">
          <span class="muted">Compare with (optional)</span>
          <input type="file" accept=".xmi,.json" onchange={(e) => (otherFile = pick(e))} />
        </label>
        <span class="grow"></span>
        <button class="primary" disabled={!modelFile || busy} onclick={openModel}>
          {otherFile ? "Compare the two files" : "Open the file"}
        </button>
      </div>
      <div class="row">
        <span class="muted">No folder and no file:</span>
        <button disabled={busy} onclick={() => onLaunch({ kind: "editor" })}>
          Draw a new diagram
        </button>
      </div>
    </div>
  </section>
</div>

{#if browsing}
  <FolderBrowser
    start={path.trim() || start?.cwd || ""}
    onclose={() => (browsing = false)}
    onpick={(p) => {
      path = p;
      browsing = false;
    }}
  />
{/if}

<style>
  .home {
    max-width: 62rem;
    margin: 0 auto;
    padding: 1.5rem 1.25rem 3rem;
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }
  .hero h1 {
    margin: 0 0 0.25rem;
    font-size: 1.6rem;
  }
  .here {
    display: flex;
    align-items: center;
    gap: 1rem;
    border-color: var(--accent);
  }
  .grow {
    flex: 1;
    min-width: 0;
  }
  .big {
    padding: 0.55rem 1.1rem;
    font-size: 0.95rem;
    white-space: nowrap;
  }
  .form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  .recents,
  .views {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .views {
    margin: 0.5rem 0 0 1rem;
    gap: 0.2rem;
  }
  .link {
    border: 0;
    background: none;
    padding: 0.1rem 0.2rem;
    color: var(--accent);
    font-family: ui-monospace, SFMono-Regular, monospace;
    text-align: left;
    overflow-wrap: anywhere;
  }
  .views .link {
    font-family: inherit;
    font-weight: 600;
  }
  .quiet {
    border-color: transparent;
    padding: 0 0.35rem;
    color: var(--muted);
  }
  .file {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
</style>
