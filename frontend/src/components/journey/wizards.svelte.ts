// The wizard that is open, as module-level state. Any page opens a wizard with
// `openWizard`; `WizardHost` in App renders it. `done` counts the wizards that
// changed the project, so a page reads it in an effect and loads again.
import type { RuleRow } from "../../lib/api";

export type WizardSpec =
  /** Add a rule. `type` starts on the form of that rule type. */
  | { kind: "rule"; type?: string }
  /** Change a rule that is in rules.yaml. */
  | { kind: "edit-rule"; rule: RuleRow }
  /** Put a constraint tag on a class or a method. */
  | { kind: "tag"; tag?: string }
  /** Make the code of today the reference. An open goal closes. */
  | { kind: "accept-code" }
  /** Put the check in CI, and set up a coding agent. */
  | { kind: "automate" };

export const wizards = $state<{ active: WizardSpec | null; done: number }>({
  active: null,
  done: 0,
});

export function openWizard(spec: WizardSpec): void {
  wizards.active = spec;
}

/** A page changed the project with no wizard: the other pages load again. */
export function projectChanged(): void {
  wizards.done += 1;
}

export function closeWizard(changed = false): void {
  wizards.active = null;
  if (changed) wizards.done += 1;
}
