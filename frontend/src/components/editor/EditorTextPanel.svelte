<script lang="ts">
  // Text/code view of the editor draft: the same JSON document `cdec convert`
  // and `cdec propose` consume, editable side-by-side with the canvas. Canvas
  // mutations re-serialize into the textarea; typing in the textarea parses
  // (debounced) back into the draft, so the two stay in lock-step whichever
  // side you edit.

  import type { ProjectDraft } from "../../lib/api";
  import {
    editorState,
    replaceProject,
  } from "../../lib/state/editor.svelte";

  let textarea: HTMLTextAreaElement | null = null;
  let text = $state("");
  let parseError = $state("");
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  // True while the latest text change originated in the textarea, so the
  // serialize-effect doesn't clobber what the user is typing.
  let typing = false;

  // Canvas/model → text. Re-runs on any draft mutation.
  $effect(() => {
    const snapshot = $state.snapshot(editorState.project);
    const serialized = JSON.stringify(snapshot, null, 2);
    if (typing) {
      // The mutation came from our own parse; keep the user's text as-is.
      typing = false;
      return;
    }
    if (document.activeElement !== textarea) {
      text = serialized;
      parseError = "";
    }
  });

  function onInput() {
    if (debounceTimer !== null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(applyText, 400);
  }

  function applyText() {
    debounceTimer = null;
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      parseError = `JSON: ${(e as Error).message}`;
      return;
    }
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      !Array.isArray((parsed as ProjectDraft).packages)
    ) {
      parseError = "model must be an object with a `packages` array";
      return;
    }
    const draft = parsed as ProjectDraft;
    draft.activities ??= [];
    draft.sequences ??= [];
    draft.associations ??= [];
    draft.source_language ??= "python";
    draft.root_path ??= "";
    parseError = "";
    typing = true;
    replaceProject(draft);
  }

  function onBlur() {
    // Flush a pending debounce so switching to the canvas applies the edit.
    if (debounceTimer !== null) {
      clearTimeout(debounceTimer);
      applyText();
    }
  }
</script>

<div class="code-panel">
  <div class="head">
    <span class="title">Model JSON</span>
    {#if parseError}
      <span class="parse-error" title={parseError}>⚠ {parseError}</span>
    {:else}
      <span class="ok">canvas in sync</span>
    {/if}
  </div>
  <textarea
    bind:this={textarea}
    bind:value={text}
    oninput={onInput}
    onblur={onBlur}
    spellcheck="false"
    autocomplete="off"
    autocapitalize="off"
  ></textarea>
</div>

<style>
  .code-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    border-left: 1px solid var(--border, #e2e8f0);
    background: var(--surface, #fff);
  }
  .head {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.6rem;
    border-bottom: 1px solid var(--border, #e2e8f0);
    font-size: 0.8rem;
  }
  .title {
    font-weight: 600;
  }
  .ok {
    color: var(--muted, #64748b);
  }
  .parse-error {
    color: #b45309;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  textarea {
    flex: 1;
    min-height: 0;
    width: 100%;
    box-sizing: border-box;
    resize: none;
    border: none;
    outline: none;
    padding: 0.6rem;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 11.5px;
    line-height: 1.45;
    color: var(--fg, #1a1a1a);
    background: var(--surface, #fff);
    white-space: pre;
  }
</style>
