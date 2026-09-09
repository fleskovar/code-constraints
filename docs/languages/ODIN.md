# Odin

> Runs against **[`examples/odin_demo`](../../examples/odin_demo)** — a `catalog` + `orders`
> slice of the bookstore domain with a fully tagged `billing` module and one intentional
> violation. Every command below is copy-pasteable from the repository root.

Odin support is complete: parser, all seven constraint tags, `cdec enforce` (Engine B) with
**precise** construction detection, and `cdec lock` (Engine C) with the `odin-ts/1`
fingerprinter. Activity and sequence diagrams are not implemented for Odin.

| | |
|---|---|
| Parser | `tree-sitter-odin` (syntactic — no semantic resolution) |
| Tags | `//@cdec …` annotation comments |
| Shim | `cdec_rules.odin` (vocabulary reference + no-op procs) |
| `enforce` | ✅ precise — composite literals and `new`/`make` |
| `lock` | ✅ `odin-ts/1` |
| Activity / sequence | ❌ |

---

## 1. How Odin maps onto a UML model

Odin has no classes, so two mapping rules do all the work. Understanding them is the
difference between tags that constrain what you meant and tags that constrain nothing.

### Structs, enums and unions become classes

```odin
Money :: struct {          // → class Money (kind: struct)
    amount:   f64,
    currency: string,
}

Status :: enum { Draft, Sent, Paid }   // → class Status (kind: enum), members as attributes
```

A field declaring several names at once (`x, y: f64`) is *one* grammar node with two
identifiers, and produces two attributes.

### Procedures belong to their first parameter

This is the important one. Odin declares procedures at package scope, so `cdec` attributes
each to the type of its **first parameter**, stripping `^` / `[]` / `[dynamic]` wrappers:

```odin
formatted :: proc(r: ^Receipt) -> string { … }
```

becomes the operation `formatted` on `Receipt` — it draws inside the Receipt box, its
qualified name is `orders.Receipt.formatted`, and a tag on it constrains that method.

The receiver is dropped from the rendered signature (it is `self` in UML terms), so
`proc(inv: ^Invoice, verbose: bool)` shows as `summarise(verbose: bool)`.

Because a procedure and its struct can live in different files, the parser is **two-phase**:
every struct is registered first, then procedures are attached. Resolution prefers the same
package, then falls back to a project-wide match *only if unambiguous* — an ambiguous name
is left unattached rather than guessed wrong.

### `using` embedding is inheritance

Odin's subtype mechanism maps to `bases`, not to an attribute:

```odin
Detailed :: struct {
    using base: Invoice,   // → Detailed inherits Invoice (an inheritance edge)
    note:       string,
}
```

This is also what makes `@cdec sealed` meaningful in Odin — see §4.

### Receiver-less procedures become a `static` class

A procedure whose first parameter isn't a project struct has no receiver, so it lands on a
synthetic class named after the file stem:

```odin
// in orders/util.odin
round_up :: proc(x: f64) -> f64 { … }   // → orders.util.round_up  (kind: static)
```

Without this a tag on a free procedure would be silently dropped.

### Other details

- **Packages** come from the directory path (Odin already scopes one package per directory),
  falling back to the declared `package` name for files at the project root.
- **`@(private)`** sets visibility to private.
- **Return types** have no field name in the grammar — they're found positionally, after the
  `->` token. Multiple returns are kept verbatim: `(out: string, ok: bool)`.
- ⚠️ **No semantic resolution.** A type referenced through an import alias appears as the
  alias. Keep that in mind when writing `forbidden-references` patterns.

---

## 2. Parse and look at it

```bash
cdec parse examples/odin_demo --lang odin --out odin.xmi
cdec serve            # http://127.0.0.1:8765 — register the folder, pick "odin"
```

`--lang` is optional when the tree is unambiguous; `.odin` files are detected automatically.

The model for the demo:

