<script lang="ts">
  import {
    applyView,
    applyServerView,
    exportViewToFile,
    importViewFromFile,
    nameToFilename,
    snapshotServerView,
  } from "../../lib/views";
  import {
    api,
    type ClassGraph,
    type ServerView,
    type ServerViewListing,
    type XmiInfo,
  } from "../../lib/api";
  import CollapsibleSection from "./CollapsibleSection.svelte";

  let { graph, xmi }: { graph: ClassGraph | null; xmi: XmiInfo } = $props();

  // ---------- server views state ----------
  let serverViews = $state<ServerViewListing[]>([]);
  let loadingViews = $state(false);
  let viewsError = $state<string | null>(null);

  // ---------- save new view ----------
  let newViewName = $state("");
  let saving = $state(false);

  // ---------- inline rename ----------
  let renamingFilename = $state<string | null>(null);
  let renameValue = $state("");

  // ---------- status feedback ----------
  let status = $state<{ kind: "ok" | "error" | "warn"; msg: string } | null>(null);

  // ---------- local file import ----------
  let fileInput: HTMLInputElement | undefined = $state();

  // Reload view list whenever the project changes.
  $effect(() => {
    const _pid = xmi.project_id; // track dependency
    loadViews();
  });

  async function loadViews() {
    loadingViews = true;
    viewsError = null;
    try {
      serverViews = await api.listViews(xmi.project_id);
    } catch (e) {
      viewsError = (e as Error).message;
    } finally {
      loadingViews = false;
    }
  }

  async function onLoad(filename: string) {
    if (!graph) return;
    status = null;
    try {
      const view = await api.getView(xmi.project_id, filename);
      const { dropped } = applyServerView(view, graph);
      if (dropped.length > 0) {
        status = {
          kind: "warn",
          msg: `${dropped.length} class${dropped.length === 1 ? "" : "es"} from this view no longer exist in the current model and were skipped.`,
        };
      } else {
        status = { kind: "ok", msg: `Loaded "${view.name}".` };
      }
    } catch (e) {
      status = { kind: "error", msg: (e as Error).message };
    }
  }

  async function onSave() {
    if (!graph || !newViewName.trim()) return;
    saving = true;
    status = null;
    try {
      const view = snapshotServerView(newViewName.trim(), graph);
      const filename = nameToFilename(newViewName.trim());
      await api.saveView(xmi.project_id, filename, view);
      await loadViews();
      status = { kind: "ok", msg: `Saved "${view.name}".` };
    } catch (e) {
      status = { kind: "error", msg: (e as Error).message };
    } finally {
      saving = false;
    }
  }

  async function onDelete(filename: string) {
    status = null;
    try {
      await api.deleteView(xmi.project_id, filename);
      await loadViews();
    } catch (e) {
      status = { kind: "error", msg: (e as Error).message };
    }
  }

  function onRenameStart(filename: string, currentName: string) {
    renamingFilename = filename;
    renameValue = currentName;
    status = null;
  }

  function onRenameCancel() {
    renamingFilename = null;
    renameValue = "";
  }

  async function onRenameSubmit(oldFilename: string) {
    const newName = renameValue.trim();
    if (!newName) { onRenameCancel(); return; }
    status = null;
    try {
      const newFilename = nameToFilename(newName);
      // Fetch existing view to preserve its positions/visible list
      const existing = await api.getView(xmi.project_id, oldFilename);
      const updated: ServerView = { ...existing, name: newName };
      await api.saveView(xmi.project_id, newFilename, updated);
      if (newFilename !== oldFilename) {
        await api.deleteView(xmi.project_id, oldFilename);
      }
      renamingFilename = null;
      await loadViews();
      status = { kind: "ok", msg: `Renamed to "${newName}".` };
    } catch (e) {
      status = { kind: "error", msg: (e as Error).message };
    }
  }

  // ---------- local file (legacy) ----------
  function onExport() {
    const name = newViewName.trim() || "view";
    try {
      exportViewToFile(name, xmi.id);
      status = { kind: "ok", msg: `Downloaded "${name}.cdecview.json".` };
    } catch (e) {
      status = { kind: "error", msg: (e as Error).message };
    }
  }

  async function onImportChange(e: Event) {
    const target = e.currentTarget as HTMLInputElement;
    const file = target.files?.[0];
    target.value = "";
    if (!file) return;
    try {
      const view = await importViewFromFile(file);
      const knownIds = graph ? new Set(graph.nodes.map((n) => n.id)) : undefined;
      applyView(view, knownIds);
      newViewName = view.name ?? "";
      status = { kind: "ok", msg: `Loaded "${view.name}" from file.` };
    } catch (e) {
      status = { kind: "error", msg: (e as Error).message };
    }
  }
