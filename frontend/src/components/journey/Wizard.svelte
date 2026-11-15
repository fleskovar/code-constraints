<script lang="ts">
  // The frame of every wizard: the title, the steps with the current one
  // marked, the body, and Back / Next. The wizard that uses it owns the steps
  // and says what Next does. An error from Next stays on the step.
  import "./journey.css";
  import type { Snippet } from "svelte";

  export interface NextAction {
    label: string;
    disabled?: boolean;
    /** Runs before the step changes. A thrown error keeps the step. */
    run?: () => Promise<void> | void;
    /** Do not go to the next step after `run`: the wizard changed it. */
    stay?: boolean;
  }

  let {
    title,
    steps,
    step = $bindable(0),
    next,
    onclose,
    children,
  }: {
    title: string;
    steps: string[];
    step?: number;
    /** `null`: the last step. The footer shows Close only. */
    next: NextAction | null;
    onclose: () => void;
    children: Snippet;
  } = $props();

  let busy = $state(false);
  let error = $state("");

  async function goNext() {
    if (!next) return;
    busy = true;
    error = "";
    try {
      await next.run?.();
      if (!next.stay) step = Math.min(steps.length - 1, step + 1);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  function back() {
    error = "";
    step = Math.max(0, step - 1);
  }
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onclose()} />

<div class="backdrop" role="presentation"></div>
<div class="jy wizard" role="dialog" aria-modal="true" aria-label={title}>
  <header>
    <h2>{title}</h2>
    <button class="close" aria-label="Close" onclick={onclose}>×</button>
  </header>
  <ol class="steps" aria-label="Steps">
    {#each steps as name, i (name)}
      <li class:current={i === step} class:past={i < step} aria-current={i === step ? "step" : undefined}>
        <span class="num">{i < step ? "✓" : i + 1}</span>
        {name}
      </li>
    {/each}
  </ol>
  <div class="body">
    {@render children()}
    {#if error}<p class="error" role="alert">{error}</p>{/if}
  </div>
  <footer>
    <button onclick={onclose}>{next ? "Cancel" : "Close"}</button>
    <span class="spacer"></span>
    {#if step > 0 && next}
      <button onclick={back} disabled={busy}>Back</button>
    {/if}
    {#if next}
      <button class="primary" onclick={goNext} disabled={busy || next.disabled}>
        {busy ? "Working…" : next.label}
      </button>
    {/if}
  </footer>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.45);
    z-index: 60;
  }
  .wizard {
    position: fixed;
    top: 5vh;
    left: 50%;
    transform: translateX(-50%);
    width: min(56rem, 94vw);
    max-height: 90vh;
    z-index: 61;
    background: var(--surface);
    border-radius: 8px;
    box-shadow: 0 20px 50px rgba(15, 23, 42, 0.35);
    display: flex;
    flex-direction: column;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem 0.5rem;
  }
  header h2 {
    margin: 0;
  }
  .close {
    border: none;
    background: transparent;
    font-size: 1.3rem;
    line-height: 1;
    color: var(--muted);
  }
  .steps {
    list-style: none;
    display: flex;
    gap: 1rem;
    margin: 0;
    padding: 0 1rem 0.6rem;
    border-bottom: 1px solid var(--border);
    color: var(--muted);
    font-size: 0.85rem;
    flex-wrap: wrap;
  }
  .steps li {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
  .steps li.current {
    color: var(--fg);
    font-weight: 600;
  }
  .num {
    width: 1.35rem;
    height: 1.35rem;
    border-radius: 50%;
    background: var(--hover);
    display: grid;
    place-items: center;
    font-size: 0.75rem;
  }
  .current .num {
    background: var(--accent);
    color: white;
  }
  .past .num {
    background: #dcfce7;
    color: #166534;
  }
  .body {
    padding: 1rem;
    overflow-y: auto;
    flex: 1;
    min-height: 12rem;
  }
  footer {
    display: flex;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-top: 1px solid var(--border);
  }
  .spacer {
    flex: 1;
  }
</style>
