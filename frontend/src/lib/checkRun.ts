// The result of one `cdec check` run as rows to filter and group, and the
// change since the run before. Pure, so it runs under plain node.
// Self-check: node src/lib/checkRun.check.ts
import type { CheckResult, CheckViolation } from "./api";

/** `open` fails the check (if its severity is at or above fail-on),
 *  `accepted` is in the exceptions list, `bypassed` is a lock that the run
 *  did not enforce. */
export type RowState = "open" | "accepted" | "bypassed";

export interface IssueRow {
  violation: CheckViolation;
  state: RowState;
  /** Not reported open by the run before. False when there is no run before. */
  isNew: boolean;
}

export type GroupBy = "rule" | "element" | "file";

export interface RowFilter {
  query: string;
  severities: Set<string>;
  states: Set<RowState>;
}

const openKeys = (r: CheckResult) => new Set(r.report.violations.map((v) => v.key));

/** Every violation of the run, open ones first. */
export function issueRows(result: CheckResult, previous: CheckResult | null): IssueRow[] {
  const before = previous ? openKeys(previous) : null;
  const row = (state: RowState) => (violation: CheckViolation): IssueRow => ({
    violation,
    state,
    isNew: state === "open" && before !== null && !before.has(violation.key),
  });
  return [
    ...result.report.violations.map(row("open")),
    ...result.report.bypassed.map(row("bypassed")),
    ...result.report.suppressed.map(row("accepted")),
  ];
}

/** The open issues that the run before had and this run does not, and the new ones. */
export function changeSince(
  previous: CheckResult,
  current: CheckResult,
): { fixed: CheckViolation[]; added: CheckViolation[] } {
  const now = openKeys(current);
  const was = openKeys(previous);
  return {
    fixed: previous.report.violations.filter((v) => !now.has(v.key)),
    added: current.report.violations.filter((v) => !was.has(v.key)),
  };
}

export function filterRows(rows: IssueRow[], f: RowFilter): IssueRow[] {
  const q = f.query.trim().toLowerCase();
  return rows.filter((r) => {
    if (!f.states.has(r.state) || !f.severities.has(r.violation.severity)) return false;
    if (!q) return true;
    const v = r.violation;
    return [v.key, v.rule_id, v.qualified_name, v.message, v.location?.file ?? ""].some((s) =>
      s.toLowerCase().includes(q),
    );
  });
}

/** The group of a row. A violation with no file goes in "(no file)". */
export function groupKey(row: IssueRow, by: GroupBy): string {
  const v = row.violation;
  if (by === "rule") return v.rule_id;
  if (by === "element") return v.qualified_name;
  return v.location?.file ?? "(no file)";
}

/** Rows in groups, in the order of the first row of each group. */
export function groupRows(rows: IssueRow[], by: GroupBy): [string, IssueRow[]][] {
  const groups = new Map<string, IssueRow[]>();
  for (const r of rows) {
    const k = groupKey(r, by);
    groups.set(k, [...(groups.get(k) ?? []), r]);
  }
  return [...groups.entries()];
}

/** The class that an issue is about: the qualified name itself, or the
 *  longest class name that it starts with (`orders.Receipt.formatted` is about
 *  `orders.Receipt`). Null when no class matches. */
export function classOf(qualifiedName: string, classes: Iterable<string>): string | null {
  let best: string | null = null;
  for (const c of classes) {
    const match = qualifiedName === c || qualifiedName.startsWith(c + ".");
    if (match && (best === null || c.length > best.length)) best = c;
  }
  return best;
}
