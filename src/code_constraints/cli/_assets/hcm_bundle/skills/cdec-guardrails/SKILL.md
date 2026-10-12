---
description: Builds guardrails with code-constraints, as rule entries in `.cdec/rules.yaml` and as constraint tags in the code. Gives each rule type with its options, each tag in each language, and a cookbook of patterns such as layers, ports and adapters, factory, value object and frozen implementation. Use when you add or change a rule or a tag, set up cdec in a project, or turn a design decision into a check.
---

# Build guardrails and constraints

A guardrail turns a design decision into a check that `cdec check` runs. A constraint has
one of two homes:

| Home | Use it for | Example |
| --- | --- | --- |
| A rule in `.cdec/rules.yaml` | A law about the architecture as a whole | "The domain does not depend on the UI." |
| A tag in the code | A law about one class or one method | "Nothing extends `Receipt`." |

The reference files of this skill:

- `./rules.md` — each rule type, with its options, its message placeholders and an example.
- `./tags.md` — each constraint tag, in each language, and what enforces it.
- `./patterns.md` — the cookbook: one recipe for each common pattern.

## Set up a project

Do these steps one time, if the project has no `.cdec/` folder.

1. Install the tool: `pip install code-constraints`.
2. Create the configuration: `cdec init --lang <language> --source <source folder>`.
   This writes `.cdec/rules.yaml` with an empty rule list, and `.cdec/reference.xmi`.
3. For a language with tags, copy the shim: `cdec update-assets --no-agents`. The command
   reads the language from `.cdec/rules.yaml`. Use `--lang` to set a different one.
   Put the shim file where the code can import it.
4. Commit the `.cdec/` folder and the shim.

`<language>` is one of `python`, `csharp`, `typescript`, `svelte`, `odin`, `lua`, `julia`.
An empty rule list enforces nothing. Each rule is opt-in.

## Add a guardrail

