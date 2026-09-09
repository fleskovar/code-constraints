// Presentation map for class-node kinds — colour-coding so types are
// distinguishable at a glance, especially when zoomed out. Shared by
// `ClassNode.svelte` (node styling) and `DiagramLegend.svelte` (the legend) so
// the two stay in sync. Mirrors the pattern of `lib/rules.ts`.

export interface KindPresentation {
  label: string; // legend label
  color: string; // accent stripe / kind-tag colour
  tint: string; // light header background
}

export const KIND_PRESENTATION: Record<string, KindPresentation> = {
  class: { label: "Class", color: "#2563eb", tint: "#eff4ff" },
  interface: { label: "Interface", color: "#0d9488", tint: "#ecfeff" },
  abstract: { label: "Abstract class", color: "#7c3aed", tint: "#f5f3ff" },
  enum: { label: "Enum", color: "#b45309", tint: "#fff7ed" },
  struct: { label: "Struct", color: "#be185d", tint: "#fdf2f8" },
  record: { label: "Record", color: "#15803d", tint: "#f0fdf4" },
  static: { label: "Static class", color: "#65a30d", tint: "#f7fee7" },
  external: { label: "External", color: "#64748b", tint: "#f8fafc" },
};

/** Insertion order of `KIND_PRESENTATION`, for the legend. */
export const KIND_ORDER = Object.keys(KIND_PRESENTATION);

export function kindPresentation(kind: string): KindPresentation {
  return KIND_PRESENTATION[kind] ?? KIND_PRESENTATION.class;
}
