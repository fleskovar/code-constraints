# Lua

> Runs against **[`examples/lua_demo`](../../examples/lua_demo)** — a `catalog` + `orders`
> slice of the bookstore domain with a fully tagged `billing` module and one intentional
> violation. Every command below is copy-pasteable from the repository root.

Lua support is complete: parser, all seven constraint tags, the `tag-conformance` rule (`tag-conformance`) with
**idiom-based** construction detection, and the `implementation-locks` rule (`implementation-locks`) with the `lua-ts/1`
fingerprinter. Activity and sequence diagrams are not implemented for Lua.

Lua is the loosest language `cdec` supports — dynamically typed, with classes that are a
convention rather than a construct. The guide is explicit about where that costs precision.

| | |
|---|---|
| Parser | `tree-sitter-lua` (syntactic; no types, so attribute/parameter types are empty) |
| Tags | `---@cdec …` annotation comments |
| Shim | `cdec_rules.lua` (vocabulary reference + runtime no-ops) |
| `enforce` | ✅ idiom-based — `T.new(...)` and `setmetatable(t, T)` |
| `lock` | ✅ `lua-ts/1` |
| Activity / sequence | ❌ |

---

## 1. How Lua maps onto a UML model

### What becomes a class

Lua has no classes, so the parser recognises the standard table-plus-metatable idiom.
Within one file, a table becomes a class when it shows **at least one** of:

- a function declared on it — `function T:m()` or `function T.m()`,
- the `T.__index = T` self-index that marks a prototype,
- a metatable base — `setmetatable({}, { __index = Base })`,
- a `---@cdec` tag above its declaration.

That last condition matters: **tagging a table is enough to model it** before it has any
methods, so you can describe a design as you write it.

Equally important is what does *not* get promoted. A plain data table stays out of the
diagram:

```lua
local scratch = {}                       -- not a class: no methods, no __index, no tag
local Money = require("billing.money")   -- not a class: binds a name, declares nothing
```

Without that rule every scratch local in the file would end up on your class diagram.

### Methods, statics and inheritance

```lua
local Receipt = {}
Receipt.__index = Receipt          -- prototype marker
Receipt.CURRENCY = "USD"           -- → static attribute (default "USD")

function Receipt.new(total)        -- → static function (dot)
  local self = setmetatable({}, Receipt)
  self.total = total               -- → instance attribute
  return self
end

function Receipt:formatted()       -- → instance method (colon)
  return string.format("%.2f", self.total)
end

local Detailed = setmetatable({}, { __index = Receipt })   -- → Detailed inherits Receipt
```

- `function T.m()` is **static**; `function T:m()` takes an implicit `self` and is an
  **instance method**.
- Metafields (`__index`, `__call`, `__tostring`, …) are recognised as structure, not data —
  they never appear as attributes.
- A leading underscore marks private by convention: `self._audit` renders as private.

### Instance attributes come from every method

Lua has no `__init__` to privilege, so **any** `self.x = …` in **any** method of `T`
contributes the attribute `x`. This is deliberately broader than the Python parser's
`__init__`-only rule — in Lua there is no reliable way to know which function is the
constructor.

The walk follows **source order**, because attribute order is visible in the class box and
is what the diff compares.

### Class tables are file-scoped

A Lua module is a file, so `function T:m()` resolves against tables declared in the *same
file* only. There is no cross-file guessing.

### Free functions become a `static` class

```lua
local function helper(x) return x end    -- → billing.invoice.helper (kind: static)
```

Named after the file stem, so a tag on a free function is never silently dropped.

---

## 2. Parse and look at it

```bash
cdec parse examples/lua_demo --lang lua --out lua.xmi
cdec serve            # http://127.0.0.1:8765 — register the folder, pick "lua"
```

Because Lua is untyped, **attribute and parameter types are empty** in the model and
association edges come from capitalised identifiers used in bodies. Expect a sparser
diagram than a C# one — that is the language, not a parser gap.

---

## 3. Writing tags

Lua has no decorator syntax, so tags ride in a `---@cdec` comment placed directly above the
declaration. The `@cdec` prefix is the namespace, so an unrelated LuaCATS/LuaLS annotation
can never be mistaken for a rule.

```lua
---@cdec immutable
---@cdec sealed
---@cdec layer("orders")
local Receipt = {}
Receipt.__index = Receipt

---@cdec locked(reason = "receipt wording is contractual")
function Receipt:formatted()
  return string.format("%d line(s) — %.2f", self.lines, self.total)
end
```

Rules:

- **Line adjacency is required** — a blank line between the comment block and the
  declaration detaches the tag. Ordinary comment lines may sit inside the block.
- **Arguments use Lua call syntax** — positional (`layer("orders")`) or named with `=`
  (`locked(reason = "why", owner = "ann")`).
- **Lists are Lua tables**: `no_instantiation(allow = {"AuditEntry"})`. (Odin and Julia use
  brackets; both forms are read correctly.)
- A bare tag needs no parentheses.
- A tag above `local T = {}` *or* above `T.__index = T` attaches to the same class, so it
  doesn't matter which line you pick.

### The shim

```bash
cdec update-assets      # drops cdec_rules.lua into the project root
```

`cdec_rules.lua` documents the vocabulary and exposes each tag as a runtime no-op function,
so `require("cdec_rules")` resolves if you prefer an explicit call somewhere. The parser
reads the **comments**, not the calls. Parsers skip the shim file itself, so its no-op
functions never appear as a module class in your diagrams.

---

## 4. the model rules — architectural drift (`cdec check`)

the model rules reads the model only. Everything in
[`rules.yaml`](../RULES_CATALOGUE.md) works for Lua unchanged.

