---
description: Plans a change so that the architecture is agreed before the code is written. Analyse the class hierarchy and its constraints, propose the changes as a UML JSON model with `cdec propose`, get the approval of a senior developer, then implement. Use when you write a work plan, split work into tasks, or start a change that adds, removes, renames or moves a class, a public member or a dependency.
---

# Plan the architecture first

In a project that uses code-constraints (`cdec`), the class hierarchy is an agreed
contract. A change to the hierarchy is a design decision. A senior developer makes that
decision before the code changes, not in the code review afterwards.

Thus each work plan starts with the same three steps:

1. Analyse the changes that the class hierarchy needs, with the current constraints in view.
2. Propose those changes as a UML diagram for the senior developers.
3. Implement the logic only after they approve the proposal.

## When this skill applies

Use the full procedure when the change does one of these things:

- It adds, removes, renames or moves a class, an interface, an enum or a struct.
- It adds, removes or changes a public attribute or a public method signature.
- It changes a base class, or makes one class refer to a different class.
- It adds a dependency between two packages or two layers.
- It adds, removes or changes a constraint tag or a rule in `.cdec/rules.yaml`.

If the change stays in the body of existing methods and adds no reference between classes,
go to [Phase 5](#phase-5--implement). If you are not sure, do Phase 1. It is fast, and it
tells you the answer.

## The phases

| Phase | What you produce | What must be true before the next phase |
| --- | --- | --- |
| 1. Analyse | An impact analysis of the hierarchy and its constraints | You know each constraint that the change touches |
| 2. Model | One JSON model file of the target architecture | The model has only the changes that the task needs |
| 3. Propose | The diagram diff in the viewer, and a review summary | **A senior developer approves the current model** |
| 4. Lock | The approved model as `.cdec/reference.xmi`, and the agreed guardrails | The gate fails only on work that is still to do |
| 5. Implement | The structure first, then the logic | `cdec check` passes |
| 6. Verify | The final report | — |

Phases 1 to 3 change no production code. Phase 3 has a hard stop.

### Phase 1 — Analyse the hierarchy and its constraints

1. Run `cdec check`. Record the result. You must know which issues exist before your change.
2. Read `.cdec/rules.yaml`: the rules, the `exceptions:` section and the `locks:` section.
3. Export the current architecture as a model:

   ```bash
   cdec parse <source> --lang <language> --out .cdec/proposals/<change>.json
   ```

   Take `<source>` and `<language>` from the `source:` and `language:` settings in
   `.cdec/rules.yaml`. If the reference is ahead of the code, start from the reference:
   `cdec convert .cdec/reference.xmi .cdec/proposals/<change>.json`.
4. Find the classes that the change touches. For each class, read its bases, its
   subclasses, the classes that it refers to, and the classes that refer to it.
5. List the constraints on each of those classes:
   - The tags in the `rules` list of the class and of its operations.
   - The rules in `.cdec/rules.yaml` whose globs match the class or its package.
   - The layer of the class, and the `allow:` matrix of the `layer-dependencies` rule.
   - The `locks:` entries whose `target` is the class or one of its methods.
6. Put each necessary change in one of three groups:

   | Group | Meaning | What you do |
   | --- | --- | --- |
   | Free | No constraint applies. | Put the change in the model. |
   | Constrained | A constraint applies, and the design can obey it. | Design the change so that it obeys. Name the constraint in the plan. |
   | Conflict | The change breaks a constraint. | Find a design that obeys first. If there is none, give the conflict to the reviewer as a question. |

A conflict is a question for the reviewer. It is not a decision for you. Examples of a
conflict are a subclass of a `sealed` class, a change to a `@locked` body, a change to a
member under `frozen-members`, and a reference that a dependency rule forbids.

The `cdec-guardrails` skill tells you what each rule type and each tag means.

### Phase 2 — Write the proposal as a model

1. Edit the JSON model from Phase 1 until it shows the target architecture. The format is
   in the `cdec-architecture-loop` skill.
2. Add each new class with its package, its kind, its bases, its attributes and its
   public methods. Write why the class exists in its `description`.
3. Add the constraint tags that the new structure needs to the `rules` lists.
4. Keep one model file for the change. Do not make a second copy for each idea.
5. Change only what the task needs. A proposal that also renames unrelated classes is
   hard to review.
6. Write the new rules for `.cdec/rules.yaml` as text in the plan. Do not add them to the
   file yet.

### Phase 3 — Propose, and stop for approval

1. Show the model as a diff against the current code:

   ```bash
   cdec propose .cdec/proposals/<change>.json --focus pkg.ClassA,pkg.ClassB
   ```

   Green is what the code must add. Red is what the code must remove. The
   `cdec-architecture-loop` skill tells you how to run the viewer and how to iterate.
2. Give the reviewer a review summary with these parts:
   - The viewer URL and the path of the model file.
   - The classes and members that the proposal adds, removes and changes.
   - The constraints that apply, and how the design obeys each one.
   - Each conflict, with the options and your recommendation.
   - The new tags and the new rules that you propose as guardrails.
   - The open questions.
3. Change the model when the reviewer asks, and run `cdec propose` again. Repeat until the
   reviewer agrees.
4. **Stop here.** Do not write production code, do not run `cdec reference set`, and do not
   edit `.cdec/rules.yaml`. Continue only when a senior developer approves the current
   model in explicit words.

The approval of an earlier version does not apply to a changed model. If you changed the
model after the approval, ask again.

If no reviewer is available in this session, write the plan, set its status to "waits for
architecture approval", and end your work. On a task board, make the proposal and its
review the first task. Make each implementation task depend on it.

### Phase 4 — Lock the approved design

Do this phase on the work branch, after the approval.

1. Lock the model as the target architecture:

   ```bash
   cdec reference set .cdec/proposals/<change>.json
   ```

2. Add the approved rules to `.cdec/rules.yaml`. See the `cdec-guardrails` skill.
3. Run `cdec check`. The rules that compare the code with the reference now fail on each
   class, member and tag that the reference has and the code does not have. Those rules
   are `reference-architecture` and the rules with `scope: diff`. Their failures are your
   work list. The report says "was removed" for an element that the code does not have
   yet. Read that as "still to build".
4. If the project has none of those rules, the check does not show the work list. Run
   `cdec propose` again to see what is still green.
5. If the check also fails on something that is not in the proposal, stop and tell the
   reviewer. Do not record an exception to hide it.

### Phase 5 — Implement

1. Build the structure first: the classes, the signatures, the base classes and the
   constraint tags of the model. Give each method an empty body or a placeholder.
2. Run `cdec check`. Continue until no structural issue is left.
3. Write the logic in the method bodies, with its tests.
4. Run `cdec check` after each step. Use the `cdec-gate` skill when it fails.

If the implementation shows that the design must change, stop the implementation. Go back
to Phase 2, change the model, and get a new approval. Do not let the code and the approved
model become different. Do not run `cdec check --automatic-exceptions reference` to make
the difference go away.

### Phase 6 — Verify and report

1. Run `cdec check`. It must exit with code 0.
2. Report these items:
   - The result of the last `cdec check`, with the rules that it skipped.
   - Each exception that you recorded: the key, the reason, and who approved it.
   - Each difference between the approved model and the code. The correct number is zero.

## The shape of a work plan

A plan for a change in a `cdec` project has these sections, in this order. The template is
`./plan-template.md`.

1. **Architecture analysis.** The output of Phase 1.
2. **Proposed architecture.** The model file, the `cdec propose` command and the summary of
   the diff.
3. **Review gate.** Who approves, and the status of the approval.
4. **Lock and guardrails.** The `cdec reference set` command and the new rules.
5. **Implementation tasks.** Structure, then logic, then tests. Each task depends on the
   review gate.
6. **Verification.** `cdec check` passes.

A plan that starts with an implementation task is not complete.

## Rules

- Do not skip the review gate because the change looks small. If the change is truly
  small, the review is fast.
- Do not approve your own proposal. A subagent cannot approve it. A person approves it.
- Do not hide a conflict in the summary. Put each conflict where the reviewer sees it first.
- Prefer the design that obeys the current constraints to the design that needs a new
  exception.
