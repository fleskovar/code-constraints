<script lang="ts">
  import Modal from "../editor/Modal.svelte";
  import { api, type LayerDependencies } from "../../lib/api";
  import { layersPanel, closeLayers } from "../../lib/state/layers.svelte";

  let { projectId }: { projectId: string } = $props();

  let data = $state<LayerDependencies | null>(null);
  let loadedFor = $state<string | null>(null);
  let error = $state("");

  // Fetch the allow-matrix the first time the modal opens for a given project
  // (re-fetch if the project changes). Cheap + cached so reopening is instant.
  $effect(() => {
    if (!layersPanel.open) return;
    if (loadedFor === projectId && data) return;
    error = "";
    api
      .layerDependencies(projectId)
      .then((d) => {
        data = d;
        loadedFor = projectId;
      })
      .catch((e: Error) => (error = e.message));
  });

  const layers = $derived(data ? Object.keys(data.allow) : []);
  const hasMatrix = $derived(layers.length > 0);
  const focusKnown = $derived(
    !layersPanel.focus || layers.includes(layersPanel.focus),
  );
</script>

<Modal
  open={layersPanel.open}
  title="Layer dependencies"
  width="460px"
  onclose={closeLayers}
>
  {#if error}
    <p class="error">{error}</p>
  {:else if !data}
    <p class="muted">Loading…</p>
  {:else if !hasMatrix}
    <p class="muted">
      No <code>layer-dependencies</code> rule found in this project's
      <code>rules.yaml</code>.
    </p>
  {:else}
    <p class="hint">
      Declared in <code>rules.yaml</code> — each layer and the layers it may
      reference. Same-layer references are always allowed.
    </p>
    <ul class="matrix">
      {#each layers as layer (layer)}
        <li class:focused={layer === layersPanel.focus}>
          <span class="layer">{layer}</span>
          <span class="arrow">→</span>
          {#if data.allow[layer].length}
            <span class="targets">
              {#each data.allow[layer] as t (t)}
                <span class="chip">{t}</span>
              {/each}
            </span>
          {:else}
            <span class="none">(none — leaf layer)</span>
          {/if}
        </li>
      {/each}
    </ul>
    {#if !focusKnown}
      <p class="muted note">
        Layer <code>{layersPanel.focus}</code> has no declared constraints.
      </p>
    {/if}
  {/if}
</Modal>

<style>
  .hint {
    margin: 0 0 0.75rem;
    font-size: 0.8rem;
    color: var(--muted, #64748b);
  }
  .matrix {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .matrix li {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    border-radius: 6px;
    background: var(--hover, #f1f5f9);
  }
  .matrix li.focused {
    outline: 2px solid var(--accent, #2563eb);
  }
  .layer {
    font-weight: 600;
    min-width: 5.5rem;
  }
  .arrow {
    color: var(--muted, #64748b);
  }
  .targets {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem;
  }
  .chip {
    background: #1d4ed8;
    color: #fff;
    font-size: 0.75rem;
    padding: 0.05rem 0.4rem;
    border-radius: 3px;
  }
  .none {
    color: var(--muted, #64748b);
    font-size: 0.8rem;
    font-style: italic;
  }
  .note {
    margin: 0.75rem 0 0;
    font-size: 0.8rem;
  }
  .muted {
    color: var(--muted, #64748b);
  }
  .error {
    color: #c63a3a;
  }
  code {
    background: var(--hover, #f1f5f9);
    padding: 0 0.25rem;
    border-radius: 3px;
  }
</style>
