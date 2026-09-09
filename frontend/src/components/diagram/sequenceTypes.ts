import type { Node } from "@xyflow/svelte";
import type { SequenceLifeline } from "../../lib/api";

export type LifelineNodeData = SequenceLifeline & {
  rowCount: number;
  headerH: number;
  rowH: number;
} & Record<string, unknown>;

export type LifelineFlowNode = Node<LifelineNodeData, "lifeline">;

export type MessageEdgeData = {
  label: string;
  guard: string;
  isReturn: boolean;
  status: "unchanged" | "added" | "removed" | "changed";
  selfCall: boolean;
};

export type FragmentNodeData = {
  kind: "alt" | "opt" | "loop";
  label: string;
  width: number;
  height: number;
  status: "unchanged" | "added" | "removed" | "changed";
} & Record<string, unknown>;
