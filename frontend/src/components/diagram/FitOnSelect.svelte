<script lang="ts">
  import { useSvelteFlow } from "@xyflow/svelte";
  import { diagramState } from "../../lib/state/diagram.svelte";

  // Must be mounted inside <SvelteFlowProvider> so useSvelteFlow has context.
  const { fitView } = useSvelteFlow();

  $effect(() => {
    const id = diagramState.selectedClassId;
    if (!id) return;
    // Defer one tick so fitView doesn't write into SvelteFlow's internal node
    // store while we're still inside the user-state effect (which xyflow
    // otherwise warns about as a synchronous update during render).
    queueMicrotask(() => {
      void fitView({ nodes: [{ id }], padding: 0.3, duration: 400, maxZoom: 1.3 });
    });
  });

  // After a re-layout, refit the whole visible subgraph. We defer two ticks
  // so the position updates have propagated through bind:nodes and the new
  // node measurements are settled before fitView reads them.
  $effect(() => {
    const token = diagramState.relayoutToken;
    if (token === 0) return;
    queueMicrotask(() => {
      queueMicrotask(() => {
        void fitView({ padding: 0.2, duration: 500 });
      });
    });
  });
</script>
