---
name: cdec-architecture-loop
description: Discuss and iterate architectural decisions with code-constraints — author a JSON model of the target architecture, show it in the browser diffed against the code with `cdec propose`, refine it through conversation (the open tab refreshes on every push), then lock it with `cdec reference set` to constrain development, and accept deliberate exceptions afterwards with `cdec exceptions allow`. Use whenever the user wants to plan, review, restructure, or agree on class/package architecture, discuss a refactor's target shape, compare a design against the current code, update the reference architecture, or decide what to do when `cdec check` / the `tag-conformance` rule blocks a change they want to keep.
---

# UML architecture discussion loop

You are driving an interactive architecture review with the **code-constraints** tool. The
human looks at a live diagram in their browser; you edit a JSON model file and push
updates. Never paste raw XMI (or the whole JSON) into the chat as the primary review
medium — the diagram diff *is* the review medium; chat is for reasoning and decisions.

## The loop

```bash
# 0. Nothing to start manually — `cdec propose` reuses a running `cdec serve`
#    (port 8765) or boots one itself.

# 1. Get an editable model (pick ONE starting point):
cdec parse <src> --lang <lang> --out target.json        # start from the code as-is
cdec convert .cdec/reference.xmi target.json             # start from the locked design

# 2. Edit target.json to express the proposed architecture (see shape below).

# 3. Push for review, pre-filtered to what's under discussion:
cdec propose target.json --focus pkg.ClassA,pkg.ClassB
#    green = code still needs to grow this; red = proposal removes this.
#    --against reference   → diff vs the locked design instead of the code
#    --against none        → render the proposal standalone (greenfield)
#    --no-browser          → push without opening a tab (tab already open)

# 4. Discuss → edit target.json → `cdec propose` again. The open tab refreshes
#    in place (it polls; positions and filters survive). Repeat until agreed.

# 5. Lock the agreed design (ONLY after explicit approval from the human):
cdec reference set target.json                          # writes .cdec/reference.xmi

# 6. Development is now constrained:
cdec check        # exit 1 on structural deviation (CI gate)
cdec check                 # drift rules (frozen tags, layers, forbidden refs)
cdec check                        # every rule: drift, tags, locks, reference

# 7. When a constraint blocks something the design intends to allow:
cdec exceptions allow V-1A2B3C4D --reason "why this is acceptable"
```

If `cdec` is not on PATH, use `.venv/Scripts/python.exe -m code_constraints.cli <command>`.

## When the constraints block a legitimate change

A locked design that can only say *no* gets switched off. Step 7 is the release valve, and
picking the right one is itself an architectural decision — say which you chose and why:

| The blocked change is… | Do this |
|---|---|
| a deliberate change to the **architecture** | edit `target.json` → `cdec propose` → approval → `cdec reference set`. Back to the loop. |
| a **known, acceptable exception** | `cdec exceptions allow <key> --reason "…"` — the rule keeps protecting everything else. |
| evidence the **rule is wrong** | change it in `.cdec/rules.yaml`, and justify it. Rare, and never silent. |

Every issue leads with a stable key — `V-` (check), `F-` (enforce), `L-` (lock):

```
- [V-DD3EA5B2] billing.LegacyGateway — billing/legacy.py:12: 'billing.LegacyGateway' is not allowed to reference 'ui.Panel'.
```

Keys hash *what* an issue is, never where it sits, so they survive reformatting and repeat
run to run. For a batch: `cdec exceptions review --out review.txt`, mark lines `[ALLOW]` (or
`[ALLOW: reason]`), then `cdec exceptions patch --file review.txt`. A `cdec check --log-out`
file is patchable as-is. `cdec exceptions list` / `remove KEY` / `prune` manage what's been
accepted.

- **Always pass a reason.** The waiver is committed and read by a human.
- **`L-` keys are not waivable.** `cdec exceptions allow` refuses them and prints
  `cdec check --automatic-exceptions locks --target … --force` — a frozen implementation changes only on the human's
  explicit say-so, never on your initiative.
- Prefer a waiver over adding an `ignore:` glob or dropping a rule: one reviewable line
  about one element, versus turning the rule off for everything it would have caught.

## How to run the conversation

- **One artifact**: keep a single `target.json` on disk and evolve it across the whole
  discussion. Don't fork variants unless the human asks to compare alternatives.
- **Small pushes, narrow focus**: push after each meaningful change and set `--focus`
  to the 2–6 classes the current question is about, so the human isn't hunting
  through the whole canvas. Change focus as the discussion moves.
- **Narrate the delta, not the model**: after each push, say in one or two sentences
  what changed since the last push and what you want the human to look at.
- **Ask, don't lock**: `cdec reference set` is the commitment point — it changes what
  every developer's `cdec check` / `cdec check` fails on. Run it only after the
  human explicitly approves the *current* model (approval of an earlier iteration
  doesn't carry over).
- After locking, offer the enforcement follow-ups: rule tags (`@layer`, `@sealed`,
  `@immutable`, `@factory`, `@no_instantiation` — Python/C# only) and `.cdec/rules.yaml`
  lint rules (`forbidden-package-references`, `no-cyclic-package-dependencies`, … —
  all languages). Every rule and tag, with options and pass/fail examples, is catalogued in
  `docs/RULES_CATALOGUE.md`.
- **Say how each new rule handles what already violates it.** Turning on a rule that fires
  on twenty existing classes with no stated way through is how a team ends up deleting the
  rule. Either fix them, waive them individually with reasons, or `cdec check
  --automatic-exceptions rules` to grandfather the lot — but name the choice.

## The JSON model shape

Same document the web editor uses; snake_case; produce a valid skeleton with
`cdec parse … --out x.json` and edit it rather than writing from scratch when possible.

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
          "attributes": [{ "name": "total", "type": "float" }],
          "operations": [
            { "name": "pay", "parameters": [], "return_type": "bool" }
          ],
          "bases": ["billing.Document"],
          "description": "why this class exists"
        }
      ],
      "sub_packages": []
    }
  ],
  "associations": []
}
```

Notes:
- `kind` is one of `class|interface|abstract|enum|struct|record|static`; `bases` holds
  qualified names and draws inheritance edges.
- An attribute `type` naming a project class draws an association edge automatically
  (collection wrappers like `list[X]` / `List<X>` are unwrapped).
- Omitted optional fields default sensibly; unknown classes referenced in `bases`
  render as external placeholder nodes.
- `.json` and `.xmi` are interchangeable in every command; `cdec convert` translates.

## Pitfalls

- The viewer runs on **port 8765** (8000 is reserved by Windows http.sys on this machine).
- Repeated `cdec propose` pushes for the same `(source path, lang)` hit the same
  project, which is what makes the open tab refresh — don't vary `--source` between
  iterations of one discussion.
- Diff orientation: the proposal is the NEW side. If the human expects "what would I
  have to delete", remind them red = present in code, absent from proposal.
- For TypeScript/Svelte, rule *tags* don't exist — encode constraints as package-level
  lint rules in `.cdec/rules.yaml` instead, and say so.
