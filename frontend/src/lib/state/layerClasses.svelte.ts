// Shared UI state for the layer-classes modal. Opened by right-clicking a
// `layer:` badge on a class node; the modal reads this to know which layer to
// show. Mutators follow the same free-function pattern as diagram.svelte.ts.

export const layerClassesPanel = $state<{ open: boolean; layerName: string | null }>({
  open: false,
  layerName: null,
});

export function openLayerClasses(name: string): void {
  layerClassesPanel.layerName = name;
  layerClassesPanel.open = true;
}

export function closeLayerClasses(): void {
  layerClassesPanel.open = false;
  layerClassesPanel.layerName = null;
}