```
catalog.Author           struct
catalog.Book             struct   ops=[display_name]
orders.Cart              struct   ops=[cart_total, add_item]
orders.Receipt           struct   ops=[formatted]
orders.AuditEntry        struct
orders.ReceiptFactory    struct   ops=[for_cart]
orders.CheckoutService   struct   ops=[summarize, quick_receipt]
```

Note `for_cart`, `cart_total` and `formatted` are all package-scope procedures in the
source — they appear as methods because of the first-parameter rule.

---

## 3. Writing tags

Odin's `@(...)` attributes are a **closed set the compiler validates**, so a no-op
`@(cdec_sealed)` would fail to build. Tags therefore ride in a namespaced comment placed
directly above the declaration, where an attribute would go:

```odin
//@cdec immutable
//@cdec sealed
//@cdec layer("orders")
Receipt :: struct {
    total: f64,
    lines: int,
}

//@cdec locked(reason = "receipt wording is contractual")
formatted :: proc(r: ^Receipt) -> string {
    return fmt.tprintf("%d line(s) — %.2f", r.lines, r.total)
}
```

Rules:

- **Line adjacency is required.** A blank line between the comment block and the declaration
  detaches the tag. Comment lines that aren't tags may sit inside the block harmlessly.
- **Arguments use call syntax** — positional (`layer("orders")`) or named with `=`
  (`locked(reason = "why", owner = "ann")`). Lists use brackets: `allow = ["AuditEntry"]`.
- A bare tag needs no parentheses.
- A malformed tag is **skipped, never fatal** — but it also silently does nothing, so if a
  badge isn't showing up, check the spelling first.

### The shim

```bash
cdec update-assets      # drops cdec_rules.odin into the project root
```

`cdec_rules.odin` is the in-repo reference for the vocabulary and declares each tag as a
no-op proc. Nothing has to import it — the `@cdec` prefix is the namespace. Parsers **skip
the shim file itself**, so its no-op procs never show up as a module class in your diagrams.

---

## 4. Engine A — architectural drift (`cdec check`)

Engine A reads the model only; it never opens a procedure body. Everything in
[`rules.yaml`](../RULES_CATALOGUE.md) works for Odin unchanged.

```bash
cdec check --config examples/odin_demo/.cdec --source examples/odin_demo
# cdec check: no violations.
# cdec lock: 1 locked element(s) verified, no changes.
```

The demo's rules cover both layering styles — package paths and `@cdec layer(...)` tags:

```yaml
- id: catalog-is-a-leaf-package
  type: forbidden-package-references
  from: ["catalog"]
  to: ["orders"]

- id: layer-directions
  type: layer-dependencies
  allow:
    orders: ["catalog"]
    catalog: []
```

**Freezing the tags themselves** matters most here — otherwise a failing constraint can be
silenced by deleting its comment:

```yaml
- id: freeze-architectural-tags
  type: frozen-rules
  scope: diff
  classes: ["orders.**"]
```

Try it — delete the `//@cdec sealed` line from `Receipt` and re-run:

```
[V-73228C5D] orders.Receipt — orders/billing.odin:39:
  Architectural tag drift: the rule 'sealed' on 'orders.Receipt' was removed.
```

---

## 5. Engine B — implementation conformance (`cdec enforce`)

```bash
cdec enforce examples/odin_demo --lang odin
```

```
cdec enforce: 2 conformance violation(s):
  - [F-4E5B2B91] [factory] orders/billing.odin:89: 'orders.CheckoutService.quick_receipt'
      constructs 'Receipt' outside its designated factory (ReceiptFactory).
  - [F-5BBDCC93] [no-instantiation] orders/billing.odin:89: 'orders.CheckoutService.quick_receipt'
      is tagged @cdec no_instantiation but constructs 'Receipt'.
```

Both fire on the one intentional violation in `quick_receipt`. Route it through the factory
and the run goes green.

**Detection in Odin is precise**, not heuristic — the grammar distinguishes the constructs
outright, so there are no false positives to suppress:

