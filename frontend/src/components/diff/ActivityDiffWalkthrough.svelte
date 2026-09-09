<script lang="ts">
  import type { DiagramChange } from "../../lib/api";
  import { diagramState, setSelected } from "../../lib/state/diagram.svelte";

  let {
    changes,
    activityName,
    onpick,
  }: {
    changes: DiagramChange[];
    activityName: string;
    onpick?: (name: string) => void;
  } = $props();

  const current = $derived(
    changes.find((c) => c.diagramName === activityName) ?? null,
  );

  const currentIdx = $derived(
    current ? changes.findIndex((c) => c.diagramName === current.diagramName) : -1,
  );

  function step(delta: number) {
    if (changes.length === 0) return;
    const next =
      currentIdx < 0
        ? delta > 0
          ? 0
          : changes.length - 1
        : (currentIdx + delta + changes.length) % changes.length;
    const target = changes[next];
    onpick?.(target.diagramName);
    setSelected(null);
  }

  function pickNode(nodeId: string | undefined) {
    if (!nodeId) return;
    setSelected(nodeId);
  }
</script>

<div class="walk">
  <header>
    <h4>Activity changes ({changes.length})</h4>
    <div class="nav">
      <button onclick={() => step(-1)} title="Previous activity">‹</button>
      <span class="pos">
        {currentIdx < 0 ? "—" : currentIdx + 1} / {changes.length}
      </span>
      <button onclick={() => step(1)} title="Next activity">›</button>
    </div>
  </header>
  <ul>
    {#each changes as c (c.diagramId)}
      <li>
        <button
          class="row {c.kind}"
          class:active={c.diagramName === activityName}
          onclick={() => onpick?.(c.diagramName)}
          title={c.diagramName}
        >
          <span class="badge {c.kind}">{c.kind[0].toUpperCase()}</span>
          <span class="summary">{c.summary}</span>
        </button>
        {#if c.members.length && c.diagramName === activityName}
          <ul class="members">
            {#each c.members as m, i (i + "|" + m.kind + "|" + m.signature + "|" + m.status)}
              <li class="member {m.status}">
                <button
                  class="member-btn"
                  onclick={() => pickNode(m.nodeId)}
                  disabled={!m.nodeId}
                  title={m.nodeId ? "Focus on canvas" : "Edge — no node focus"}
                >
                  <span class="sign">{m.status === "added" ? "+" : "−"}</span>
                  <span class="kind">{m.kind}</span>
                  <code>{m.signature}</code>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </li>
    {/each}
  </ul>
</div>

<style>
  .walk {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }
  header h4 {
    margin: 0;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
    flex: 1;
  }
  .nav {
    display: flex;
    align-items: center;
    gap: 0.25rem;
  }
  .nav button {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 4px;
    width: 1.6rem;
    height: 1.6rem;
    cursor: pointer;
    color: var(--fg);
  }
  .nav button:hover {
    background: var(--hover);
  }
  .pos {
    font-size: 0.75rem;
    color: var(--muted);
    min-width: 3rem;
    text-align: center;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0.25rem 0;
    overflow-y: auto;
    flex: 1;
    min-height: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    padding: 0.3rem 0.75rem;
    background: transparent;
    border: none;
    text-align: left;
    cursor: pointer;
    color: var(--fg);
    font-size: 0.85rem;
  }
  .row:hover {
    background: var(--hover);
  }
  .row.active {
    background: var(--accent);
    color: white;
  }
  .row.active .badge {
    background: rgba(255, 255, 255, 0.25);
    color: white;
  }
  .badge {
    flex-shrink: 0;
    display: inline-block;
    width: 1.4em;
    height: 1.4em;
    line-height: 1.4em;
    text-align: center;
    border-radius: 3px;
    font-size: 0.7rem;
    font-weight: 700;
  }
  .badge.added {
    background: #daf7dc;
    color: #166534;
  }
  .badge.removed {
    background: #fbd7d7;
    color: #991b1b;
  }
  .badge.changed {
    background: #fff6cc;
    color: #92400e;
  }
  .members {
    list-style: none;
    margin: 0;
    padding: 0 0.75rem 0.4rem 2.5rem;
  }
  .member {
    font-size: 0.75rem;
    font-family: ui-monospace, SFMono-Regular, monospace;
    line-height: 1.4;
  }
  .member-btn {
    background: transparent;
    border: none;
    padding: 0.1rem 0;
    cursor: pointer;
    color: inherit;
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    text-align: left;
  }
  .member-btn:disabled {
    cursor: default;
  }
  .member-btn:not(:disabled):hover code {
    text-decoration: underline;
  }
  .member.added {
    color: #166534;
  }
  .member.removed {
    color: #991b1b;
    text-decoration: line-through;
  }
  .member .kind {
    color: var(--muted);
    font-size: 0.65rem;
    text-transform: uppercase;
  }
  .member .sign {
    width: 0.7em;
    text-align: center;
    flex-shrink: 0;
  }
</style>
