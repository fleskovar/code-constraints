<script lang="ts">
  import { api, type ProjectInfo } from "../lib/api";

  let { onSelect }: { onSelect: (p: ProjectInfo) => void } = $props();

  let path = $state("");
  let lang = $state<"python" | "csharp" | "typescript" | "svelte">("python");
  let busy = $state(false);
  let error = $state("");

  async function register() {
    busy = true;
    error = "";
    try {
      const info = await api.registerProject(path, lang);
      onSelect(info);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }
</script>

<div class="card">
  <h2>Choose a project</h2>
  <p class="hint">Point code-constraints at a source directory. The path must be accessible from the server.</p>
  <label>
    Path
    <input type="text" bind:value={path} placeholder="C:/path/to/project" />
  </label>
  <label>
    Language
    <select bind:value={lang}>
      <option value="python">Python</option>
      <option value="csharp">C#</option>
      <option value="typescript">TypeScript</option>
      <option value="svelte">Svelte 5</option>
    </select>
  </label>
  <button onclick={register} disabled={busy || !path}>
    {busy ? "Working…" : "Continue"}
  </button>
  {#if error}
    <p class="error">{error}</p>
  {/if}
</div>

<style>
  .card {
    max-width: 480px;
    margin: 4rem auto;
    padding: 2rem;
    background: var(--surface);
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  h2 { margin: 0; }
  .hint { margin: 0; color: var(--muted); font-size: 0.9rem; }
  label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.875rem; }
  input, select {
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 1rem;
    background: var(--bg);
    color: var(--fg);
  }
  button {
    padding: 0.65rem 1rem;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
  }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .error { color: #c63a3a; margin: 0; font-size: 0.875rem; }
</style>