```bash
cdec check --config examples/lua_demo/.cdec --source examples/lua_demo
# cdec check: no violations.
# cdec lock: 1 locked element(s) verified, no changes.
```

Freezing the tags themselves is the rule that matters most, since a comment is easy to
delete:

```yaml
- id: freeze-architectural-tags
  type: frozen-rules
  scope: diff
  classes: ["orders.**"]
```

Delete `---@cdec sealed` from `Receipt` and re-run:

```
[V-73228C5D] orders.Receipt — orders/billing.lua:33:
  Architectural tag drift: the rule 'sealed' on 'orders.Receipt' was removed.
```

the model rules is the strongest of the three on Lua, because it needs no type information — it
works off the model's shape, which the parser recovers reliably.

---

## 5. `tag-conformance` — implementation conformance (the `tag-conformance` rule)

```bash
cdec check --config examples/lua_demo/.cdec --source examples/lua_demo
```

```
[tags-must-be-honoured] (error) — 2 finding(s):
  - [F-4E5B2B91] [factory] orders/billing.lua:103: 'orders.CheckoutService.quick_receipt'
      constructs 'Receipt' outside its designated factory (ReceiptFactory).
  - [F-5BBDCC93] [no-instantiation] orders/billing.lua:103: 'orders.CheckoutService.quick_receipt'
      is tagged @cdec no_instantiation but constructs 'Receipt'.
```

### Detection is heuristic — know the boundaries

Lua construction has no syntax of its own, so `cdec` recognises **two idioms**:

| Code | Treated as |
|---|---|
| `Receipt.new(…)` / `Receipt:new(…)` where `Receipt` is a project class | construction |
| `setmetatable(tbl, Receipt)` | construction |
| `Receipt(…)` — a bare call | **not** construction (that's `__call`, not a constructor) |

Constructor names recognised: `new`, `create`, `init`, `_init`, `_new`.

If your codebase uses a different constructor convention, `tag-conformance` will under-report. That
is the honest trade — a looser heuristic would flag every ordinary call.

**`immutable`** flags `self.x = …` outside the constructor, where "the constructor" means a
function with one of the names above.

**A type may always construct itself** — without this rule every Lua constructor would be
flagged, since `Receipt.new` necessarily does `setmetatable({}, Receipt)`.

**`sealed`** needs no body analysis and is fully reliable — it compares the tag against
every other table's metatable base:

```lua
---@cdec sealed
local Base = {}
local Derived = setmetatable({}, { __index = Base })  -- → [sealed] violation
```

### Escape hatches

```lua
---@cdec no_instantiation(allow = {"AuditEntry"})
local CheckoutService = {}
```

Or record a one-off in the ledger:

```bash
cdec exceptions allow F-5BBDCC93 --config examples/lua_demo/.cdec --reason "legacy path, ticket #142"
```

---

## 6. `implementation-locks` — implementation freeze (the `implementation-locks` rule)

```bash
cdec locks examples/lua_demo --lang lua --config examples/lua_demo/.cdec
# ok   orders.Receipt.formatted  method  (tag)  orders/billing.lua:45
```

```bash
cdec check --automatic-exceptions locks   examples/lua_demo --lang lua --config examples/lua_demo/.cdec --reason "…"
cdec check examples/lua_demo --lang lua --config examples/lua_demo/.cdec
```

**A Lua "class" is not one node.** The table-plus-metatable idiom spreads a class across
several statements (`local T = {}`, `T.__index = T`, each `function T:m()`), so a *class*
lock digests the whole group. That is the right semantics for a freeze: **adding a method to
a locked class is a change to the class**.

Two consequences worth knowing:

- A `---@cdec locked` above `function T:m()` locks the **method**, not the class — even
  though that statement is part of the class's digest.
- Locking a class is a much broader commitment in Lua than in Python or C#. Prefer locking
  individual methods unless you really mean "this table is finished".

All the usual invariants hold — these leave the digest untouched:

- adding or removing the `---@cdec locked` tag,
- comment edits inside the body,
- reformatting,
- inserting unrelated code above the function.

Re-baselining a genuine change stays privileged:

```bash
cdec check --automatic-exceptions locks examples/lua_demo --lang lua --target orders.Receipt.formatted --force --reason "…"
```

---

## 7. Gotchas

**A tag detached by a blank line does nothing, silently.**

```lua
---@cdec sealed

local Receipt = {}    -- ← tag NOT applied
```

**Your table isn't on the diagram?** It probably has no methods, no `__index`, no metatable
base and no tag. Add a `---@cdec` tag to pull it in, or check you're not looking at a
`require` binding.

**Attribute you didn't expect?** Instance attributes come from `self.x = …` in *every*
method, not just the constructor. A transient field set in a method is still a field of the
object, and is modelled as one.

**Cross-file classes don't resolve.** `function T:m()` only attaches to a `T` declared in the
same file. If you split a class across files, the methods land on the file's `static` module
class instead.

**`tag-conformance` under-reports by design.** If construction in your codebase doesn't look like
`T.new(…)` or `setmetatable(t, T)`, it isn't detected. Lean on the model rules (layering, frozen
tags) and `implementation-locks` (locks) — both are fully reliable on Lua.

---

## 8. CI

```yaml
- run: cdec check   --config .cdec --source .   # the model rules + C
```

See [Tutorial Part 9](../TUTORIAL.md#part-9--wiring-up-cicd) for full workflows.

---

## Where to go next

- **[Tutorial](../TUTORIAL.md)** — the full workflow including the design loop.
- **[Rules catalogue](../RULES_CATALOGUE.md)** — every rule and tag in detail.
- **[Language guides index](README.md)** — how Lua compares to the others.
