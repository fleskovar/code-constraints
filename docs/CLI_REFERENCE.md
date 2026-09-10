# code-constraints — CLI & CI/CD Reference Guide

A developer reference for the `cdec` command-line tool: every command, the `.cdec/`
configuration files, a summary of the architectural-rule catalogue, and how to wire it all
into CI/CD so pull requests that drift from the intended architecture are rejected
automatically.

For the constraints themselves — every rule type and source tag with its options, a sample
configuration, and a passing *and* failing example — see the
**[Rules & constraints catalogue](RULES_CATALOGUE.md)**.

> **Invocation.** All examples use `cdec`. If the console script isn't on your
> `PATH`, the equivalent is `python -m code_constraints.cli …` (on Windows with the bundled venv:
> `.venv/Scripts/python.exe -m code_constraints.cli …`). The two are interchangeable.

---

## Table of contents

> **New here?** Start with the [Tutorial](TUTORIAL.md) — a guided path from parsing your
> first codebase to a fully gated CI pipeline. This document is the exhaustive reference.
>
> **Choosing what to enforce?** §4 and §5 below summarise the tags and rule types. The
> per-rule reference — every option, a sample configuration, and a passing *and* failing
> example each — is the [Rules & constraints catalogue](RULES_CATALOGUE.md).

