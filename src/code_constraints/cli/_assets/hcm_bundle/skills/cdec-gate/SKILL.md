---
description: Runs the `cdec check` gate of code-constraints and resolves its failures. Read the report, find the issue keys, and choose between a code fix, a design change, a recorded exception and a rule change. Use before and after each code change in a project that has a `.cdec/` folder, and when `cdec check` fails or blocks a change.
---

# Run the gate and resolve its failures

`cdec check` is the full gate. It runs each rule in `.cdec/rules.yaml` and gives one
report and one exit code. There is no second command to run.

## Run the gate

```bash
cdec check                              # the full gate
cdec check --format json                # the same report as JSON
cdec check --log-out check.log          # also write the report to a file
cdec check --base-ref origin/main       # diff rules compare with a git revision
cdec check --rules-file fast            # only the rules in .cdec/rules/fast.yaml
cdec check --fail-on warning            # warnings also fail the run
```

| Exit code | Meaning |
| --- | --- |
| `0` | No issue at or above the `--fail-on` severity. |
| `1` | One or more issues. Read the report. |
| `2` | The configuration is not valid: no `rules.yaml`, an unknown rule type, or a language mismatch. |

Run the gate at these times:

1. Before you start, so that you know which issues exist without your change.
2. After each step of the implementation.
3. Before you report the task as complete.

With the MCP tools, `cdec_check` runs the gate and `cdec_issues` gives the issues as a
list. The keys are the same as the keys of the command line.

## Read the report

```
[catalog-is-a-leaf-package] (error)
  - [V-DD3EA5B2] catalog — Layering violation: 'catalog' must not depend on 'orders'. ...

[tags-must-be-honoured] (error)
  - [F-5A5D24E3] orders.CheckoutService.quick_receipt — orders/billing.py:97: ... constructs 'Receipt' outside its designated factory (ReceiptFactory).

Summary: 2 error(s), 0 warning(s).
```

- The heading is the `id` of the rule in `.cdec/rules.yaml`. Read that entry, and read its
  `message:`. The message tells you why the rule exists and how to fix the issue.
- Each issue starts with a stable key. The prefix names the engine:

  | Prefix | Engine | The question it answers |
  | --- | --- | --- |
  | `V-` | Model rules | Did the architecture drift, and does it obey the written laws? |
  | `F-` | `tag-conformance` | Does the code obey its constraint tags? |
  | `L-` | `implementation-locks` | Did a frozen implementation change? |
  | `R-` | `reference-architecture` | Is the public shape different from the reference? |

- A key comes from what the issue is, not from where it is. It stays the same when the
  code moves or when the format changes.
- Read the **skipped** list. A skipped rule did not run. It is not a pass. Two usual causes
  are a `scope: diff` rule with no baseline, and a tag rule on TypeScript or Svelte.

## Decide what to do

Find the cause first. Then use the first row that applies.

| The cause | What you do | Approval |
| --- | --- | --- |
| The code is wrong. It breaks a constraint that is correct. | Fix the code. This is the usual case. | Not necessary |
| The design changed on purpose. | Use the `cdec-architecture-first` skill: change the model, propose it, then run `cdec reference set`. | Necessary |
| One known case is acceptable, and the rule stays correct for all other cases. | Record an exception: `cdec exceptions allow <key> --reason "..."`. | Necessary |
| The rule is wrong for the project. | Change the rule in `.cdec/rules.yaml`, and give the reason. | Necessary |

When approval is necessary, stop and ask. Give the key, the message, the cause and your
recommendation. Do not select the second, third or fourth row because the first row is
more work.

### Fix by engine

**`V-` — a model rule.**

- `forbidden-references`, `forbidden-package-references`, `layer-dependencies`: remove the
  reference, or invert it. Define an interface in the lower layer and implement it in the
  higher layer.
- `no-cyclic-package-dependencies`: move the shared types to a leaf package, or invert one
  direction with an interface.
