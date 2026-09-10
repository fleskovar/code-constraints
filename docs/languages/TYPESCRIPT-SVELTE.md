# TypeScript & Svelte

> Runs against **[`examples/typescript_demo`](../../examples/typescript_demo)** and
> **[`examples/svelte_demo`](../../examples/svelte_demo)** — the bookstore domain and a
> Svelte 5 storefront.

TypeScript and Svelte are **parse-only** languages today: full modelling, diagrams, diffing,
and every `rules.yaml` rule (the model rules) plus the reference gate (`reference-architecture`). They have no rule
shim, so the `tag-conformance` rule has nothing to check and the `implementation-locks` rule refuses by name.

That still covers most of what teams actually gate on — layering, dependency direction,
cycles, naming, fanout, and "did the architecture change since we agreed on it".

| | |
|---|---|
| Parser | `tree-sitter-typescript` (+ a Svelte wrapper for `.svelte` files) |
| Tags | ❌ none yet |
| `check` (the model rules) | ✅ every rule |
| `enforce` (`tag-conformance`) | — nothing to check |
| `lock` (`implementation-locks`) | ❌ refuses by name |
| Reference gate (`reference-architecture`) | ✅ |
| Activity / sequence | ❌ |

---

## 1. How they map onto a UML model

**TypeScript.** Packages come from the directory layout; a file-level `namespace X { … }`
(the grammar's `internal_module`) nests classes further inside it. `class_declaration`
becomes a class, `interface_declaration` an interface, and `type_alias_declaration` maps to
`interface` as the closest UML equivalent. `.d.ts` files are skipped — they restate types
defined elsewhere and would double-count.

**Svelte.** The parser handles `.svelte` and `.ts` files together, running the TypeScript
grammar over `<script>` block contents, and resolves component imports into relationships —
so a component's helper module shows up alongside it.

⚠️ **No semantic resolution.** A type referenced through an aliased import appears as the
alias. Write `forbidden-references` patterns against the source text.

---

## 2. Parse and look at it

```bash
cdec parse examples/typescript_demo --lang typescript --out ts.xmi
cdec parse examples/svelte_demo     --lang svelte     --out svelte.xmi
cdec serve
```

Detection handles the overlap for you: **any `.svelte` file present wins**, since Svelte
projects also carry `.ts`. Otherwise the language with the most files wins.

`node_modules`, `dist`, `build`, `.svelte-kit`, `.next`, `.turbo` and `coverage` are skipped.

---

## 3. the model rules — the part that works fully

`cdec init` and `cdec check` work normally:

```bash
cdec init --lang typescript --source .
cdec check --config .cdec --source .
```

> **Note:** older versions of this documentation warned that the config loader rejected
> `language: typescript`. That limitation is gone — `.cdec/rules.yaml` accepts every
> supported language, and `cdec check` runs against TypeScript and Svelte projects directly.

Rules worth reaching for first:

```yaml
- id: ui-does-not-import-data-layer
  type: forbidden-package-references
  from: ["components"]
  to: ["db", "server"]

- id: no-cyclic-package-dependencies
  type: no-cyclic-package-dependencies

- id: bounded-class-fanout
  type: max-class-fanout
  limit: 8
```

The [reference gate](../TUTORIAL.md#part-7--the-reference-gate) (`cdec check`) also
works, and is the strictest option available for these languages:

```bash
cdec reference set demo.json
cdec check --lang typescript
```

---

## 4. What you don't get, and what to do instead

**No constraint tags.** There is no `@sealed` / `[Sealed]` equivalent, so the tag-driven
rules — `layer-dependencies`, `frozen-rules` — have nothing to read.

Use **package-path rules instead of tags**: `forbidden-package-references` expresses the
same layering intent as `@layer` without needing a tag on each class.

**No the `implementation-locks` rule.** Implementation freezing needs an AST fingerprinter, which these
languages don't have yet. the `implementation-locks` rule refuses **by name** rather than reporting "0 locks", so
you can tell the difference between "unsupported" and "nothing tagged":

```
the `implementation-locks` rule supports python, csharp, odin, lua and julia; got 'typescript'.
Implementation freezing needs an AST fingerprinter for the language.
```

**No activity or sequence diagrams.** `<uml-activity>` / `<uml-sequence>` tags are not
recognised in `.ts` / `.svelte` files.

---

## 5. CI

```yaml
- run: cdec check --config .cdec --source .    # the model rules
```

the `tag-conformance` rule is safe to run but reports nothing, so there is no reason to add it yet.

---

## Where to go next

- **[Tutorial](../TUTORIAL.md)** — the full workflow including the design loop.
- **[Rules catalogue](../RULES_CATALOGUE.md)** — every rule the model rules offers.
- **[Language guides index](README.md)** — the full capability matrix.
