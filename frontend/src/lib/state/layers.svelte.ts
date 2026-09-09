// Shared UI state for the layer-dependencies modal. Opened by clicking a
// `layer:` badge on a class node; the modal (mounted in DiagramViewer) reads
// this and fetches the allow-matrix. Mutators are free functions so they
// survive HMR (same pattern as `diagram.svelte.ts`).

export const layersPanel = $state<{ open: boolean; focus: string | null }>({
  open: false,
  focus: null,
});

export function openLayers(focus: string | null): void {
  layersPanel.focus = focus;
  layersPanel.open = true;
}

export function closeLayers(): void {
  layersPanel.open = false;
  layersPanel.focus = null;
}