- `subclass-naming`: rename the class so that it matches the pattern.
- `max-class-fanout`: split the class, or make it depend on an interface.
- `dangling-classes`: delete the dead class. If a framework creates it, ask to add it to
  `entry_points`.
- `no-new-classes`, `no-removed-classes`, `frozen-members`: the shape changed against the
  baseline. Revert the change, or go through the design loop.
- `frozen-rules`: a constraint tag was removed or its arguments changed. Put the tag back
  exactly as it was.

**`F-` — the code does not obey a tag.**

- `factory`: get the object from the designated factory. Do not construct it directly.
- `no-instantiation`: inject the collaborator. Do not construct it in the tagged class.
- `immutable`: return a new instance. Do not assign to a field after construction.
- `sealed`: hold an instance of the sealed class. Do not extend it.
- A false positive in Python is possible, because a call to a capitalised name counts as a
  construction. The fix is a wider `allow=[...]` on the tag. That edit changes a tag, so
  `frozen-rules` reports it. Ask for approval first.

**`L-` — a frozen implementation changed.**

- Revert your change to the locked body. This is the only fix that you can do alone.
- If the task cannot be done without the change, stop and tell the user. A lead approves
  the change with `cdec check --automatic-exceptions locks --target <element> --force`.
  The `--target` option limits the approval to that element.
- A `missing` lock means that a new `@locked` tag has no recorded digest. Ask before you
  run `cdec check --automatic-exceptions locks`. That command only adds digests.

**`R-` — the public shape is different from the reference.**

- If you did not intend the change, revert it. The report names the class and the member.
- If the reference is the target of an approved proposal, the issue is work that is still
  to do. Continue the implementation until the code matches.
- If you intended the change and no proposal covers it, go through the design loop.

## Record an exception

Do this only after a person approves it.

```bash
cdec exceptions allow V-DD3EA5B2 --reason "legacy adapter, removal tracked in ARCH-42"
```

For many issues at one time:

```bash
cdec exceptions review --out review.txt     # one line for each issue
#  add [ALLOW: the reason] to each line that the reviewer accepts
cdec exceptions patch --file review.txt
```

| Command | Effect |
| --- | --- |
| `cdec exceptions list` | Show the recorded exceptions and their reasons. |
| `cdec exceptions remove <key>` | Remove an exception, so that the issue blocks again. |
| `cdec exceptions prune` | Remove the exceptions whose issue does not occur any more. |

- Always give a reason. The exception goes into a committed file, and a person reviews it.
- One exception covers one element. Prefer it to an `ignore:` glob, which stops the rule
  for each element that matches.
- `cdec exceptions allow` refuses an `L-` key. A lock has no exception.
- A file from `cdec check --log-out` also works as the input of `cdec exceptions patch`.

## Commands that need explicit approval

These commands change what the gate accepts. Do not run them on your own initiative.

| Command | What it accepts |
| --- | --- |
| `cdec exceptions allow`, `cdec exceptions patch` | One or more named issues. |
| `cdec check --automatic-exceptions rules` | Each current issue, except the lock issues. |
| `cdec check --automatic-exceptions reference` | The current code as the new reference. |
| `cdec check --automatic-exceptions locks` | New digests for newly tagged code. It only adds. |
| `cdec check --automatic-exceptions locks --force` | Each change to frozen code. Only a lead approves this. |
| `cdec check --automatic-exceptions locks --target <glob> --force` | The change to the named elements only. Only a lead approves this. |
| `cdec check --bypass-locks` | A run that ignores lock issues. It prints an audit banner. |
| `cdec reference set` | A new target architecture. |

The MCP tools `cdec_allow`, `cdec_accept` and `cdec_reference_set` have the same effects
and need the same approval.

## Things that you must not do

- Do not delete a constraint tag so that a check passes.
- Do not change a rule to `severity: off` or `severity: warning` so that a check passes.
- Do not add an `ignore:` glob so that a check passes.
- Do not report "the gate passes" when a rule was skipped or bypassed. Report the skip.
- Do not edit the `exceptions:` or `locks:` sections of `.cdec/rules.yaml` by hand. The
  tool writes them.
