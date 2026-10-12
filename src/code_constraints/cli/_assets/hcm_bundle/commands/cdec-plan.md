---
description: Write an architecture-first work plan for a change, with a UML proposal for review
argumentHint: "[the feature, refactor or fix to plan]"
---

Write a work plan for this change: $ARGUMENTS

Use the `cdec-architecture-first` skill. Do Phases 1 to 3 now:

1. Analyse the class hierarchy and the constraints that apply to the change.
2. Write the target architecture as one JSON model file.
3. Show it with `cdec propose`, and give me the review summary.

Write the plan with the plan template of that skill. Put the architecture analysis and
the proposal first. Make each implementation task depend on the review gate.

Then stop. Do not write production code, do not run `cdec reference set`, and do not edit
`.cdec/rules.yaml` until I approve the proposal.