</script>

<div class="saved-views">
  <CollapsibleSection title="Views">
  {#if loadingViews}
    <p class="hint">Loading…</p>
  {:else if viewsError}
    <p class="status error">{viewsError}</p>
  {:else if serverViews.length === 0}
    <p class="hint">No saved views yet.</p>
  {:else}
    <ul class="view-list">
      {#each serverViews as v (v.filename)}
        <li class="view-row">
          {#if renamingFilename === v.filename}
            <input
              class="name-input rename-input"
              bind:value={renameValue}
              onkeydown={(e) => {
                if (e.key === "Enter") onRenameSubmit(v.filename);
                if (e.key === "Escape") onRenameCancel();
              }}
            />
            <button class="icon-btn" title="Confirm rename" onclick={() => onRenameSubmit(v.filename)}>✓</button>
            <button class="icon-btn" title="Cancel" onclick={onRenameCancel}>✕</button>
          {:else}
            <span class="view-name" title={v.filename}>{v.name}</span>
            <button class="action-btn" onclick={() => onLoad(v.filename)}>Load</button>
            <button class="icon-btn" title="Rename" onclick={() => onRenameStart(v.filename, v.name)}>✎</button>
            <button class="icon-btn danger" title="Delete" onclick={() => onDelete(v.filename)}>✕</button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  <div class="save-row">
    <input
      type="text"
      placeholder="View name"
      bind:value={newViewName}
      class="name-input"
      onkeydown={(e) => { if (e.key === "Enter") onSave(); }}
    />
    <button onclick={onSave} disabled={!graph || saving || !newViewName.trim()}>
      {saving ? "…" : "Save"}
    </button>
  </div>

  {#if status}
    <p class="status {status.kind}">{status.msg}</p>
  {/if}

  <details class="local-file">
    <summary>Local file (export / import)</summary>
    <div class="row">
      <button onclick={onExport} title="Download view as .cdecview.json">Export</button>
      <button onclick={() => fileInput?.click()} title="Load a view from a .cdecview.json file">Import</button>
      <input
        type="file"
        accept=".json,application/json"
        bind:this={fileInput}
        onchange={onImportChange}
        style="display:none"
      />
    </div>
  </details>
  </CollapsibleSection>
</div>

<style>
  .saved-views {
    border-top: 1px solid var(--border);
    padding: 0.5rem 0.75rem;
    background: #fbfbfb;
  }
  /* View list */
  .view-list {
    list-style: none;
    margin: 0 0 0.5rem;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .view-row {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  .view-name {
    flex: 1;
    font-size: 0.85rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--fg);
  }

  /* Save row */
  .save-row {
    display: flex;
    gap: 0.25rem;
    align-items: center;
    margin-bottom: 0.25rem;
  }

  /* Inputs */
  .name-input {
    flex: 1;
    padding: 0.25rem 0.5rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 0.8rem;
    min-width: 0;
    background: var(--bg);
    color: var(--fg);
  }
  .rename-input {
    flex: 1;
  }

  /* Buttons */
  button {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.25rem 0.5rem;
    font-size: 0.75rem;
    cursor: pointer;
    color: var(--fg);
    white-space: nowrap;
    flex-shrink: 0;
  }
  button:hover:not(:disabled) {
    background: var(--hover);
  }
  button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .action-btn {
    font-size: 0.72rem;
    padding: 0.2rem 0.4rem;
  }
  .icon-btn {
    padding: 0.2rem 0.35rem;
    font-size: 0.8rem;
    line-height: 1;
  }
  .icon-btn.danger {
    color: #b91c1c;
    border-color: transparent;
  }
  .icon-btn.danger:hover {
    border-color: #b91c1c;
    background: #fff5f5;
  }

  /* Status messages */
  .status {
    margin: 0.3rem 0 0;
    font-size: 0.72rem;
    line-height: 1.3;
  }
  .status.ok { color: #166534; }
  .status.error { color: #c63a3a; }
  .status.warn { color: #92400e; }

  /* Hint (empty state / loading) */
  .hint {
    margin: 0 0 0.4rem;
    font-size: 0.78rem;
    color: var(--muted);
    font-style: italic;
  }

  /* Local file details */
  .local-file {
    margin-top: 0.5rem;
  }
  .local-file summary {
    cursor: pointer;
    font-size: 0.72rem;
    color: var(--muted);
    user-select: none;
    list-style: none;
  }
  .local-file summary::before {
    content: "▸ ";
  }
  .local-file[open] summary::before {
    content: "▾ ";
  }
  .local-file .row {
    display: flex;
    gap: 0.25rem;
    margin-top: 0.35rem;
  }
</style>
