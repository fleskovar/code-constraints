<script lang="ts">
  import { tick } from "svelte";
  import { useSvelteFlow, type Node } from "@xyflow/svelte";
  import { api } from "../../lib/api";
  import {
    hideMany,
    notify,
    selectedIds,
    setSelected,
  } from "../../lib/state/diagram.svelte";

  // The menu a right click on a canvas node opens. Must be mounted inside
  // <SvelteFlowProvider>. The canvas calls `open(event, node)` from
  // `onnodecontextmenu`.
  //
  // `allIds` is every node id of the diagram (Hide needs it while no filter is
  // set). `xmiId` turns on the two file items: only a class has a source file.
  let { allIds, xmiId }: { allIds: string[]; xmiId?: string } = $props();

  const { fitView } = useSvelteFlow();

  interface Target {
    id: string;
    name: string;
    file: string | null;
    /** What Hide and Focus act on: the selection when the node is part of it. */
    ids: string[];
  }

  let menu = $state<{ x: number; y: number; target: Target } | null>(null);
  let el: HTMLElement | undefined = $state();

  export async function open(event: MouseEvent | TouchEvent, node: Node) {
    event.preventDefault();
    const selected = selectedIds();
    // A right click on a node outside the selection selects that node, as a
    // file manager does. Inside the selection it keeps the selection.
    const inSelection = selected.includes(node.id);
    if (!inSelection) setSelected(node.id, false);
    const data = node.data as { name?: string; location?: { file?: string } | null };
    const at = "clientX" in event ? event : event.changedTouches[0];
    menu = {
      x: at.clientX,
      y: at.clientY,
      target: {
        id: node.id,
        name: data.name ?? node.id,
        file: data.location?.file ?? null,
        ids: inSelection ? selected : [node.id],
      },
    };
    await tick();
    if (!menu || !el) return;
    // Keep the menu on the screen, then give it the keyboard.
    const r = el.getBoundingClientRect();
    menu.x = Math.max(4, Math.min(menu.x, window.innerWidth - r.width - 4));
    menu.y = Math.max(4, Math.min(menu.y, window.innerHeight - r.height - 4));
    items()[0]?.focus();
  }

  function close() {
    menu = null;
  }

  const items = () => [...(el?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [])];

  // Run an item, then close. `action` gets the target the menu was opened on.
  function run(action: (t: Target) => void) {
    const target = menu?.target;
    close();
    if (target) action(target);
  }

  const hide = (t: Target) => hideMany(t.ids, allIds);

  // No `duration`: see FitOnSelect.svelte.
  const focus = (t: Target) =>
    void fitView({ nodes: t.ids.map((id) => ({ id })), padding: 0.3, maxZoom: 1.3 });

  function onFile(action: "reveal" | "open") {
    return (t: Target) => {
      if (!xmiId) return;
      api
        .nodeDesktopAction(xmiId, t.id, action)
        .then(() => notify(action === "reveal" ? `Shown in the file explorer: ${t.file}` : `Opened: ${t.file}`))
        .catch((e: Error) => notify(e.message, 6000));
    };
  }

  // The menu owns the keyboard while it is open: a key must not reach the
  // canvas shortcuts (`h` would hide, Tab would change the selection).
  function onKey(e: KeyboardEvent) {
    e.stopPropagation();
    if (e.key === "Escape" || e.key === "Tab") {
      e.preventDefault();
      close();
      return;
    }
    const list = items();
    const i = list.indexOf(document.activeElement as HTMLButtonElement);
    let next = -1;
    if (e.key === "ArrowDown") next = (i + 1) % list.length;
    else if (e.key === "ArrowUp") next = (i - 1 + list.length) % list.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = list.length - 1;
    if (next < 0) return;
    e.preventDefault();
    list[next]?.focus();
  }

  // A press outside the menu closes it. So does a scroll or a zoom: the node
  // moves away from under the menu.
  function onOutside(e: Event) {
    if (menu && !(e.target instanceof Element && el?.contains(e.target))) close();
  }
</script>

<svelte:window onpointerdown={onOutside} onwheel={onOutside} onblur={close} onresize={close} />

{#if menu}
  {@const t = menu.target}
  {@const many = t.ids.length > 1}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="node-menu"
    role="menu"
    aria-label="Actions for {t.name}"
    tabindex="-1"
    bind:this={el}
    style="left:{menu.x}px;top:{menu.y}px"
    onkeydown={onKey}
    oncontextmenu={(e) => e.preventDefault()}
  >
    <div class="title" title={t.name}>{many ? `${t.ids.length} elements` : t.name}</div>
    <button role="menuitem" onclick={() => run(hide)}>
      <span>Hide</span><kbd>h</kbd>
    </button>
    <button role="menuitem" onclick={() => run(focus)}>
      <span>Focus</span><kbd>f</kbd>
    </button>
    {#if xmiId}
      <hr />
      <button
        role="menuitem"
        disabled={!t.file}
        title={t.file ?? "No source file is recorded for this element"}
        onclick={() => run(onFile("reveal"))}
      >
        <span>Reveal in file explorer</span>
      </button>
      <button
        role="menuitem"
        disabled={!t.file}
        title={t.file ?? "No source file is recorded for this element"}
        onclick={() => run(onFile("open"))}
      >
        <span>Open in editor</span>
      </button>
    {/if}
  </div>
{/if}

<style>
  .node-menu {
    position: fixed;
    z-index: 50;
    min-width: 13rem;
    padding: 0.25rem;
    background: var(--surface, #fff);
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 6px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
    font-size: 0.82rem;
  }
  .node-menu:focus {
    outline: none;
  }
  .title {
    padding: 0.2rem 0.5rem 0.3rem;
    max-width: 18rem;
    font-weight: 600;
    color: var(--muted, #6b7280);
    font-size: 0.72rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  button {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1.2rem;
    width: 100%;
    padding: 0.3rem 0.5rem;
    border: none;
    border-radius: 4px;
    background: transparent;
    font: inherit;
    color: var(--fg, #1a1a1a);
    text-align: left;
    cursor: pointer;
    white-space: nowrap;
  }
  button:hover:not(:disabled),
  button:focus-visible {
    background: var(--hover, #f1f5f9);
    outline: none;
  }
  button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  kbd {
    font: inherit;
    font-size: 0.7rem;
    border: 1px solid var(--border, #e5e7eb);
    border-radius: 3px;
    padding: 0 0.3rem;
    color: var(--muted, #6b7280);
  }
  hr {
    border: none;
    border-top: 1px solid var(--border, #e5e7eb);
    margin: 0.25rem 0;
  }
</style>
