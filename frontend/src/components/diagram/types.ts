import type { Node } from "@xyflow/svelte";
import type { ClassGraphNode } from "../../lib/api";

// Optional per-node highlight hints set only by the edge-focus popup: which
// rows of this node participate in the focused edge. Absent on the main canvas.
export interface EdgeHighlight {
  /** Attribute signatures to emphasise. */
  highlightAttributes?: string[];
  /** Operation signatures to emphasise. */
  highlightOperations?: string[];
  /** Emphasise the header (the edge comes from an inheritance base). */
  highlightHeader?: boolean;
}

// SvelteFlow requires node data to extend Record<string, unknown>.
// ClassGraphNode has a known shape but at runtime its plain-object values
// satisfy that constraint — we intersect for the typing seam.
export type ClassNodeData = ClassGraphNode & EdgeHighlight & Record<string, unknown>;
export type ClassFlowNode = Node<ClassNodeData, "class">;