| Construct | Recognised as |
|---|---|
| `Money{amount = 1}` | composite literal → construction of `Money` |
| `new(Receipt)`, `make([]Book, 3)` | allocation → construction of the first argument's type |
| `for_cart(&s.receipts, cart)` | an ordinary call — **not** a construction |

Field reassignment for `@cdec immutable` is matched on `recv.field = …` rooted at the
receiver parameter, so an unrelated `other.total = …` is not flagged.

**A type may always construct itself.** `Receipt`'s own constructor building a `Receipt` is
never a `factory` or `no-instantiation` violation.

`sealed` needs no body analysis — it compares the tag against every other struct's `using`
embedding:

```odin
//@cdec sealed
Base :: struct { id: int }

Derived :: struct { using base: Base }   // → [sealed] 'Derived' subclasses sealed 'Base'
```

### Escape hatch

```odin
//@cdec no_instantiation(allow = ["AuditEntry"])
CheckoutService :: struct { receipts: ReceiptFactory }
```

For a one-off you disagree with, record it in the ledger instead:

```bash
cdec baseline allow F-5BBDCC93 --config examples/odin_demo/.cdec --reason "legacy path, ticket #142"
```

---

## 6. Engine C — implementation freeze (`cdec lock`)

```bash
cdec lock list examples/odin_demo --lang odin --config examples/odin_demo/.cdec
# ok   orders.Receipt.formatted  method  (tag)  orders/billing.odin:46
#      reason: demo baseline
```

Tag a procedure or struct, then baseline it:

```bash
cdec lock set examples/odin_demo --lang odin --config examples/odin_demo/.cdec \
  --reason "receipt wording is contractual"
cdec lock check examples/odin_demo --lang odin --config examples/odin_demo/.cdec
```

**A lock is an AST identity, not a line range.** For Odin specifically, all of these leave
the digest untouched:

- adding or removing the `//@cdec locked` tag itself,
- editing or adding comments inside the body,
- reformatting,
- inserting unrelated code above the procedure.

Any semantic change to the body — down to swapping the em-dash for a comma in that format
string — fails the check. Accepting one is a privileged, reviewable act:

```bash
cdec lock set examples/odin_demo --lang odin --target orders.Receipt.formatted --force \
  --reason "finance approved the new wording"
```

Gate `.cdec/locks.yaml` with CODEOWNERS and that stays a lead-only operation. Locks are
**not waivable** through `cdec baseline allow` — the refusal points you here instead.

---

## 7. Gotchas

**A tag detached by a blank line does nothing, silently.** The most common Odin mistake:

```odin
//@cdec sealed

Receipt :: struct { … }    // ← tag NOT applied
```

**A procedure whose first parameter isn't a project struct is not a method.** If an
operation isn't appearing where you expect, check the first parameter's type — it may have
landed on the file's `static` module class instead.

**An ambiguous type name across packages is left unattached.** Two structs named `Config` in
different packages, and a procedure taking `^Config` from a third: the parser declines to
guess. Move the procedure into the owning package.

**`cdec lock` refuses unsupported languages by name.** If you see a message naming the
languages rather than "0 locks", you passed the wrong `--lang`.

---

## 8. CI

Nothing Odin-specific — the same three commands gate everything:

```yaml
- run: cdec check   --config .cdec --source .   # Engine A + C
- run: cdec enforce . --lang odin               # Engine B
```

`cdec check` runs the lock verification automatically whenever the project has ledger
entries, so the two lines above cover all three engines. See
[Tutorial Part 9](../TUTORIAL.md#part-9--wiring-up-cicd) for full workflows.

---

## Where to go next

- **[Tutorial](../TUTORIAL.md)** — the full workflow including the design loop.
- **[Rules catalogue](../RULES_CATALOGUE.md)** — every rule and tag in detail.
- **[Language guides index](README.md)** — how Odin compares to the others.
