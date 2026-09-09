<script lang="ts">
  import { onMount } from "svelte";
  import { api, type ProjectInfo, type XmiInfo } from "./lib/api";
  import HomePage, { type HomeIntent } from "./components/HomePage.svelte";
  import DiagramViewer from "./components/DiagramViewer.svelte";
  import DiffViewer from "./components/DiffViewer.svelte";
  import EditorPage from "./components/editor/EditorPage.svelte";
  import EditorModals from "./components/editor/EditorModals.svelte";
  import { newBlank, setMode } from "./lib/state/editor.svelte";
  import { setPendingFocus } from "./lib/state/diagram.svelte";

  type Mode = "browse" | "diff" | "editor";

  let project = $state<ProjectInfo | null>(null);
  let xmi = $state<XmiInfo | null>(null);
  let mode = $state<Mode>("browse");
  let editorOnly = $state(false);
  let error = $state("");
  // `cdec serve parse` deep-links here with ?path=&lang=; auto-run the parse.
  let autoloading = $state(false);
  let autoloadPath = $state("");

  function launch(intent: HomeIntent) {
    if (intent.kind === "editor") {
      newBlank();
      setMode("edit");
      editorOnly = true;
      project = null;
      xmi = null;
      error = "";
      mode = "editor";
      return;
    }
    project = intent.project;
    editorOnly = false;
    error = "";
    if (
      intent.kind === "parse" ||
      intent.kind === "quick_diff" ||
      intent.kind === "xmi_diff"
    ) {
      xmi = intent.xmi;
      mode = "browse";
    } else {
      // diff_custom: go to DiffViewer ref-pickers, no xmi yet
      xmi = null;
      mode = "diff";
    }
  }

  // Synthetic projects (uploaded-XMI diffs) have ids starting with `u` and a
  // placeholder path. They can't be re-parsed or diffed against git refs.
  const isSynthetic = $derived(
    !!project && (project.path.startsWith("uploaded:") || project.id.startsWith("u")),
  );

  async function reparse() {
    if (!project) return;
    try {
      xmi = await api.parse(project.id);
      mode = "browse";
    } catch (e) {
      error = (e as Error).message;
    }
  }

  function reset() {
    project = null;
    xmi = null;
    editorOnly = false;
    setMode("view");
    error = "";
    stopProposalPolling();
  }

  // ---- proposal live-refresh -------------------------------------------
  // When entered via a `cdec propose` deep link (?proposal=1), poll the
  // project's latest-proposal endpoint and hot-swap the XMI whenever the
  // agent pushes a new iteration. Drag positions and visibility filters are
  // keyed by stable ids in diagramState, so they survive the swap.
  let proposalTimer: ReturnType<typeof setInterval> | null = null;
  let proposalSeq = 0;

  function startProposalPolling(projectId: string, initialSeq: number) {
    stopProposalPolling();
    proposalSeq = initialSeq;
    proposalTimer = setInterval(async () => {
      try {
        const p = await api.latestProposal(projectId);
        if (p.seq > proposalSeq) {
          proposalSeq = p.seq;
          if (p.focus.length > 0) setPendingFocus(p.focus);
          xmi = { id: p.id, project_id: p.project_id };
        }
      } catch {
        // Server briefly unreachable or proposal gone — keep polling quietly.
      }
    }, 2500);
  }

  function stopProposalPolling() {
    if (proposalTimer !== null) clearInterval(proposalTimer);
    proposalTimer = null;
  }

  // Deep-link entry: `cdec serve parse` opens /?path=<dir>&lang=<lang>. Run the
  // same register+parse flow HomePage uses, then land on the class diagram.
  onMount(async () => {
    const q = new URLSearchParams(window.location.search);
    const path = q.get("path");
    const lang = q.get("lang");

    // `cdec reference show` deep-links here with a pre-registered, already-diffed
    // XMI: ?xmi=<id>&project=<id>. Both ProjectInfo and XmiInfo are plain shapes,
    // so we can reconstruct them straight from the URL — no backend lookup. The
    // diff walkthrough activates on its own once /api/xmi/{id}/changes is non-empty.
    const xmiId = q.get("xmi");
    const projectId = q.get("project");
    // `cdec propose` adds &focus=A,B (pre-filter the class canvas to these
    // qualified names) and &proposal=1 (poll for newer pushes and hot-swap).
    const focus = (q.get("focus") ?? "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (focus.length > 0) setPendingFocus(focus);
    const isProposal = q.get("proposal") === "1";
    if (xmiId && projectId) {
      const proj: ProjectInfo = {
        id: projectId,
        path: path ?? "",
        lang: (lang ?? "python") as ProjectInfo["lang"],
      };
      const x: XmiInfo = { id: xmiId, project_id: projectId };
      launch({ kind: "xmi_diff", project: proj, xmi: x });
      if (isProposal) {
        // Seed the sequence from the server so a stale tab still catches up.
        try {
          const p = await api.latestProposal(projectId);
          startProposalPolling(projectId, p.id === xmiId ? p.seq : 0);
        } catch {
          startProposalPolling(projectId, 0);
        }
      }
      history.replaceState(null, "", window.location.pathname);
      return;
    }

    if (!path || !lang) return;
    autoloading = true;
    autoloadPath = path;
    error = "";
    try {
      const proj = await api.registerProject(
        path,
        lang as ProjectInfo["lang"],
      );
      const x = await api.parse(proj.id);
      launch({ kind: "parse", project: proj, xmi: x });
      // Clear the query so a refresh / Home doesn't re-trigger the autoload.
      history.replaceState(null, "", window.location.pathname);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      autoloading = false;
    }
  });
</script>

<div class="app">
  <header>
    <h1>code-constraints</h1>
    {#if project}
      <span class="path" title={project.path}>{project.path}
        <span class="lang">{project.lang}</span>
      </span>
      <nav>
        <button class:active={mode === "browse"} onclick={() => (mode = "browse")}>Browse</button>
        {#if !isSynthetic}
          <button class:active={mode === "diff"} onclick={() => (mode = "diff")}>Diff</button>
        {/if}
      </nav>
      {#if !isSynthetic}
        <button class="ghost" onclick={reparse} title="Re-parse current source">Re-parse</button>
      {/if}
      {#if xmi}
        <a
          class="export"
          href={`/api/xmi/${xmi.id}/source`}
          download={`${xmi.id}.xmi`}
          title="Download the XMI for the current view (equivalent to cdec parse --out)"
        >
          Download XMI
        </a>
      {/if}
      <button class="reset" onclick={reset}>Home</button>
    {/if}
  </header>
  <div class="content">
    {#if editorOnly}
      <EditorPage onexit={reset} />
    {:else if autoloading}
      <p class="autoload">Parsing <code>{autoloadPath}</code> …</p>
    {:else if !project}
      <HomePage onLaunch={launch} />
    {:else if error}
      <p class="error">{error}</p>
    {:else if mode === "browse" && xmi}
      <DiagramViewer {xmi} />
    {:else if mode === "diff"}
      <DiffViewer {project} />
    {/if}
  </div>
</div>

<EditorModals />

<style>
  :global(:root) {
    --bg: #fafafa;
    --surface: #ffffff;
    --fg: #1a1a1a;
    --muted: #6b7280;
    --border: #e5e7eb;
    --accent: #2563eb;
    --hover: #f1f5f9;
  }
  :global(body) {
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  }
  :global(html, body, #app) {
    height: 100%;
  }
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
  header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 1.25rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  h1 { margin: 0; font-size: 1.1rem; }
  .path {
    color: var(--muted);
    font-size: 0.875rem;
    font-family: ui-monospace, SFMono-Regular, monospace;
    max-width: 40rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .lang {
    background: var(--hover);
    border-radius: 4px;
    padding: 0.05rem 0.4rem;
    margin-left: 0.4rem;
    font-size: 0.75rem;
    color: var(--fg);
  }
  nav { margin-left: auto; display: flex; gap: 0.25rem; }
  nav button,
  .ghost,
  .reset,
  .export {
    background: transparent;
    border: 1px solid var(--border);
    padding: 0.3rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    color: var(--fg);
    text-decoration: none;
    font-size: 0.85rem;
    line-height: 1.4;
    display: inline-flex;
    align-items: center;
  }
  nav button.active {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .export {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  .reset, .ghost {
    color: var(--muted);
  }
  .reset:hover, .ghost:hover, nav button:hover, .export:hover {
    background: var(--hover);
  }
  .export:hover {
    background: #1d4ed8;
  }
  .content {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
  }
  .error { color: #c63a3a; padding: 1rem; }
  .autoload { color: var(--muted); padding: 1rem; }
  .autoload code {
    background: var(--hover);
    padding: 0 0.3rem;
    border-radius: 3px;
  }
</style>
