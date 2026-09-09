<script lang="ts">
  import { api, type ProjectInfo, type XmiInfo } from "../lib/api";
  import DiagramViewer from "./DiagramViewer.svelte";

  let { project }: { project: ProjectInfo } = $props();

  let refs = $state<string[]>([]);
  let oldRef = $state("");
  let newRef = $state("");
  let subpath = $state("");
  let xmi = $state<XmiInfo | null>(null);
  let error = $state("");
  let busy = $state(false);

  $effect(() => {
    api
      .refs(project.id)
      .then((r) => {
        refs = r;
        if (r.length >= 2) {
          oldRef = r[1];
          newRef = r[0];
        } else if (r.length === 1) {
          oldRef = r[0];
          newRef = r[0];
        }
      })
      .catch((e: Error) => (error = e.message));
  });

  async function runDiff() {
    busy = true;
    error = "";
    try {
      xmi = await api.diff(project.id, oldRef, newRef, subpath);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
</script>

<div class="diff">
  <div class="controls">
    <label>
      Old ref
      <select bind:value={oldRef}>
        {#each refs as r}<option value={r}>{r}</option>{/each}
      </select>
    </label>
    <label>
      New ref
      <select bind:value={newRef}>
        {#each refs as r}<option value={r}>{r}</option>{/each}
      </select>
    </label>
    <label>
      Sub-path
      <input type="text" bind:value={subpath} placeholder="optional" />
    </label>
    <button onclick={runDiff} disabled={busy || !oldRef || !newRef}>
      {busy ? "Diffing…" : "Diff"}
    </button>
  </div>
  {#if error}<p class="error">{error}</p>{/if}
  {#if xmi}
    <div class="viewer">
      <DiagramViewer {xmi} />
    </div>
  {/if}
</div>

<style>
  .diff { display: flex; flex-direction: column; height: 100%; }
  .controls {
    display: flex;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    align-items: end;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--muted);
  }
  select, input {
    padding: 0.35rem 0.55rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    background: var(--bg);
    color: var(--fg);
    min-width: 180px;
  }
  button {
    padding: 0.45rem 0.9rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 600;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .viewer { flex: 1; min-height: 0; }
  .error { color: #c63a3a; padding: 0 1rem; }
</style>
