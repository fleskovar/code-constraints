---
description: Runs the propose, review and lock loop of code-constraints. Write a JSON model of the target architecture, show it in the browser as a diff against the code with `cdec propose`, change it until the reviewer agrees, then lock it with `cdec reference set`. Use when you propose, discuss or review a class or package design, compare a design with the code, or update the reference architecture.
---

# The propose, review and lock loop

The reviewer looks at a live class diagram in a browser. You edit one JSON model file and
push it to the viewer. The diagram diff is the review medium. Use the chat for reasons and
decisions. Do not paste the full model or raw XMI into the chat for review.

To decide when a change needs this loop, use the `cdec-architecture-first` skill.

## The loop

```bash
# 1. Get a model that you can edit. Use ONE of these.
cdec parse <source> --lang <language> --out target.json   # start from the code
cdec convert .cdec/reference.xmi target.json              # start from the locked design

# 2. Edit target.json until it shows the target architecture.

# 3. Push it to the viewer, filtered to the classes under discussion.
cdec propose target.json --focus pkg.ClassA,pkg.ClassB

# 4. Discuss, edit target.json, and run `cdec propose` again. Repeat.

# 5. Lock the design. Do this ONLY after the reviewer approves the current model.
cdec reference set target.json                            # writes .cdec/reference.xmi

# 6. The gate now compares the code with the locked design.
cdec check
```

`<language>` is one of `python`, `csharp`, `typescript`, `svelte`, `odin`, `lua`, `julia`.
`.json` and `.xmi` model files are interchangeable in each command.

If `cdec` is not on `PATH`, use `python -m code_constraints.cli <command>`.

## Start the viewer

`cdec propose` uses a viewer that runs on port 8765. If no viewer runs, `cdec propose`
starts one itself and does not return. That blocks your shell.

- Start the viewer as a background process before the first push: `cdec ui --no-browser`.
- Then each `cdec propose` returns immediately and prints the URL.
- If you have the MCP tools, `cdec_propose` starts the viewer for you and returns the URL.

Give the URL to the reviewer after the first push.

## Options of `cdec propose`

| Option | Effect |
| --- | --- |
| `--focus A,B` | The viewer shows only these classes. Use qualified names. |
| `--against source` | The diff baseline is the current code. This is the default. |
| `--against reference` | The diff baseline is `.cdec/reference.xmi`. |
| `--against none` | The viewer shows the proposal alone. Use it for a new project. |
| `--no-browser` | Push without a new browser tab. |
| `--source DIR`, `--lang L` | Set the source tree and the language. The default comes from `.cdec/rules.yaml`. |
| `--port N` | Use a viewer on a different port. |

How to read the diff: the proposal is the new side.

- **Green**: the proposal has it and the code does not. The code must add it.
- **Red**: the code has it and the proposal does not. The code must remove it.
- **Yellow**: the element is in the two sides, and it is different.

## How to run the review

- **Keep one model file.** Change the same file through the full discussion. Make a second
  file only when the reviewer asks to compare two alternatives.
- **Push small changes.** Push after each change that has a meaning. Set `--focus` to the
  two to six classes of the current question.
- **Tell the difference, not the model.** After each push, say in one or two sentences
  what changed and what the reviewer must look at.
- **Do not change `--source` between pushes.** The viewer finds the open tab by the source
  path and the language. The same pair refreshes the tab. A different pair opens a new
  project.
- **Ask before you lock.** `cdec reference set` changes what `cdec check` fails on for
  each developer. Run it only after the reviewer approves the current model. The approval
  of an earlier version does not apply.

## The model file

The model is the same JSON document that the web editor uses. All field names are
snake_case. Do not write the file from nothing when the code exists. Run `cdec parse` and
edit the result.

```json
{
  "source_language": "python",
  "packages": [
    {
      "name": "billing",
      "qualified_name": "billing",
      "classes": [
        {
          "name": "Invoice",
          "qualified_name": "billing.Invoice",
          "kind": "class",
          "description": "Why this class exists.",
          "bases": ["Document"],
          "rules": [{ "name": "sealed" }],
          "attributes": [{ "name": "total", "type": "float" }],
          "operations": [
            {
              "name": "pay",
              "parameters": [{ "name": "amount", "type": "float" }],
              "return_type": "bool"
            }
          ]
        }
      ],
      "sub_packages": []
    }
  ]
}
```

Each field, with its permitted values, is in `./model-format.md`. Read it before you add a
constraint tag with arguments to the model. The form of the arguments is exact.

## After the lock

- The gate is `cdec check`. Use the `cdec-gate` skill to read its report and to decide what
  to do when it blocks a change.
- To change a locked design, run the loop again: edit the model, propose, get the approval,
  and run `cdec reference set`.
- `cdec reference set` declares what the code must become.
  `cdec check --automatic-exceptions reference` records what the code is now. Do not use
  the second command to accept a design. It deletes the difference that the reference
  exists to show.
- Offer guardrails for the new structure. The `cdec-guardrails` skill has the rule types,
  the tags and a pattern cookbook.

## Problems

| Problem | Cause and solution |
| --- | --- |
| `cdec propose` does not return. | No viewer was in operation, so the command started one. Start `cdec ui --no-browser` in the background first. |
| The tab does not refresh. | You changed `--source` or `--lang` between pushes. Use the same values. |
| A new class has no edge to its base. | `bases` must name a class of the model, as the source writes the name. An unknown name shows as an external node. |
| The viewer does not start on port 8000. | The default port is 8765. Do not use 8000. Some Windows machines reserve it. |
| A tag in the model shows as changed. | The tag arguments are not in the exact source form. See `./model-format.md`. |
