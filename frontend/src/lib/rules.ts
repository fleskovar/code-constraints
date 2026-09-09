// Presentation map for architectural-rule tags — the frontend twin of the
// backend catalog in `src/code_constraints/core/rules.py`. Keep ids in sync with that file.

import type { ClassGraphRule } from "./api";

export interface RulePresentation {
  label: string; // short badge text
  color: string; // badge background
  summary: string; // tooltip line
}

const PRESENTATION: Record<string, RulePresentation> = {
  "no-instantiation": {
    label: "no-new",
    color: "#b45309",
    summary: "May not construct objects (except types in `allow`).",
  },
  "no-side-effects": {
    label: "pure",
    color: "#0e7490",
    summary: "Must be free of side effects.",
  },
  sealed: {
    label: "sealed",
    color: "#6d28d9",
    summary: "May not be subclassed.",
  },
  immutable: {
    label: "immut",
    color: "#0f766e",
    summary: "Fields may not be reassigned after construction.",
  },
  factory: {
    label: "factory",
    color: "#9d174d",
    summary: "Designated constructor of the types in `creates`.",
  },
  layer: {
    label: "layer",
    color: "#1d4ed8",
    summary: "Assigns the class to an architectural layer.",
  },
  locked: {
    label: "locked",
    color: "#a16207",
    summary:
      "Implementation is frozen — any semantic change fails `cdec lock check` until re-baselined.",
  },
};

const FALLBACK: RulePresentation = {
  label: "rule",
  color: "#475569",
  summary: "",
};

export function rulePresentation(id: string): RulePresentation {
  return PRESENTATION[id] ?? { ...FALLBACK, label: id };
}

/** The layer name carried by a `@layer("name")` tag, with quotes stripped.
 *  `args[0]` holds raw source text, so C# yields `"controller"` with quotes. */
export function layerName(rule: ClassGraphRule): string {
  const raw = rule.args[0] ?? "";
  return raw.replace(/^['"]|['"]$/g, "");
}

/** Badge text. The layer badge reads `layer: <name>`; everything else uses the
 *  short presentation label. */
export function ruleBadgeLabel(rule: ClassGraphRule): string {
  if (rule.name === "layer") {
    const name = layerName(rule);
    return name ? `layer: ${name}` : "layer";
  }
  return rulePresentation(rule.name).label;
}

/** Human-readable params string, e.g. `("domain")` or `(allow=['list'])`. */
export function ruleParams(rule: ClassGraphRule): string {
  const parts: string[] = [];
  for (const a of rule.args) parts.push(a);
  for (const [k, v] of Object.entries(rule.kwargs)) parts.push(`${k}=${v}`);
  return parts.length ? `(${parts.join(", ")})` : "";
}

/** Full tooltip text for a rule badge: name, params, and the summary line. */
export function ruleTooltip(rule: ClassGraphRule): string {
  const p = rulePresentation(rule.name);
  const params = ruleParams(rule);
  const head = `@${rule.name}${params}`;
  return p.summary ? `${head} — ${p.summary}` : head;
}
