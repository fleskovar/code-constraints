## Architecture constraints (code-constraints)

This project uses code-constraints (`cdec`) to gate its architecture. The contract is
`.cdec/rules.yaml` and `.cdec/reference.xmi`. The gate is `cdec check`.

- **Plan the architecture first.** Use the `cdec-architecture-first` skill before you write
  a work plan, and before you add, remove, rename or move a class, a public member or a
  dependency. The first step of each plan is the analysis of the class hierarchy and of
  its constraints. The second step is a proposal as a UML JSON model, shown with
  `cdec propose`. Do not write the implementation until a senior developer approves the
  proposal.
- **Run the gate.** Run `cdec check` before you start and after each change. Do not report
  a task as complete while `cdec check` fails. Use the `cdec-gate` skill when it fails.
- **Do not weaken a constraint to pass the gate.** Without the approval of a person, do
  not delete a constraint tag, edit a rule, add an `ignore:` glob or record an exception.
- **Do not change locked code.** A `@locked` implementation changes only when a lead
  approves it. Do not run `cdec check --automatic-exceptions locks --force` or
  `cdec check --bypass-locks` on your own initiative.
- **Ask before you change the contract.** `cdec reference set`,
  `cdec check --automatic-exceptions` and `cdec exceptions allow` change what the gate
  accepts. Run them only after explicit approval.
- **Add guardrails with the catalogue.** Use the `cdec-guardrails` skill to write a rule or
  a constraint tag. If the project has no `.cdec/` folder, that skill tells you how to
  create it.
