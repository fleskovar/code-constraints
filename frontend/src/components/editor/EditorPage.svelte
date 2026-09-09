<script lang="ts">
  import { api, type ProjectDraft } from "../../lib/api";
  import { diagramState } from "../../lib/state/diagram.svelte";
  import {
    editorState,
    loadFromJson,
    newBlank,
    setBaseline,
  } from "../../lib/state/editor.svelte";
  import EditorCanvas from "./EditorCanvas.svelte";

  interface Props {
    /** "exit" pops the user back to the home page. */
    onexit: () => void;
  }

  let { onexit }: Props = $props();

  let busy = $state(false);
  let error = $state("");
  let fileInput: HTMLInputElement | null = null;
  let baselineInput: HTMLInputElement | null = null;

  function startBlank(
    lang: "python" | "csharp" | "typescript" | "svelte" = "python",
  ) {
    newBlank(lang);
    diagramState.nodePositions = new Map();
    error = "";
  }

  /** Read a model file (.xmi via the server codec, .json parsed locally). */
  async function readModelFile(file: File): Promise<ProjectDraft> {
    if (file.name.toLowerCase().endsWith(".json")) {
      const parsed = JSON.parse(await file.text()) as ProjectDraft;
      if (!Array.isArray(parsed.packages)) {
        throw new Error(`${file.name}: not a model JSON (missing packages[])`);
      }
      parsed.activities ??= [];
      parsed.sequences ??= [];
      parsed.associations ??= [];
      parsed.source_language ??= "python";
      parsed.root_path ??= "";
      return parsed;
    }
    return api.editFromXmi(file, file.name);
  }

  async function openFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    error = "";
    busy = true;
    try {
      const draft = await readModelFile(file);
      loadFromJson(draft, file.name);
      diagramState.nodePositions = new Map();
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  async function openBaseline(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    error = "";
    busy = true;
    try {
      setBaseline(await readModelFile(file));
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  function download(blob: Blob, name: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function saveXmi() {
    error = "";
    busy = true;
    try {
      const name = editorState.fileName.replace(/\.json$/i, ".xmi");
      const blob = await api.editToXmi(editorState.project, name);
      download(blob, name || "diagram.xmi");
      editorState.dirty = false;
    } catch (err) {
      error = (err as Error).message;
    } finally {
      busy = false;
    }
  }

  function saveJson() {
    error = "";
    const name =
      editorState.fileName.replace(/\.xmi$/i, ".json") || "diagram.json";
    const body = JSON.stringify(
      $state.snapshot(editorState.project),
      null,
      2,
    );
    download(new Blob([body], { type: "application/json" }), name);
    editorState.dirty = false;
  }
</script>

<div class="page">
  <header class="bar">
    <div class="left">
      <strong>UML editor</strong>
      <span class="muted">{editorState.fileName}{editorState.dirty ? " *" : ""}</span>
    </div>
    <div class="right">
      <button onclick={() => startBlank()} disabled={busy}>New diagram</button>
      <button onclick={() => fileInput?.click()} disabled={busy}>Open…</button>
      <input
        bind:this={fileInput}
        type="file"
        accept=".xmi,.json,application/xml,text/xml,application/json"
        onchange={openFile}
        hidden
      />
      <button
        onclick={() => baselineInput?.click()}
        disabled={busy}
        title="Load a baseline model (.xmi or .json) to diff the draft against while editing"
      >Baseline…</button>
      <input
        bind:this={baselineInput}
        type="file"
        accept=".xmi,.json,application/xml,text/xml,application/json"
        onchange={openBaseline}
        hidden
      />
      <button class="primary" onclick={saveXmi} disabled={busy}>Save .xmi</button>
      <button onclick={saveJson} disabled={busy}>Save .json</button>
      {#if busy}<span class="muted">…</span>{/if}
      {#if error}<span class="error">{error}</span>{/if}
      <button class="ghost" onclick={onexit} title="Back to home">Home</button>
    </div>
  </header>
  <div class="canvas-wrap">
    <EditorCanvas />
  </div>
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex: 0 0 auto;
    flex-wrap: wrap;
  }
  .left,
  .right {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    flex-wrap: wrap;
  }
  .muted {
    color: var(--muted);
    font-size: 0.85rem;
  }
  button {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.3rem 0.6rem;
    font-size: 0.85rem;
    cursor: pointer;
    color: var(--fg);
  }
  button:hover:not(:disabled) {
    background: var(--hover);
  }
  button.primary {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  button.active {
    background: var(--accent);
    color: white;
    border-color: var(--accent);
  }
  button.ghost {
    color: var(--muted);
  }
  button:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .error {
    color: #c63a3a;
    font-size: 0.85rem;
  }
  .canvas-wrap {
    flex: 1;
    min-height: 0;
  }
</style>