1. Write the decision as one sentence. Example: "Only `ReceiptFactory` constructs a `Receipt`."
2. Find the mechanism in the table below. Then read its recipe in `./patterns.md`.
3. Write the rule entry or the tag. Give each rule a `message:` that teaches.
4. Run `cdec check`.
5. Decide what to do with the issues that already exist. See
   [Existing violations](#existing-violations).
6. If you added a tag, make sure that a `frozen-rules` rule protects it.
7. Commit `.cdec/rules.yaml`, `.cdec/reference.xmi` and the tagged code together.

A new guardrail changes the gate for each developer. Propose it first and get the approval
of a senior developer. In a work plan, the proposal of the guardrails is part of the
architecture proposal. See the `cdec-architecture-first` skill.

## Choose the mechanism

| You want to say | Use |
| --- | --- |
| "This package is at the bottom of the dependency graph." | `forbidden-package-references` |
| "The layers depend only downward", and the layers are the folders | `forbidden-package-references` |
| "The layers depend only downward", and the layers are not the folders | `layer` tag + `layer-dependencies` |
| "This class must not know that class." | `forbidden-references` |
| "The packages stay independent." | `no-cyclic-package-dependencies` |
| "This interface is a published contract." | `frozen-members` |
| "No public class disappears." | `no-removed-classes` |
| "Each new class in this subsystem goes through design review." | `no-new-classes` |
| "There is one way to construct this type." | `factory` tag + `no-instantiation` tag + `tag-conformance` |
| "This service wires its collaborators. It does not build them." | `no-instantiation` tag + `tag-conformance` |
| "This is a value object." | `immutable` tag + `sealed` tag + `tag-conformance` |
| "Nobody extends this class." | `sealed` tag + `tag-conformance` |
| "The name tells the role." | `subclass-naming` |
| "No class becomes a hub." | `max-class-fanout` |
| "Delete the dead code." | `dangling-classes` |
| "Nobody deletes a constraint to make a change pass." | `frozen-rules` |
| "This function is settled. Nobody changes it." | `locked` tag + `implementation-locks` |
| "Nothing in the public shape changes without review." | `reference-architecture` |

## Anatomy of a rule

```yaml
rules:
  - id: catalog-is-a-leaf-package          # unique and stable; the heading in the report
    type: forbidden-package-references     # the rule type, from ./rules.md
    severity: error                        # error | warning | off
    scope: snapshot                        # diff | snapshot; each type has a default
    message: |                             # printed when the rule fires
      Layering violation: '{source}' must not depend on '{target}'.
      `catalog` is pure domain data. Move the reference to the package
      that owns the workflow.
    ignore:                                # qualified-name globs that are exempt
      - "catalog.legacy.**"
    from: ["catalog"]                      # the options of the rule type
    to:   ["orders", "users"]
```

- `scope: snapshot` looks at the current code only.
- `scope: diff` compares the code with a baseline. The baseline is `.cdec/reference.xmi`,
  or the git revision of `--base-ref`. With no baseline, the rule is skipped, not passed.
- In a glob, `*` matches any text, dots included. `orders.**` matches `orders` and each
  descendant of `orders`. Thus one glob covers a package and its sub-packages.
- Quote `"off"`. YAML reads a bare `off` as a boolean.
- Edit only the part of the file above the managed section. The tool writes `exceptions:`
  and `locks:`.

### Write a message that teaches

The `message:` is what a developer or an agent reads when the build fails. Write three
things in it: what is wrong, why the rule exists, and how to fix the issue.

Weak: `catalog -> orders is forbidden.`

Strong:

```
Layering violation: '{source}' must not depend on '{target}'. `catalog` describes
books and authors. It stays at the bottom of the dependency graph, so that each caller
can use it alone. Move the reference to the package that owns the workflow.
```

## Existing violations

A new rule on existing code usually finds issues that are already there. Name which of
these three options you use, and get approval for the second and the third.

| Option | Command | Use it when |
| --- | --- | --- |
| Fix them | — | There are few issues, and the fix is safe. |
| Accept each one, with a reason | `cdec exceptions allow <key> --reason "..."` | Some cases are known and acceptable. |
| Accept all of them | `cdec check --automatic-exceptions rules` | You adopt a rule on a large codebase. New issues still fail. |

A softer start is `severity: warning`. The rule reports and does not fail the run.

## Adopt in steps

Do not turn on each rule at one time on a mature codebase. Use this sequence.

1. **Observe.** Add rules, and run `cdec check --fail-on none`. Nothing fails.
2. **Ratchet.** Accept the current issues with `cdec check --automatic-exceptions rules`.
   Only new issues fail.
3. **Tag the important classes.** Add `sealed`, `immutable` and `factory` tags where the
   design matters. Add a `tag-conformance` rule. Its `rules:` option adopts one tag at a time.
4. **Lock what must not change.** Add `locked` tags and an `implementation-locks` rule. Put
   `.cdec/rules.yaml` behind CODEOWNERS.
5. **Add `reference-architecture`** when each structural change must be deliberate.

Then decrease the `exceptions:` list with time. `cdec exceptions prune` removes the
entries whose issue is gone.

## What each language supports

| Capability | Python | C# | Odin | Lua | Julia | TypeScript | Svelte |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Model rules | yes | yes | yes | yes | yes | yes | yes |
| `reference-architecture` | yes | yes | yes | yes | yes | yes | yes |
| Constraint tags | decorators | attributes | `//@cdec` comments | `---@cdec` comments | macros | no | no |
| `tag-conformance` | yes | yes | yes | yes | yes | no | no |
| `implementation-locks` | yes | yes | yes | yes | yes | no | no |

TypeScript and Svelte have no tags. For these languages, write each constraint as a
package rule or a class rule in `.cdec/rules.yaml`. A tag rule on these languages is
skipped, and the report says so.

## Limits to tell the reviewer

- `no-side-effects` is recorded and frozen, but nothing examines the method body.
- `frozen-members` does not see a change of visibility, of `static` or `abstract`, or of
  the class kind. `reference-architecture` sees them.
- `layer-dependencies` ignores a reference to a class that has no `layer` tag. Tag each
  class of a layered subsystem.
- In Python, `no-instantiation` and `factory` use a heuristic. A call to a capitalised
  name counts as a construction. The `allow=[...]` argument is the escape.
- If no check can enforce a decision, say so. Do not write a rule that only looks like it
  enforces the decision.