1. [Mental model](#1-mental-model)
   - [`frozen-members` vs `reference-architecture`](#frozen-members-vs-reference-architecture)
2. [Command reference](#2-command-reference)
   - [Project setup](#21-project-setup)
   - [Parsing, rendering & diffing](#22-parsing-rendering--diffing)
   - [`cdec check` — the gate](#23-cdec-check--the-gate)
   - [Accepting known violations](#24-accepting-known-violations-cdec-exceptions) — the review loop
   - [The reference model](#25-the-reference-model-cdec-reference)
   - [Web viewer & the design loop](#26-web-viewer)
3. [`.cdec/rules.yaml`](#3-cdecrulesyaml)
   - [Settings](#31-settings)
   - [`rules:`](#32-rules)
   - [`exceptions:`](#33-exceptions)
   - [`locks:`](#34-locks)
   - [`reference.xmi`](#35-referencexmi)
   - [`.gitignore` & `cache/`](#36-gitignore--cache)
4. [Architectural-rule tags](#4-architectural-rule-tags) — *full detail: [catalogue §2](RULES_CATALOGUE.md#2--source-level-constraint-tags)*
5. [Lint-rule catalogue (`rules.yaml` types)](#5-lint-rule-catalogue-rulesyaml-types) — *full detail: [catalogue §1](RULES_CATALOGUE.md#1--configured-rules-cdecrulesyaml)*
   - [Complete sample `rules.yaml`](#complete-sample-rulesyaml)
6. [Exit codes](#6-exit-codes)
7. [CI/CD recipes](#7-cicd-recipes)

---

## 1. Mental model

code-constraints parses a source tree into a language-agnostic UML model, serialised to
**XMI 2.1** as the on-disk source of truth. From there it can render diagrams, diff two
snapshots, and enforce architectural constraints.

**One file, one command.** Everything a project commits lives in `.cdec/rules.yaml`, and
`cdec check` is the whole gate. Four kinds of rule run inside it. They share a rule
catalogue but no logic, and they answer different questions:

| Rule kind | `type:` values | Question it answers | Reads method bodies? | Needs a baseline? |
|---|---|---|---|---|
| **Model rules** | `no-new-classes`, `forbidden-references`, `layer-dependencies`, … | "Did the architecture drift, and does it obey the laws we wrote down?" | No (model only) | Only `scope: diff` rules |
| **Conformance** | `tag-conformance` | "Does the code actually obey the constraint tags written on it?" | Yes | No |
| **Freeze** | `implementation-locks` | "Did this specific implementation change **at all**?" | Yes (digests them) | Yes (the `locks:` list) |
| **Reference gate** | `reference-architecture` | "Has *anything* structural changed vs the reference snapshot?" | No (model only) | Yes (the reference model) |

Each is opt-in: an entry in `rules.yaml` turns it on, `severity: off` or deleting the entry
turns it off. `cdec check` enforces exactly what the file asks for and nothing more.

- **Model rules** are the everyday policy engine: dependency direction, layering, naming,
  cycles, fanout, and drift against a baseline.
- **`tag-conformance`** is tag-driven: it re-parses the source and inspects bodies for
  `@no_instantiation`, `@factory` and `@immutable`, plus the structural `@sealed`.
- **`implementation-locks`** is the strictest and narrowest: it freezes a specific class or
  function *body* by digesting its normalised AST. Reformatting, renaming a local, moving
  the function down the file, or editing a comment do **not** trip it; any semantic change
  does. Scope is opt-in per element via `@locked` / `[Locked]`, or by glob.
- **`reference-architecture`** is an all-or-nothing structural gate: it fails on *every*
  structural deviation (added/removed classes and members, signature and return-type
  changes, access-level and modifier changes, class-kind changes, base-class changes). Use
  it to freeze the public shape of a codebase and review every change deliberately.

**Choosing between them.** They operate at descending levels of granularity — the reference
gate over the whole public shape, model rules over the laws you name, `tag-conformance`
over tagged bodies, `implementation-locks` over individual bodies:

| You want to say | Add this rule |
|---|---|
| "Nothing about the public shape changes without review" | `reference-architecture` |
| "These specific architectural laws are never broken" | any model rule |
| "Code tagged with a constraint must actually honour it" | `tag-conformance` |
| "*This function* is settled — nobody touches it" | `implementation-locks` |

They compose, and they all run in one `cdec check`, so CI has one command and one exit
code.

### `frozen-members` vs `reference-architecture`

These two look alike — both compare the current code against a reference model — but they
answer different questions and behave differently. The distinction matters when choosing
your CI gate.

**`frozen-members` (and the other `scope: diff` rules) are a configurable, opt-in policy
engine.** They flag only what you asked for: a named set of classes, a named set of member
kinds, with a severity, `ignore` globs, and an exceptions list to grandfather pre-existing
cases.

**`reference-architecture` is an all-or-nothing structural gate.** It has no per-element
configuration. *Any* structural deviation from the reference fails it. You do not tell it
what to care about — it cares about everything.

| | `frozen-members` | `reference-architecture` |
|---|---|---|
| What it flags | Only the classes and member kinds you name | Every structural change |
| Configuration | `classes`, `members`, `kinds` | `categories` at most |
| Suppress known issues | The `exceptions:` list | The `exceptions:` list |
| Severity levels | `error` / `warning` / `off`, tuned via `--fail-on` | Same, but effectively binary in practice |
| Baseline source | git ref (`--base-ref`) **or** the reference model | The reference model only |
| Granularity | The classes and member kinds you choose | Fixed: classes, members, signatures, modifiers, kinds, bases |

#### The subtle technical gap

Even where they overlap, **they detect different things**, because they sit on two
different comparison engines:

- The `scope: diff` rules read the statuses produced by `diff_projects`
  (`src/code_constraints/core/diff.py`). That engine matches members by **`signature()`**
  (`name:type` for attributes, `name(params):return_type` for operations) and only marks a
  *matched* member changed when its constraint **tags** differ. It is therefore **blind**
  to:
  - access-level changes (`public` → `private`),
  - modifier changes (`static`, `abstract`, `readonly`),
  - class-kind changes (concrete → abstract).
- `reference-architecture` runs its **own dedicated comparator**
  (`src/code_constraints/reference/compare.py`) that walks both models field by field and
  *does* catch all of those.

So a pull request that flips a public method to private, or makes a concrete class
abstract, would **pass** `frozen-members` but **fail** `reference-architecture`. This is
the main reason the reference gate exists as a rule type of its own rather than an option
on another.

#### When to use which

- **`reference-architecture`** — "freeze the shape of this codebase; nothing changes
  without a reviewer deliberately accepting it." The intended-change workflow is: gate
  fails → reviewer approves → author runs `cdec check --automatic-exceptions reference`,
  commits the new `reference.xmi` → gate passes. Ideal for stable public APIs or a locked
  architecture.
- **Model rules** — "enforce these specific architectural laws" (no UI→domain references,
  no package cycles, factories must be named `*Factory`, do not remove classes). Targeted
  governance where most change is fine but certain rules are sacred. They are also the only
  ones that can diff against a **live git ref** (`--base-ref origin/main`) instead of a
  committed snapshot.

They are complementary, and since they live in the same file you can run both: many teams
keep `reference-architecture` as a hard backstop **and** the specific model and tag rules
that carry semantic meaning.


---

## 2. Command reference

Running `cdec` with **no subcommand** launches an interactive session in the current
directory. Every subcommand below is non-interactive and CI-safe.

### 2.1 Project setup

#### `cdec init`

Scaffold a `.cdec/` folder (config, rule templates, baseline, README) and snapshot an
initial `reference.xmi` from the source.

```
cdec init [--config .cdec] [--lang python] [--source .] [--force]
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--config` | `.cdec` | Directory to create. |
| `--lang` | `python` | `python \| csharp \| odin \| lua \| julia \| typescript \| svelte`. |
| `--source` | `.` | Source tree that `cdec check` will parse; also snapshotted into `reference.xmi`. |
| `--force` | off | Overwrite existing files instead of refusing. |

#### `cdec update-assets`

Refresh the bundled assets (Claude agents, language shims) in an existing project after
upgrading code-constraints.

```
cdec update-assets [--project-root .] [--no-agents] [--no-shims] [--lang L]
```

`--lang` is auto-detected from `.cdec/rules.yaml` when omitted. Use `--no-agents` /
`--no-shims` to limit what is refreshed.

#### `cdec update`

Update the code-constraints installation itself in place (pull latest, re-sync deps, rebuild
the web UI). `--branch` targets a specific branch; `--no-frontend` skips the UI rebuild.

### 2.2 Parsing, rendering & diffing

#### `cdec parse`

Parse a source tree and write an XMI 2.1 file.

```
cdec parse PATH --lang L --out FILE.xmi
```

#### `cdec render`

Render an SVG from a stored XMI. Requires Graphviz `dot` on `PATH` (or `$CDEC_DOT_BIN`).

```
cdec render XMI --diagram class|package|activity|sequence [--name NAME] -o OUT.svg
```

`--name` is required for `activity` and `sequence` diagrams.

#### `cdec diff`

Diff two **git revisions** and emit an annotated XMI (added/removed/changed elements).
Checks both refs out into a temp dir, so your working tree is untouched.

```
cdec diff OLD_REF NEW_REF --lang L --out FILE.xmi [--repo .] [--subpath ""]
```

`--subpath` restricts parsing to one directory of each revision.

#### `cdec diff-vs-xmi`

Diff a freshly-parsed source tree against a **reference XMI** (the XMI is the *old*
side, the source is the *new* side).

```
cdec diff-vs-xmi REFERENCE_XMI SOURCE_PATH --lang L --out FILE.xmi
```

#### `cdec diff-xmi`

Diff two **existing XMI files** (e.g. CI artefacts from two branches) without re-parsing.

```
cdec diff-xmi OLD_XMI NEW_XMI --out FILE.xmi
```

#### `cdec convert`

Convert a model file between **XMI 2.1** and **editor JSON**. The direction is inferred
from the file extensions, so one command covers both ways.

```
cdec convert SRC DEST        # .xmi -> .json, or .json -> .xmi
```

The JSON shape is the same document the web editor and the proposal endpoint use. It is a
snake_case mirror of the internal model (packages → classes → attributes/operations, with
rule tags), which makes it far easier to author or edit by hand — or by an AI agent — than
XMI. Converting back produces standard XMI again.

> Every command that reads or writes a model file accepts **either** format. `parse --out
> model.json`, `render model.json`, `reference set model.json` and `propose model.json` all
> work, so `convert` is only needed when you explicitly want the other representation on
> disk.

### 2.3 `cdec check` — the gate

Runs every rule in `.cdec/rules.yaml` and exits non-zero when violations remain after the
`exceptions:` list is applied. This is the only enforcement command; the rule types decide
what it actually does.

```
cdec check [--config .cdec] [--source DIR] [--lang L] [--reference MODEL] [--base-ref REF] \
           [--repo .] [--fail-on error|warning|none] [--format human|json] \
           [--json-out FILE] [--log-out FILE] \
           [--automatic-exceptions WHAT] [--force] \
           [--bypass-locks] [--bypass-reason TEXT]
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--config` | `.cdec` | Folder holding `rules.yaml`. |
| `--source` | from `rules.yaml` | Override the source tree. |
| `--lang` | from `rules.yaml` | Override the language. |
| `--reference` | from `rules.yaml` / `.cdec/reference.xmi` | Baseline model for `scope: diff` rules and for `reference-architecture`. |
| `--base-ref` | — | Use a git ref as the baseline instead of a stored model (parsed live). Wins over `--reference`. |
| `--repo` | `.` | Git repo root (only used with `--base-ref`). |
| `--fail-on` | `error` | Minimum severity that fails the run: `error \| warning \| none`. |
| `--format` | `human` | `human \| json` stdout format. |
| `--json-out` | from `rules.yaml` | Also write a JSON report to a file. |
| `--log-out` | from `rules.yaml` | Tee the human report to a file. That file is directly patchable — see [§2.4](#24-accepting-known-violations-cdec-exceptions). |
| `--automatic-exceptions` | — | Accept the current state instead of failing on it. See below. Repeatable, or comma-separated. Short form `-A`. |
| `--force` | off | With `--automatic-exceptions locks`, also re-baseline **changed** implementations and prune released entries. The privileged operation. |
| `--bypass-locks` | off | Report lock violations but do not fail on them. Prints an audit banner and sets `summary.bypassed`. |
| `--bypass-reason` | `""` | Why locks are being bypassed. Recorded in the output and the JSON report. |

Baseline resolution order: `--base-ref` → `--reference` → the `reference:` setting in
`rules.yaml` → `.cdec/reference.xmi`. Rules declared `scope: diff` are **skipped** (not
failed) when no baseline is available, and the report says so — a rule that could not run
must never look like one that passed.

#### `--automatic-exceptions` — accepting the current state

The counterweight to enforcement, and the thing that makes adoption on an existing codebase
possible. Each value accepts a different kind of "yes, this is fine":

| Value | Effect |
|---|---|
| `rules` | Grandfather every currently-reported violation into the `exceptions:` list. Only **new** violations of the same rule fail afterwards — the ratchet. |
| `locks` | Record digests for elements newly tagged `@locked`. Safe for anyone to run: without `--force` it only *adds*. |
| `reference` | Re-snapshot `.cdec/reference.xmi` from the current source. |
| `all` | All three. |

Order is fixed and matters: `reference` and `locks` settle first, then the checks re-run,
and only what is *still* reported is grandfathered. The other way round would write
exceptions for issues the re-snapshot was about to erase.

**Lock violations are never grandfathered.** `--automatic-exceptions rules` reports them
and refuses; accepting a change to frozen code is `--automatic-exceptions locks --force`,
which leaves a reviewable ledger diff. See the privilege boundary below.

**Common flows**

```bash
# The CI gate
cdec check

# Pre-merge, against the target branch (parsed live, no stored model needed)
cdec check --base-ref origin/main --json-out report.json

# Adopting on an existing codebase: grandfather today's violations
cdec check --automatic-exceptions rules

# Record digests for newly @locked code
cdec check --automatic-exceptions locks

# Accept a deliberate architectural change
cdec check --automatic-exceptions reference
```

#### The source-reading rules

Three rule types re-read the code rather than the model. They are documented in full in the
[catalogue](RULES_CATALOGUE.md); what follows is what you need to operate them.

**`tag-conformance`** confirms the code obeys its constraint tags. It checks
`no-instantiation`, `factory` and `immutable` (body analysis) plus `sealed` (structural),
and consults no baseline or diff — the question is only what the code does right now.
`rules: [...]` narrows it to a subset of tags so a team can adopt them one at a time.
Available for **python, csharp, odin, lua and julia**; the other languages have no tag
syntax and the rule reports as skipped.

> `no-side-effects` is captured, visualised, diffed and drift-frozen, but its **body
> analysis is deliberately not implemented** — the rule will not flag a side-effecting
> method tagged `@no_side_effects`. Treat the tag as documentation plus drift protection.

**`implementation-locks`** freezes the *body* of a class or function so it cannot change
without an explicit, reviewable re-baseline. Identity is **AST-derived, not line-based**:
inserting code above a locked function, reformatting it, renaming a local variable, or
editing a comment never trips the lock. Any semantic change does.

Declare intent in the source with `@locked` / `[Locked]` / `@cdec locked`, then record the
approved digest with `cdec check --automatic-exceptions locks`. Available for **python,
csharp, odin, lua and julia** — the languages with an AST fingerprinter. TypeScript and
Svelte are refused **by name**, so the rule reports as skipped rather than "nothing locked".

It catches five distinct failures, each reported with its own kind:

| Kind | Headline | Meaning |
|---|---|---|
| `changed` | frozen implementation changed | The body's digest no longer matches the ledger. |
| `missing` | declared `@locked` but not baselined | An element is tagged `@locked` but was never recorded. |
| `removed` | frozen element no longer exists | A locked element was deleted or renamed. |
| `unlocked` | `@locked` tag was removed | The tag was deleted while the ledger entry remains. |
| `algo-mismatch` | digest algorithm changed | The ledger was written by a different fingerprinter — re-baseline required. |

These are the `rule` values in the JSON report, so CI can branch on them.

**The privilege boundary.** `cdec check --automatic-exceptions locks` freely *adds* locks
for newly tagged elements, so it is safe for anyone to run and can never erase evidence
that frozen code changed. Accepting a change to already-locked code — or pruning an entry
whose tag was deleted — requires `--force`, which shows up as a reviewable diff on the
`locks:` section of `.cdec/rules.yaml`:

```bash
cdec check --automatic-exceptions locks           # safe: only adds new locks
cdec check --automatic-exceptions locks --force   # privileged: accepts a change
```

Gate `.cdec/rules.yaml` with a CODEOWNERS entry to keep re-baselining a lead-only action.
`cdec exceptions allow` refuses an `L-` key for the same reason, and prints that command
instead.

**Bypass** is `--bypass-locks` (or `CDEC_LOCK_BYPASS=1`). It still collects violations and
prints an audit banner, and sets `summary.bypassed` in the JSON report so CI can reject
bypassed runs rather than silently accepting them.

**Target identity.** Classes use the UML qualified name (`orders.Receipt`); module-level
Python functions additionally carry the module stem (`orders.billing.compute_tax`), since
two modules in a package may define the same name. Same-named siblings — overloads,
`@property` + its setter — are **grouped into one target**, so adding an overload to a
locked name is itself a violation.

**`reference-architecture`** fails on every structural deviation from the reference model.
See [§1](#frozen-members-vs-reference-architecture) for what it catches that the diff-based
rules cannot, and `cdec reference` in [§2.5](#25-the-reference-model-cdec-reference) for
authoring the model it gates against.

#### Inspecting what is lockable

```
cdec locks [SOURCE] [--lang L] [--config .cdec] [--all] [--json]
```

Read-only. Shows what is frozen and whether each entry still matches; `--all` also lists
every *lockable* element, so you can see what you could freeze before you tag it.
Verification is `cdec check`; recording is `cdec check --automatic-exceptions locks`.

#### Retired commands

`cdec enforce`, the `cdec lock` group, `cdec reference test` and `cdec reference update`
were separate gates with separate reports and separate exit codes. They are rule types now.
The old commands still exist as hidden stubs that print where the behaviour went:

| Old command | Now |
|---|---|
| `cdec enforce` | the `tag-conformance` rule, run by `cdec check` |
| `cdec lock check` | the `implementation-locks` rule, run by `cdec check` |
| `cdec lock set` | `cdec check --automatic-exceptions locks` |
| `cdec lock set --force` | `cdec check --automatic-exceptions locks --force` |
| `cdec lock list` | `cdec locks` |
| `cdec lock remove` | delete the `@locked` tag, then `--automatic-exceptions locks --force` |
| `cdec reference test` | the `reference-architecture` rule, run by `cdec check` |
| `cdec reference update` | `cdec check --automatic-exceptions reference` |
| `cdec check --update-baseline` | `cdec check --automatic-exceptions rules` |
| `cdec check --update-reference` | `cdec check --automatic-exceptions reference` |
| `cdec check --enforce` | `cdec check` (add a `tag-conformance` rule) |
| `cdec baseline …` | `cdec exceptions …` (the old name still works, hidden) |

### 2.4 Accepting known violations (`cdec exceptions`)

Enforcement that can only ever say *no* gets switched off. `cdec exceptions` is the other
half of the loop: read the report, decide which issues are acceptable, record the decision
**with a reason** in the `exceptions:` section of `.cdec/rules.yaml`, and keep moving. The recorded decision is a
committed, reviewable diff — and it can be withdrawn later.

**Every issue prints a stable key.**

```
[no-new-classes] (error)
  - [V-DD3EA5B2] animals.Cat — animals/cat.py:1: New class 'animals.Cat' was added.
```

| Prefix | Reported by | Acceptable as an exception |
|--------|-------------|----------------------------|
| `V-` | a model rule (drift, dependencies, naming, shape) | yes |
| `F-` | `tag-conformance` | yes |
| `L-` | `implementation-locks` | **no** — see below |
| `R-` | `reference-architecture` | yes |

The key is a hash of *what* the issue is (which kind of rule, the element, a
discriminator), never of *where* it is, and never of which `rules.yaml` entry surfaced it.
So re-running over unchanged code always yields the same key; inserting lines above the
offending element does not change it; and renaming the rule entry does not either. The flip
side is deliberate: a key names an equivalence class, so two identical violations of one
rule on one element share a key and one exception covers both.

#### Two ways in

**By file** — the review path, for a batch of issues:

```bash
cdec exceptions review --out review.txt   # one markable line per issue
#  …edit review.txt, adding [ALLOW] to the lines you accept…
cdec exceptions patch --file review.txt
```

A marked line looks like this; the marker can go anywhere on the line, and
`[ALLOW: reason]` records why:

```
- [ALLOW: legacy, tracked in ARCH-42] [V-DD3EA5B2] [error] [no-new-classes] [animals/cat.py:1] animals.Cat: New class 'animals.Cat' was added.
```

`cdec check --log-out report.txt` output works as a patch file too — the parser only needs
a marker and a key on the same line, so any text file will do. A `#` at the start of a line
comments it out, which is how you cancel a decision without deleting the evidence.

**By key** — the one-liner / agent path:

```bash
cdec exceptions allow V-DD3EA5B2 --reason "agreed in ARCH-42"
cdec exceptions allow V-DD3EA5B2 F-5BBDCC93        # several at once
```

`--format json` on `cdec check` and `cdec exceptions review` both emit the keys, so an
agent or an MCP server can go report → decision → `allow` without parsing prose.

#### Subcommands

```
cdec exceptions review [--config .cdec] [--out FILE] [--all] [--format text|json] \
                     [--source DIR] [--reference XMI] [--base-ref REF] [--repo .]
cdec exceptions patch  --file FILE|-  [--reason TEXT] [--dry-run] [--ignore-unknown] …
cdec exceptions allow  KEY...         [--reason TEXT] [--dry-run] …
cdec exceptions remove KEY...         [--dry-run]
cdec exceptions list   [--engine check|enforce|reference] [--format human|json]
cdec exceptions prune  [--dry-run]
```

| Command | What it does |
|---------|--------------|
| `review` | Writes every current issue as one markable line. `--all` includes already-accepted ones (mark them `[REMOVE]` to withdraw). |
| `patch` | Applies the `[ALLOW]` / `[REMOVE]` marks in a file. `--file -` reads stdin. |
| `allow` | Accepts issues named by key. |
| `remove` | Withdraws exceptions by key, so the issue blocks again. Needs no source parse. |
| `list` | Shows what is accepted, with reason, date, and who granted it. |
| `prune` | Drops exceptions whose issue no longer occurs — a stale one silently pre-approves a *future* violation of the same rule on the same element. Only prunes engines whose rules actually ran. |

`review`, `patch`, `allow`, and `prune` re-run the rules, and take the same
baseline-resolution options as `cdec check` (`--source`, `--reference`, `--base-ref`,
`--repo`). Pass the same ones you passed to `check`, or the keys won't line up.

`cdec baseline` is a hidden alias for this group, kept so scripts written against the old
name keep working.

**A key that matches no current issue is an error, not a no-op** (exit `1`), because it
almost always means the report being quoted is stale. `--ignore-unknown` downgrades that on
`patch`.

#### Locks are not acceptable as exceptions

`implementation-locks` violations appear in the report with an `L-` key, but
`cdec exceptions allow` refuses them and prints the privileged command instead:

```
cdec check --automatic-exceptions locks --force
```

`--automatic-exceptions rules` refuses them too, and says which ones it would not
grandfather. That is by design. Accepting a changed frozen implementation is meant to
produce a reviewable diff on the `locks:` section of `.cdec/rules.yaml` behind a CODEOWNERS
entry; routing it through the ordinary exceptions list would quietly undo that guarantee.

### 2.5 The reference model (`cdec reference`)

The `reference-architecture` rule gates against a stored model, and every `scope: diff`
rule uses the same model as its baseline. These commands **author and visualise** that
model; checking against it is `cdec check`.

Both subcommands resolve their inputs from **explicit arguments with a `.cdec/`
fallback**: `SOURCE` falls back to the `source:` setting, `--lang` to `language:` (then
auto-detection), and `--reference` to `.cdec/reference.xmi`.

There are two ways to produce a reference model, and the difference is the point:

| Command | Meaning |
|---|---|
| `cdec check --automatic-exceptions reference` | "Snapshot **what the code is**." — accept a change that already happened. |
| `cdec reference set MODEL` | "Declare **what the code should become**." — accept a design. |

#### `cdec reference set`

Promote an **authored** model file (hand-written or agent-written, `.json` or `.xmi`) to be
the project's reference. This is the "accept the proposal" step of the design loop.

```
cdec reference set MODEL [--reference MODEL] [--config .cdec]
```

After it runs, `cdec check` immediately starts constraining development against the target
architecture. Because the target usually contains classes that do not exist yet,
`cdec reference show` renders them as green "still to build".

#### `cdec reference show`

Parse the current code, diff it against the reference, and open the web viewer straight to
the diff — added/removed/changed elements highlighted, with the change walkthrough
populated.

Here the reference model is treated as the **target** architecture and the codebase as the
**current** state. So elements present in the reference but missing from the code show as
green additions ("the code still needs to grow this"), and elements in the code but absent
from the reference show as red removals. This is intentionally the inverse of the
`reference-architecture` rule and of `diff-vs-xmi`, where the reference is the *old* side.

```
cdec reference show [SOURCE] [--reference MODEL] [--lang L] [--config .cdec] \
                    [--host 127.0.0.1] [--port 8765]
```

#### Snapshotting from the code

```
cdec check --automatic-exceptions reference [--source DIR] [--reference MODEL] [--config .cdec]
```

Re-parses the source and writes the model. `cdec init` takes the first snapshot for you, so
most projects only run this when a reviewer has approved an architectural change — and the
regenerated `reference.xmi` belongs in the same pull request as the code that caused it,
because that is what makes the delta reviewable.

### 2.6 Web viewer

#### `cdec serve`

Start the FastAPI + Svelte viewer (default `http://127.0.0.1:8765`).

```
cdec serve [--host 127.0.0.1] [--port 8765]
```

> Port 8000 is reserved by Windows `http.sys` on some machines; 8765 is the default for
> that reason. Change with `--port`.

#### `cdec serve parse`

Shortcut: parse a tree and open the browser directly to its class diagram. Language is
auto-detected when `--lang` is omitted.

```
cdec serve parse [PATH] [--lang L] [--host 127.0.0.1] [--port 8765]
```

#### `cdec propose`

Push a **proposed** architecture to the viewer, diffed against a baseline. This is the
interactive half of the design loop: green = still to build, red = to be removed.

```
cdec propose MODEL [--source DIR] [--lang L] [--config .cdec] \
             [--against source|reference|none] [--focus A,B] \
             [--host 127.0.0.1] [--port 8765] [--no-browser]
```

| Option | Default | Meaning |
|--------|---------|---------|
| `MODEL` | — | Proposed architecture (`.json` is easiest to author). |
| `--source` | from config | Source tree the proposal is for. |
| `--lang` | from config / auto | Language. |
| `--against` | `source` | Baseline: `source` (current code) · `reference` (`.cdec/reference.xmi`) · `none`. |
| `--focus` | — | Comma-separated qualified class names; the viewer pre-filters to these. |
| `--no-browser` | off | Push and print the URL without opening a tab. |

**Re-running `propose` refreshes an already-open viewer tab in place** — no new tabs, no
manual reload — which is what makes it usable as a conversation loop: edit the model,
re-propose, discuss, repeat. If a `cdec serve` instance is already listening on the port it
is reused; otherwise a server is started (blocking) with the proposal pre-loaded.

Once the design is agreed, freeze it with `cdec reference set MODEL`.

---

## 3. `.cdec/rules.yaml`

Created by `cdec init`. Commit everything except `cache/`.

```
.cdec/
├── rules.yaml       # settings, rules, exceptions, lock digests — the whole contract
├── reference.xmi    # committed reference snapshot
├── README.md        # human notes (generated)
├── .gitignore       # ignores cache/
└── cache/           # transient parse artefacts (gitignored)
```

`rules.yaml` has four top-level parts. You write the first two; the tool writes the last
two, into a marked section at the end of the file:

```yaml
language: python                  # settings — §3.1
source: src
reference: .cdec/reference.xmi

rules:                            # the laws — §3.2
  - id: domain-must-not-depend-on-ui
    type: forbidden-package-references
    ...

# >>> cdec: managed section — rewritten by `cdec check --automatic-exceptions`
# >>> and by `cdec exceptions ...`. Edit the rules above this line, not below it.
exceptions:                       # accepted violations — §3.3
  - key: V-7C1E90AB
    ...
locks:                            # approved digests — §3.4
  - target: orders.Receipt.formatted
    ...
```

**Writes are surgical.** A tool write keeps every byte above the marker verbatim and
regenerates only what is below it, so the comments and `message:` blocks that make a failed
build teach something are never reflowed or deleted.

> **Upgrading?** Older versions split the same content across `config.yaml`,
> `baseline.yaml` and `locks.yaml`. All three are still read when present, so nothing
> breaks on upgrade, and `cdec init --migrate` folds them into `rules.yaml` and deletes
> them. `cdec check` prints a one-line note while they remain.

### 3.1 Settings

Top-level keys that say what to check and where.

```yaml
language: python                 # python | csharp | odin | lua | julia | typescript | svelte
source: .                        # source tree, relative to the project root
reference: .cdec/reference.xmi   # default baseline model; omit to require --base-ref
output:
  json: null                     # optional default for --json-out
  log: null                      # optional default for --log-out
```

| Key | Required | Meaning |
|-----|----------|---------|
| `language` | yes | Parser to use: `python`, `csharp`, `odin`, `lua`, `julia`, `typescript` or `svelte`. |
| `source` | yes | Directory parsed by `cdec check`, resolved relative to the project root. |
| `reference` | no | Default baseline model. Omit it and `scope: diff` rules need `--base-ref`. |
| `output.json` | no | Default path for the JSON report (`--json-out` overrides). |
| `output.log` | no | Default path for the teed human log (`--log-out` overrides). |

The legacy nesting `baseline: {reference: …}` still resolves, for projects that have not
migrated.

### 3.2 `rules:`

The list of rules `cdec check` runs. Each entry:

```yaml
rules:
  - id: domain-must-not-depend-on-ui   # stable id, used to group the report
    type: forbidden-package-references  # rule implementation (see §5)
    severity: error                     # error | warning | off
    scope: snapshot                     # diff | snapshot (default depends on type)
    message: |                          # optional: explain WHY and HOW to fix
      The domain layer must stay UI-agnostic. Move presentation
      concerns into myapp.ui, or invert the dependency.
    ignore:                             # qualified-name globs to exempt
      - "myapp.domain.legacy.**"
    # …any further keys are rule-specific options (e.g. from/to, classes, allow)
    from: ["myapp.domain.**"]
    to:   ["myapp.ui.**"]
```

| Field | Meaning |
|-------|---------|
| `id` | Stable identifier. Groups the violations in the report, so name it after the law it states. It is **not** part of the issue key, so renaming it never invalidates an exception. Must be unique. |
| `type` | Which rule to run (catalogue in §5). |
| `severity` | `error` (fails at default `--fail-on`), `warning`, or `off` (rule not loaded at all). |
| `scope` | `diff` rules need a baseline and inspect what changed; `snapshot` rules evaluate the current model. Each type has a sensible default. |
| `message` | Optional explanation printed when the rule fires. Supports `{placeholders}` (see the generated `rules.yaml` comments for the set available per type) and multi-line YAML block scalars. Write these for your teammates — say why the rule exists and how to satisfy it. |
| `ignore` | List of qualified-name globs exempted from the rule (`**` matches across dots). |
| *other keys* | Rule-specific options, e.g. `classes`, `from`/`to`, `base`/`name_pattern`, `allow`, `limit`, `targets`. |

`rules: []` (the default scaffold) means no rules run — `cdec check` passes trivially until
you opt in. That is deliberate: you add laws one at a time, as the team agrees on them.

### 3.3 `exceptions:`

The ledger of accepted violations — used to adopt the tool on an existing codebase without
fixing every pre-existing issue at once, and to keep evolving afterwards. Written by
[`cdec exceptions`](#24-accepting-known-violations-cdec-exceptions) (with a reason
attached) or wholesale by `cdec check --automatic-exceptions rules`.

```yaml
exceptions:
  - key: V-7C1E90AB
    engine: check
    rule: no-removed-classes
    qualified_name: myapp.legacy.OldThing
    reason: replaced by myapp.core.Thing in ARCH-42
    added: '2026-08-04T09:00:00+00:00'
    added_by: fran
  - key: F-5BBDCC93
    engine: enforce
    rule: no-instantiation
    qualified_name: myapp.billing.Ledger
    detail: settle->Invoice
```

An entry is matched by its identity — `(engine, rule, qualified_name, detail)` — with `key`
as the human-quotable form of exactly that tuple. **Older ledgers load unchanged**: the key
is derived, so there is nothing to migrate, and the legacy `violations:` / `findings:`
shape is still read. A matching violation is reported as *suppressed* rather than failing
the run; new violations of the same rule on other elements still fail.

`reason`, `added`, and `added_by` are metadata only — they exist so the commit that accepts
a violation explains itself to the next reviewer.

`implementation-locks` has no entries here on purpose: a frozen implementation is
re-baselined through `cdec check --automatic-exceptions locks --force`, which is separately
reviewable. `cdec exceptions allow` refuses an `L-` key, and a hand-written entry for one
is ignored rather than honoured.

### 3.4 `locks:`

The approved-digest ledger, written by `cdec check --automatic-exceptions locks`.

```yaml
locks:
- target: orders.Receipt.formatted
  kind: method
  algo: py-ast/1
  digest: def9d237e48b6d2aae2cc46251c3b670d563130c551bf3116d394a097fe35863
  file: orders/billing.py
  locked_at: '2026-08-02T21:00:38+00:00'
  locked_by: Fran
  reason: receipt wording is contractual; finance signed off on it
```

`algo` records which fingerprinter produced the digest. A mismatch surfaces as an
`algo-mismatch` violation ("re-baseline") rather than a false "implementation changed", so
upgrading the tool never looks like tampering.

This is the section to put behind a CODEOWNERS entry — see the privilege boundary in
[§2.3](#the-source-reading-rules).

### 3.5 `reference.xmi`

The committed model snapshot of the architecture. It is the baseline for:

- every `scope: diff` rule (when `--base-ref` is not given), and
- the `reference-architecture` rule and `cdec reference show`.

`cdec init` takes the first snapshot. Regenerate it — the explicit "accept this change"
action — with:

```bash
cdec check --automatic-exceptions reference    # snapshot what the code IS
cdec reference set target.json                 # declare what it SHOULD BECOME
```

Commit the regenerated file in the same pull request that makes the architectural change,
so reviewers see the model delta in the diff.

### 3.6 `.gitignore` & `cache/`

`.cdec/.gitignore` ignores `cache/`, which holds transient parse artefacts. Everything else
in `.cdec/` should be committed.

---

## 4. Architectural-rule tags

> Summary table only. For each tag's parameters, detection semantics per language, and a
> worked passing/failing pair, see
> [Rules & constraints catalogue §2](RULES_CATALOGUE.md#2--source-level-constraint-tags).

Tags are applied in source as **Python decorators** (imported from the `cdec_rules`
shim) or **C# attributes** (`using CodeConstraints.Rules;`). They are captured on the model,
round-trip through XMI, render as badges in the web viewer, participate in the diff, and
are enforced. A tag is only recognised when imported from the shim namespace, so
unrelated decorators never false-match.

`cdec init` scaffolds `.cdec/` only — run **`cdec update-assets`** to drop the shim (and the
bundled Claude agents/skill) into your project root. The interactive session (`cdec` with no
subcommand) does both with prompts.

| Tag (`id`) | Python / C# | Applies to | Enforced by | Meaning |
|------------|-------------|-----------|-------------|---------|
| `no-instantiation` | `@no_instantiation` / `[NoInstantiation]` | class, method | `tag-conformance` (body) | May not construct objects, except types listed in `allow`. |
| `factory` | `@factory` / `[Factory]` | class, method | `tag-conformance` (body) | The designated constructor of the types in `creates`; construction elsewhere is forbidden. |
| `immutable` | `@immutable` / `[Immutable]` | class | `tag-conformance` (body) | Fields may not be reassigned after construction. |
| `sealed` | `@sealed` / `[Sealed]` | class | `tag-conformance` (structural) | May not be subclassed (composition over inheritance). |
| `no-side-effects` | `@no_side_effects` / `[NoSideEffects]` | method | `frozen-rules` only | Must be side-effect-free. Body analysis is deferred; the tag is still captured, visualised, and frozen. |
| `layer` | `@layer("name")` / `[Layer("name")]` | class | `layer-dependencies` | Assigns the class to an architectural layer for dependency-direction checks. |
| `locked` | `@locked` / `[Locked]` | class, method, function | `implementation-locks` | The implementation is frozen: any semantic change to the body fails CI until re-baselined. Optional `reason` / `owner` are recorded in the ledger and echoed in violations. |

Applying or removing the `locked` tag never changes a digest — the fingerprinters strip it
recursively, including a method-level lock nested inside a locked class — so tagging code
does not require an immediate re-baseline of everything around it.

To freeze the *presence* of these tags over time (so removing or weakening one fails CI),
add a `frozen-rules` entry to `rules.yaml` (see §5). That is drift detection on the tags
themselves — distinct from the `tag-conformance` rule, which checks the code actually obeys them.

---

## 5. Lint-rule catalogue (`rules.yaml` types)

These are the `type:` values usable in `rules.yaml`, grouped by concern. `scope` shows
the default (override per entry).

> Summary tables only. Each rule's full option list, message `{placeholders}`, and a
> passing/failing example are in
> [Rules & constraints catalogue §1](RULES_CATALOGUE.md#1--configured-rules-cdecrulesyaml).

**Structural drift** (default `scope: diff` — needs a baseline)

| `type` | Key options | Fires when… |
|--------|-------------|-------------|
| `no-new-classes` | `ignore` | A class is added vs the baseline. |
| `no-removed-classes` | `ignore` | A class is removed vs the baseline. |
| `frozen-members` | `classes`, `members`, `kinds` | An attribute/operation on a matched class is added, removed, or changed. |
| `frozen-rules` | `classes` | An architectural-rule tag present in the baseline is removed or weakened. |

**Dependency rules** (default `scope: snapshot`, except cycles)

| `type` | Key options | Fires when… |
|--------|-------------|-------------|
| `forbidden-references` | `from`, `to` | A class in `from` references a class in `to`. |
| `forbidden-package-references` | `from`, `to` | A package in `from` references a package in `to`. |
| `no-cyclic-package-dependencies` | — | A dependency cycle exists between packages. |
| `layer-dependencies` | `allow` | A class references another class in a layer not permitted by the `allow` matrix (reads `@layer` tags). |

**Shape rules** (default `scope: snapshot`)

| `type` | Key options | Fires when… |
|--------|-------------|-------------|
| `dangling-classes` | `entry_points`, `framework_bases` | No other class in the project references it (and it isn't an `entry_points` glob or a subclass of a `framework_bases` type). |
| `subclass-naming` | `base`, `name_pattern` | A subclass of `base` has a name not matching `name_pattern`. |
| `max-class-fanout` | `limit` (default `10`) | A class references more than `limit` other classes. |

**Source rules** (default `scope: snapshot`) — these re-read the code rather than the
model, and are the three that used to be separate commands. See
[§2.3](#the-source-reading-rules) for how to operate them.

| `type` | Key options | Fires when… |
|--------|-------------|-------------|
| `tag-conformance` | `rules` | A method body breaks the constraint tag written on it (`no-instantiation`, `factory`, `immutable`), or a `@sealed` class is subclassed. |
| `implementation-locks` | `targets`, `include_docstrings` | A frozen body changed, was deleted, lost its tag, or was never baselined. **Not acceptable as an exception.** |
| `reference-architecture` | `reference`, `categories` | The code deviates structurally from the reference model in any way. |

Every rule also accepts the common fields `id`, `type`, `severity`, `scope`, `message`,
and `ignore` (§3.2). See the comment block at the top of the generated `rules.yaml` for
the `{placeholders}` available in each rule's `message`.

### Complete sample `rules.yaml`

A maximal, annotated configuration exercising **every** rule type with several variants.
Copy what you need — this is a menu, not a recommended baseline (running all of these at
`error` on a real codebase would be very strict). Defaults are shown explicitly for
clarity even where they could be omitted.

```yaml
# .cdec/rules.yaml — every rule type, with variants.

language: python
source: src
reference: .cdec/reference.xmi

# Common fields on every entry:
#   id        unique, stable; the heading violations are grouped under
#   type      the rule implementation (see §5)
#   severity  error | warning | off          (off disables the entry entirely)
#   scope     diff | snapshot                (each type has a sensible default)
#   message   optional explanation, supports {placeholders} + multi-line `|`
#   ignore    list of qualified-name globs to exempt (** matches across dots)

rules:

  # ─────────────────────────── structural drift (scope: diff) ───────────────────────────

  # Forbid any new class anywhere outside tests.
  - id: no-new-classes
    type: no-new-classes
    severity: error
    scope: diff
    message: |
      A new class '{qualified_name}' appeared. New top-level types must be
      reviewed by an architect — add it to the design doc first.
    ignore:
      - "tests.**"
      - "**.conftest"

  # Forbid deleting classes (API stability).
  - id: no-removed-classes
    type: no-removed-classes
    severity: error
    scope: diff
    message: "Class '{qualified_name}' was removed — this is a breaking change."

  # Variant A: lock the ENTIRE public API surface — any member add/remove/change fails.
  - id: freeze-public-api
    type: frozen-members
    severity: error
    scope: diff
    classes: ["myapp.api.**"]
    message: >
      Member '{member}' on '{qualified_name}' was {action}. The public API is
      frozen; bump the major version and update the design doc to change it.

  # Variant B: freeze only the operations (methods) of the domain model, ignoring
  # attribute churn, and only for a named set of classes.
  - id: freeze-domain-methods
    type: frozen-members
    severity: warning
    scope: diff
    classes:
      - "myapp.domain.Order"
      - "myapp.domain.Invoice"
    kinds: ["operation"]          # attribute | operation (default: both)
    members: ["*"]                # member-name/signature globs (default: all)

  # Freeze the architectural-rule TAGS recorded in the baseline: removing or
  # weakening @sealed/@immutable/@layer/… on these classes fails.
  - id: freeze-architectural-tags
    type: frozen-rules
    severity: error
    scope: diff
    classes: ["myapp.**"]
    message: >
      Architectural tag '{rule}' on '{qualified_name}' was {action}. These tags
      encode deliberate constraints — re-add it, or run
      `cdec check --automatic-exceptions reference` to deliberately retire it.

  # ─────────────────────────── dependency rules (scope: snapshot) ───────────────────────

  # Class-level: nothing in the domain may touch a concrete HTTP client.
  - id: domain-no-http-client
    type: forbidden-references
    severity: error
    from: ["myapp.domain.**"]
    to:   ["myapp.infra.HttpClient", "myapp.infra.http.**"]
    message: "{source} must not reference {target}; depend on an interface instead."

  # Package-level: the domain package must not depend on the UI package.
  - id: domain-must-not-depend-on-ui
    type: forbidden-package-references
    severity: error
    from: ["myapp.domain.**"]
    to:   ["myapp.ui.**"]
    message: |
      The domain layer must stay UI-agnostic ({source} -> {target}).
      Move presentation concerns into myapp.ui, or invert the dependency.

  # No import cycles between packages.
  - id: no-package-cycles
    type: no-cyclic-package-dependencies
    severity: error
    message: "Package dependency cycle detected: {cycle}."

  # Layered architecture: each layer may only reference the layers listed.
  # Reads @layer("name") tags on classes; an empty list means "depends on nothing".
  - id: enforce-layering
    type: layer-dependencies
    severity: error
    allow:
      ui:      [domain]
      domain:  [data]
      data:    []
    message: >
      {source} ({source_layer}) may not reference {target} ({target_layer}).
      Allowed targets for '{source_layer}' are restricted by the layer matrix.

  # ─────────────────────────── shape rules (scope: snapshot) ────────────────────────────

  # Flag classes that nothing references and that reference nothing (dead code),
  # excluding declared entry points and framework-managed base classes.
  - id: no-dangling-classes
    type: dangling-classes
    severity: warning
    entry_points:                 # globs that are allowed to be unreferenced
      - "myapp.cli.**"
      - "myapp.Main"
    framework_bases:              # subclasses of these are never "dangling"
      - "django.db.models.Model"
      - "unittest.TestCase"
    message: "'{qualified_name}' is unreferenced — dead code, or a missing wiring?"

  # Naming convention: every subclass of IFactory must end in "Factory".
  - id: factories-must-end-in-Factory
    type: subclass-naming
    severity: error
    base: "IFactory"
    name_pattern: ".*Factory$"
    message: "{name} extends {base} but doesn't match /{pattern}/."

  # A second naming rule: repositories.
  - id: repositories-naming
    type: subclass-naming
    severity: warning
    base: "myapp.data.Repository"
    name_pattern: ".*Repository$"

  # Cap coupling: no class may reference more than 12 others.
  - id: limit-fanout
    type: max-class-fanout
    severity: warning
    limit: 12
    message: "'{qualified_name}' references {fanout} classes (limit {limit}); split it up."

  # ──────────────────────── source rules (scope: snapshot) ─────────────────────────
  # These three re-read the code rather than the model. They used to be separate
  # commands; they are rule types now, so `cdec check` is the whole gate.

  # Does the implementation obey the constraint tags written on it? Inspects
  # method bodies. `rules:` narrows it to a subset, which is how you adopt one
  # tag at a time on a codebase that cannot pass all of them yet.
  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error
    rules: [no-instantiation, factory, immutable, sealed]
    ignore:
      - "tests.**"
    message: |
      [{rule}] {message}
      A constraint tag is a promise the code has to keep. Route the call through
      the designated collaborator, or widen the tag with `allow=[...]` — do not
      delete it.

  # A frozen body may not change at all. Digests live in the `locks:` section at
  # the end of this file; record new ones with
  # `cdec check --automatic-exceptions locks`.
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    include_docstrings: false     # do docstring edits count as implementation changes?
    targets:                      # freeze these WITHOUT needing a tag in the source
      - "myapp.pricing.**"

  # The wall behind the scalpels: any structural deviation from the reference
  # model at all, including the access-level and modifier changes the diff engine
  # cannot see. `categories:` narrows it if the full gate is too strict.
  - id: public-shape-is-frozen
    type: reference-architecture
    severity: error
    reference: .cdec/reference.xmi
    message: |
      [{category}] {message}
      If this change is intended, re-snapshot with
      `cdec check --automatic-exceptions reference` and commit reference.xmi in
      the same pull request.

  # An entry kept on the books but disabled — `off` skips it entirely.
  - id: experimental-rule
    type: dangling-classes
    severity: off

# ───────────────────────────────────────────────────────────────────────────────
# Below this point the tool writes. Everything above it is yours, and a tool
# write preserves it byte for byte.

# >>> cdec: managed section — rewritten by `cdec check --automatic-exceptions`
# >>> and by `cdec exceptions ...`. Edit the rules above this line, not below it.
exceptions:
- key: V-7C1E90AB
  engine: check
  rule: no-removed-classes
  qualified_name: myapp.legacy.OldThing
  reason: replaced by myapp.core.Thing in ARCH-42
  added: '2026-08-04T09:00:00+00:00'
  added_by: fran
locks:
- target: myapp.pricing.compute_tax
  kind: function
  algo: py-ast/1
  digest: def9d237e48b6d2aae2cc46251c3b670d563130c551bf3116d394a097fe35863
  file: myapp/pricing.py
  locked_at: '2026-08-02T21:00:38+00:00'
  locked_by: alice
  reason: tax rule signed off by finance
```

---

## 6. Exit codes

Every command returns `0` on success. Non-zero codes for CI gating:

| Command | `1` | `2` |
|---------|-----|-----|
| `cdec check` | Any violation at or above `--fail-on`, from any rule type | Missing or invalid `rules.yaml`, unknown rule type, or a language mismatch in a diff |
| `cdec exceptions patch` / `allow` | A key matched no current issue, was malformed, or named a lock | Config error, or an unreadable ledger |
| `cdec exceptions remove` | A key was not accepted in the first place | Unreadable ledger |
| `cdec render` | Requested diagram not found | Graphviz `dot` not installed |
| `cdec reference set` / `show` | — | Model unreadable, or unresolvable arguments |
| `cdec parse` / `diff*` / `convert` / `init` / `update*` | Operation error (e.g. refused overwrite, diff language mismatch) | — |
| `cdec enforce` / `cdec lock` / `cdec reference test` | — | Retired — prints the rule type that replaced it |

`cdec check` is the only exit code CI needs. Every rule type you switched on contributes to
it, so there is no way to satisfy the gate by running part of it.

Two things a pipeline should read from `--json-out` rather than the exit code:
`summary.bypassed` (a `--bypass-locks` run passes, and a protected branch should reject it
anyway) and `summary.skipped` (a rule that could not run, which is not a failure but is
also not a pass).

`cdec parse`, `cdec diff*`, and the parsers do **not** require Graphviz; only `cdec render`
and the viewer's SVG endpoint do.

---

## 7. CI/CD recipes

### 7.1 Which rules to switch on

The pipeline step is always the same:

```bash
cdec check
```

What it enforces is decided in `rules.yaml`, not on the command line:

- **Freeze the whole architecture** → add `reference-architecture`. Any structural change
  fails until a reviewer runs `cdec check --automatic-exceptions reference` and commits the
  new `reference.xmi`.
- **Targeted, rule-by-rule governance** → add the model rules you want: dependency
  direction, layering, naming, cycles, fanout, drift.
- **Make tagged code honour its tags** → add `tag-conformance`.
- **Freeze specific implementations** → tag them `@locked` and add
  `implementation-locks`.

They compose. A pragmatic default for a team onboarding external contributors is all four,
with `reference-architecture` as the hard backstop behind the specific rules that carry
semantic meaning.

The gate communicates purely through its **exit code**, so it slots into any CI system
without parsing output. Add `--json-out` when you want a machine-readable artefact too.

### 7.2 When the gate blocks a change you want to keep

The failing report names every issue with a stable key, so accepting one is a two-command
round trip that leaves a reviewable record:

```bash
cdec check --log-out check.log          # fails; every line carries a V-/F-/L-/R- key
#  …mark the lines you accept with [ALLOW: why]…
cdec exceptions patch --file check.log  # records them in .cdec/rules.yaml
git add .cdec/rules.yaml                # the decision goes through code review
```

Or, when you already know which issue you mean (and for agents driving the CLI):

```bash
cdec exceptions allow V-DD3EA5B2 --reason "agreed in ARCH-42"
```

Adopting a rule on an existing codebase is the bulk version of the same thing:

```bash
cdec check --automatic-exceptions rules   # grandfather today's violations
```

Two habits keep this from turning into a rubber stamp:

- **Require a reason.** It ends up in the diff a reviewer reads.
- **Run `cdec exceptions prune` periodically.** An exception for an issue that no longer
  exists silently pre-approves the next one just like it.

A lock violation (`L-`) is deliberately outside this loop — it needs
`cdec check --automatic-exceptions locks --force`, which produces its own reviewable diff.

### 7.3 Generated helper scripts

`cdec` can emit ready-made wrappers (`cdec-ci.sh` and `cdec-ci.bat`) from the interactive
session. They are one line of real work, because the gate is one command:

```bash
#!/usr/bin/env bash
set -euo pipefail
python -m code_constraints.cli check --config .cdec --source .
echo "code-constraints checks passed."
```

### 7.4 GitHub Actions

```yaml
name: architecture
on: [pull_request]

jobs:
  constraints:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }            # need history for --base-ref
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install code-constraints

      - name: Architectural constraints
        run: cdec check --base-ref origin/${{ github.base_ref }} --json-out report.json

      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: constraint-report
          path: report.json
```

`fetch-depth: 0` matters whenever you use `--base-ref` — the runner needs the baseline
commit in history. Drop `--base-ref` to gate against the committed `reference.xmi` instead.

When a change is intentional, the author accepts it locally — `cdec exceptions allow` for a
single issue, or `cdec check --automatic-exceptions reference` for an approved
architectural change — and commits the updated `.cdec/` in the same pull request, so the
delta is visible to reviewers.

### 7.5 GitLab CI

```yaml
architecture:
  image: python:3.11
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  before_script:
    - pip install code-constraints
  script:
    - cdec check --base-ref origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME --json-out report.json
  artifacts:
    when: always
    paths: [report.json]
```

### 7.6 Pre-commit hook

Catch drift before it is even pushed:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: cdec-check
        name: cdec check
        entry: cdec check
        language: system
        pass_filenames: false
        always_run: true
```

### 7.7 Rejecting bypassed runs

A `--bypass-locks` run passes on purpose, so a protected branch has to reject it
explicitly:

```bash
cdec check --json-out report.json
python -c "
import json, sys
if json.load(open('report.json'))['summary'].get('bypassed'):
    sys.exit('locks were bypassed — not allowed on this branch')
"
```

### 7.8 Operating the gate day-to-day

1. A pull request changes the code → the gate fails, listing every violation with its key.
2. The reviewer evaluates whether the change is *intended*.
   - **Unintended** → the author fixes the code; the gate passes.
   - **Intended, and specific** → the author runs `cdec exceptions allow <key> --reason
     "…"`, and the recorded decision is part of the diff.
   - **Intended, and architectural** → the author runs
     `cdec check --automatic-exceptions reference`, commits the new `.cdec/reference.xmi`
     in the same pull request, and the reviewer sees the model delta as part of code
     review.
   - **Intended, and inside frozen code** → a lead runs
     `cdec check --automatic-exceptions locks --force`, which rewrites the `locks:` section
     behind CODEOWNERS.

This makes every change to the architecture an explicit, reviewable event rather than
something that slips through unnoticed.
