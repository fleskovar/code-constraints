# Work plan: <name of the change>

**Status:** waits for architecture approval | approved | in implementation | complete

## 1. Architecture analysis

**Goal of the change:** <one or two sentences>

**State of the gate before the change:** `cdec check` → <pass | the list of issue keys>

**Classes that the change touches:**

| Class | Why the change touches it | Bases and subclasses | Refers to / referred to by |
| --- | --- | --- | --- |
| `pkg.ClassA` | | | |

**Constraints that apply:**

| Constraint | Where it is | Applies to | Group | How the design obeys, or the conflict |
| --- | --- | --- | --- | --- |
| `sealed` tag | `pkg.ClassA` | `pkg.ClassA` | Constrained | The new class holds a `ClassA`. It does not extend it. |
| `layering` rule (`layer-dependencies`) | `.cdec/rules.yaml` | `domain` → `infrastructure` | Conflict | See question 1. |

Group is Free, Constrained or Conflict.

## 2. Proposed architecture

**Model file:** `.cdec/proposals/<change>.json`

**Review command:**

```bash
cdec propose .cdec/proposals/<change>.json --focus pkg.ClassA,pkg.ClassB
```

**Summary of the diff:**

| Change | Element | Reason |
| --- | --- | --- |
| Add | `pkg.NewClass` (class, layer `domain`) | |
| Change | `pkg.ClassA.method(x: int) -> str` | |
| Remove | `pkg.OldClass` | |

**Proposed guardrails:**

| Guardrail | Type | What it protects |
| --- | --- | --- |
| `@immutable` + `@sealed` on `pkg.NewClass` | tags | The class is a value object. |
| `new-adapters-end-in-adapter` | `subclass-naming` rule | The role of each adapter is clear from its name. |

**Conflicts and open questions for the reviewer:**

1. <the conflict, the options, your recommendation>

## 3. Review gate

- **Reviewer:** <name or role of the senior developer>
- **Approval:** <not yet | approved on DATE by NAME, for the model at commit HASH>

No task below starts before this approval.

## 4. Lock and guardrails

- [ ] `cdec reference set .cdec/proposals/<change>.json`
- [ ] Add the approved rules to `.cdec/rules.yaml`
- [ ] `cdec check` fails only on the elements of the summary in section 2

## 5. Implementation tasks

Each task depends on section 3.

- [ ] **Structure.** Create the classes, signatures, base classes and tags of the model,
      with empty bodies. `cdec check` shows no structural issue.
- [ ] **Logic.** <one task for each unit of behaviour, each with its tests>
- [ ] **Clean up.** Remove the elements that the diff shows in red.

## 6. Verification

- [ ] `cdec check` exits with code 0
- [ ] The report lists each recorded exception, with its key, its reason and its approver
- [ ] The code and the approved model have no difference
