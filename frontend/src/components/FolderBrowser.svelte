<script lang="ts">
  // Choose a folder of this machine. The server lists the folders: a browser
  // cannot give a page the path of a folder.
  import "./journey/journey.css";
  import { api, type FolderListing } from "../lib/api";
  import Modal from "./editor/Modal.svelte";

  let {
    start = "",
    onpick,
    onclose,
  }: {
    /** The folder to open on. Empty, or not a folder: the folder of the viewer. */
    start?: string;
    onpick: (path: string) => void;
    onclose: () => void;
  } = $props();

  let listing = $state<FolderListing | null>(null);
  let error = $state("");

  async function go(path: string) {
    try {
      listing = await api.folders(path);
      error = "";
    } catch (e) {
      error = (e as Error).message;
    }
  }
  // A half-typed path is not a folder. Start from the folder of the viewer.
  api
    .folders(start)
    .catch(() => api.folders())
    .then((l) => (listing = l))
    .catch((e: Error) => (error = e.message));
</script>

<Modal open title="Choose a folder" width="640px" {onclose}>
  <div class="jy browser">
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    {#if listing}
      <div class="row">
        <button
          onclick={() => go(listing!.parent!)}
          disabled={listing.parent === null}
          title="The folder that holds this one">↑ Up</button
        >
        <code class="here" title={listing.path}>{listing.path}</code>
      </div>
      <div class="row roots">
        <span class="muted">Go to</span>
        {#each listing.roots as root (root)}
          <button onclick={() => go(root)}>{root}</button>
        {/each}
      </div>
      <ul class="folders" aria-label="Folders in {listing.path}">
        {#each listing.folders as folder (folder.path)}
          <li>
            <button class="folder" onclick={() => go(folder.path)}>
              <span aria-hidden="true">📁</span>
              <span class="name">{folder.name}</span>
              {#if folder.project}<span class="badge goal">cdec project</span>{/if}
            </button>
          </li>
        {:else}
          <li class="muted empty">This folder has no folder in it.</li>
        {/each}
      </ul>
    {:else if !error}
      <p class="muted">Loading…</p>
    {/if}
  </div>
  {#snippet footer()}
    <div class="jy row">
      <button onclick={onclose}>Cancel</button>
      <button class="primary" disabled={!listing} onclick={() => onpick(listing!.path)}>
        Use this folder
      </button>
    </div>
  {/snippet}
</Modal>

<style>
  .browser {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    min-height: 22rem;
  }
  .here {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 0.25rem 0.4rem;
  }
  .folders {
    list-style: none;
    margin: 0;
    padding: 0;
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow-y: auto;
    max-height: 50vh;
    flex: 1;
  }
  .folder {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    text-align: left;
    border: 0;
    border-bottom: 1px solid var(--border);
    border-radius: 0;
  }
  .name {
    flex: 1;
  }
  .empty {
    padding: 0.6rem;
  }
</style>
