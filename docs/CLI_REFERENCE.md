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
   - [Drift vs the reference gate](#drift-cdec-check-vs-the-reference-gate-cdec-reference-test)
2. [Command reference](#2-command-reference)
   - [Project setup](#21-project-setup)
   - [Parsing, rendering & diffing](#22-parsing-rendering--diffing)
   - [Architecture enforcement](#23-architecture-enforcement) — `check` (A), `enforce` (B), `lock` (C)
   - [Accepting known violations](#24-accepting-known-violations-cdec-baseline) — the review loop
   - [The reference gate](#25-the-reference-gate-cdec-reference)
   - [Web viewer & the design loop](#26-web-viewer)
3. [The `.cdec/` configuration folder](#3-the-cdec-configuration-folder)
   - [`config.yaml`](#31-configyaml)
   - [`rules.yaml`](#32-rulesyaml)
   - [`baseline.yaml`](#33-baselineyaml)
   - [`reference.xmi`](#34-referencexmi)
   - [`.gitignore` & `cache/`](#35-gitignore--cache)
4. [Architectural-rule tags](#4-architectural-rule-tags) — *full detail: [catalogue §2](RULES_CATALOGUE.md#2--source-level-constraint-tags)*
5. [Lint-rule catalogue (`rules.yaml` types)](#5-lint-rule-catalogue-rulesyaml-types) — *full detail: [catalogue §1](RULES_CATALOGUE.md#1--configured-rules-cdecrulesyaml)*
   - [Complete sample `rules.yaml`](#complete-sample-rulesyaml)
6. [Exit codes](#6-exit-codes)
7. [CI/CD recipes](#7-cicd-recipes)

---

## 1. Mental model

code-constraints parses a source tree into a language-agnostic UML model, serialised to
**XMI 2.1** as the on-disk source of truth. From there it can render diagrams, diff
two snapshots, and enforce architectural constraints.

There are **four independent enforcement mechanisms**. They share a rule catalogue
but no logic, and answer different questions:

| Mechanism | Command | Question it answers | Reads method bodies? | Needs a baseline? |
|-----------|---------|---------------------|----------------------|-------------------|
| **Drift** (Engine A) | `cdec check` | "Did the architecture drift from the committed baseline / a git ref?" | No (model only) | Yes (for `diff`-scope rules) |
| **Conformance** (Engine B) | `cdec enforce` | "Does the code actually obey its architectural-rule tags right now?" | Yes | No |
| **Freeze** (Engine C) | `cdec lock check` | "Did this specific implementation change **at all**?" | Yes (digests them) | Yes (`.cdec/locks.yaml`) |
| **Reference gate** | `cdec reference test` | "Has *anything* structural changed vs the reference snapshot?" | No (model only) | Yes (the reference XMI) |

- **`cdec check`** is configurable: you opt into specific rules via `.cdec/rules.yaml`,
  and pre-existing violations can be grandfathered in `.cdec/baseline.yaml`.
- **`cdec enforce`** is tag-driven: it inspects bodies for `@no_instantiation`,
  `@factory`, `@immutable`, and structural `@sealed`.
- **`cdec lock check`** is the strictest and narrowest: it freezes a specific class or
  function *body* by digesting its normalised AST. Reformatting, renaming a local, moving
  the function down the file, or editing a comment do **not** trip it; any semantic change
  does. Scope is opt-in per element via `@locked` / `[Locked]`.
- **`cdec reference test`** is an all-or-nothing structural gate: it fails on *every*
  structural deviation (added/removed classes, members, signature/return-type changes,
  access-level and modifier changes, class-kind changes, base-class changes), with no
  per-rule configuration. Use it when you want to freeze the public shape of a codebase
  and review every change deliberately.

**Choosing between them.** They operate at descending levels of granularity — the
reference gate over the whole public shape, `check` over the rules you name, `enforce`
over tagged bodies, `lock` over individual bodies:

| You want to say | Use |
|---|---|
| "Nothing about the public shape changes without review" | `cdec reference test` |
| "These specific architectural laws are never broken" | `cdec check` |
| "Code tagged with a constraint must actually honour it" | `cdec enforce` |
| "*This function* is settled — nobody touches it" | `cdec lock` |

They compose. `cdec check` runs Engine C automatically whenever the project has locks,
and runs Engine B too with `--enforce` — so a single `cdec check` in CI can gate all
three. The reference gate stays a separate command because it needs no configuration.

### Drift (`cdec check`) vs the reference gate (`cdec reference test`)

These two look alike — both compare the current code against a reference XMI — but they
answer different questions and behave differently. The distinction matters when choosing
your CI gate.

**`cdec check` is a configurable, opt-in policy engine.** It only flags what
`.cdec/rules.yaml` tells it to. With the default empty `rules: []` it passes no matter
what changed. You compose specific rules (`no-new-classes`, `frozen-members`,
`forbidden-references`, …), each with its own severity, `ignore` globs, and a
`baseline.yaml` allowlist to grandfather pre-existing violations.

**`cdec reference test` is an all-or-nothing structural gate.** There is no configuration
and no allowlist. *Any* structural deviation from the reference fails it. You don't tell
it what to care about — it cares about everything.

| | `cdec check` (drift) | `cdec reference test` |
|---|---|---|
| What it flags | Only what `rules.yaml` opts into | Every structural change |
| Configuration | Per-rule (`rules.yaml`) | None |
| Suppress known issues | `baseline.yaml` allowlist | No escape hatch |
| Severity levels | `error` / `warning` / `off`, tuned via `--fail-on` | Binary: any deviation = fail |
| Baseline source | git ref (`--base-ref`) **or** a reference XMI | Reference XMI only |
| Granularity | The class/member/package/dependency/tag rules you choose | Fixed: classes, members, signatures, modifiers, kinds, bases |

#### The subtle technical gap

Even where they overlap — e.g. `check`'s `frozen-members` rule vs the reference gate —
**they detect different things**, because they sit on two different comparison engines:

- `cdec check` reads the statuses produced by `diff_projects` (`src/code_constraints/core/diff.py`).
  That engine matches members by **`signature()`** (`name:type` for attributes,
  `name(params):return_type` for operations) and only marks a *matched* member changed
  when its architectural-rule **tags** differ. It is therefore **blind** to:
  - access-level changes (`public` → `private`),
  - modifier changes (`static`, `abstract`, `readonly`),
  - class-kind changes (concrete → abstract).
- `cdec reference test` runs its **own dedicated comparator**
  (`src/code_constraints/reference/compare.py`) that walks both models field-by-field and *does* catch
  all of those.

So a PR that flips a public method to private, or makes a concrete class abstract, would
**pass** `cdec check` (even with `frozen-members` enabled) but **fail** `cdec reference
test`. This is the main reason the reference gate exists as a separate mechanism rather
than just another `check` rule.

#### When to use which

- **Reference gate** — "freeze the shape of this codebase; nothing changes without a
  reviewer deliberately accepting it." The intended-change workflow is: gate fails →
  reviewer approves → author runs `cdec reference update`, commits the new `reference.xmi`
  → gate passes. Ideal for stable public APIs or a locked architecture.
- **`cdec check`** — "enforce these specific architectural laws" (no UI→domain
  references, no package cycles, factories must be named `*Factory`, don't remove
  classes). Targeted governance where most change is fine but certain rules are sacred.
  It is also the only one of the two that can diff against a **live git ref**
  (`--base-ref origin/main`) instead of a committed snapshot.

They are complementary: many teams run `cdec reference test` as a hard backstop **and**
`cdec check` / `cdec enforce` for the rules that need semantic meaning (dependencies, tags,
naming).

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

`--lang` is auto-detected from `.cdec/config.yaml` when omitted. Use `--no-agents` /
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

### 2.3 Architecture enforcement

#### `cdec check` — drift detection (Engine A)

Runs the architectural-lint rules from `.cdec/rules.yaml` over the parsed model,
optionally diffing against a baseline first. Exits non-zero when violations remain
after the baseline allowlist is applied.

```
cdec check [--config .cdec] [--source DIR] [--reference XMI] [--base-ref REF] \
          [--fail-on error|warning|none] [--format human|json] \
          [--json-out FILE] [--log-out FILE] [--repo .] [--enforce] \
          [--update-reference] [--update-baseline]
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--config` | `.cdec` | Folder with `config.yaml` + `rules.yaml`. |
| `--source` | from config | Override the source tree. |
| `--reference` | from config / `.cdec/reference.xmi` | Baseline XMI for `diff`-scope rules. |
| `--base-ref` | — | Use a git ref as the baseline instead of a stored XMI (parsed live). Wins over `--reference`. |
| `--fail-on` | `error` | Minimum severity that fails the run: `error \| warning \| none`. |
| `--format` | `human` | `human \| json` stdout format. |
| `--json-out` | from config | Also write a JSON report to a file. |
| `--log-out` | from config | Tee the human report to a log file. |
| `--repo` | `.` | Git repo root (only used with `--base-ref`). |
| `--enforce` | off | Also run Engine B (`cdec enforce`) in the same invocation. |
| `--update-reference` | off | Re-snapshot `reference.xmi` from source and exit. |
| `--update-baseline` | off | Record current violations into `baseline.yaml` and exit. |

Baseline resolution order: `--base-ref` → `--reference` → `config.yaml` `baseline.reference`
→ `.cdec/reference.xmi`. Rules declared `scope: diff` are **skipped** (not failed) when no
baseline is available.

**Common flows**

```bash
# Drift vs the committed reference snapshot
cdec check

# Pre-merge drift vs the target branch (parsed live, no stored XMI needed)
cdec check --base-ref origin/main --json-out lint.json

# Accept the current state as the new baseline / reference
cdec check --update-reference
cdec check --update-baseline
```

#### `cdec enforce` — implementation conformance (Engine B)

Re-parses the source and inspects method bodies to confirm the code obeys its
architectural-rule tags. Independent of any baseline or diff.

```
cdec enforce PATH --lang L [--format human|json] [--json-out FILE] \
             [--config .cdec] [--no-baseline]
```

Checks `no-instantiation`, `factory`, `immutable` (body analysis) and `sealed`
(structural). Exits `1` when any conformance violation is found.

Findings accepted through [`cdec baseline`](#24-accepting-known-violations-cdec-baseline)
are silenced, so a team can adopt a tag without fixing every pre-existing case first;
`--no-baseline` reports them all regardless.

> `no-side-effects` is captured, visualised, diffed and drift-frozen, but its **body
> analysis is deliberately not implemented** — `cdec enforce` will not flag a side-effecting
> method tagged `@no_side_effects`. Treat the tag as documentation plus drift protection.

#### `cdec lock` — implementation freeze (Engine C)

Freezes the *body* of a class or function so it cannot change without an explicit,
reviewable re-baseline. Identity is **AST-derived, not line-based**: inserting code above a
locked function, reformatting it, renaming a local variable, or editing a comment never
trips the lock. Any semantic change does.

Declare intent in the source with `@locked` / `[Locked]` / `@cdec locked`, then record the
approved digest in `.cdec/locks.yaml`. Available for **python, csharp, odin, lua and
julia** — the languages with an AST fingerprinter. TypeScript and Svelte are refused by
name rather than reporting "nothing locked".

```
cdec lock list  [SOURCE] [--lang L] [--config .cdec] [--lockfile F] [--all] [--json]
cdec lock check [SOURCE] [--lang L] [--config .cdec] [--lockfile F] \
                [--bypass] [--bypass-reason TEXT] [--format human|json] [--json-out FILE]
cdec lock set   [SOURCE] [--lang L] [--config .cdec] [--lockfile F] \
                [--target GLOB]... [--force] [--reason TEXT] [--owner NAME] [--dry-run]
cdec lock remove --target GLOB... [--config .cdec] [--lockfile F]
```

| Subcommand | Purpose |
|---|---|
| `list` | Show what is frozen and whether each entry still matches. `--all` also lists every *lockable* element, so you can see what you could freeze. |
| `check` | The CI gate. Exits `1` if any frozen implementation changed. |
| `set` | Record current implementations as the approved baseline. |
| `remove` | Drop entries from the ledger (also delete the tag in source, or the next `check` reports them as un-baselined). |

**`cdec lock check` catches five distinct failures**, each reported with its own kind:

| Kind | Headline | Meaning |
|---|---|---|
| `changed` | frozen implementation changed | The body's digest no longer matches the ledger. |
| `missing` | declared `@locked` but not baselined | An element is tagged `@locked` but was never recorded via `lock set`. |
| `removed` | frozen element no longer exists | A locked element was deleted or renamed. |
| `unlocked` | `@locked` tag was removed | The tag was deleted while the ledger entry remains. |
| `algo-mismatch` | digest algorithm changed | The ledger was written by a different fingerprinter — re-baseline required. |

These are the `kind` values in the JSON report (`--format json` / `--json-out`), so CI can
branch on them.

**The privilege boundary.** `cdec lock set` freely *adds* locks for newly tagged elements,
so it is safe for anyone to run and can never erase evidence that frozen code changed.
Accepting a change to already-locked code — or pruning an entry whose tag was deleted —
requires `--force`, which shows up as a reviewable diff on `.cdec/locks.yaml`:

```bash
cdec lock set                                   # safe: only adds new locks
cdec lock set --target orders.Receipt.formatted --force \
              --reason "approved settlement fix" --owner alice
```

Gate `.cdec/locks.yaml` with a CODEOWNERS entry to keep re-baselining a lead-only action.

**Bypass** is `--bypass` (or `CDEC_LOCK_BYPASS=1`). It still collects violations and prints
an audit banner, and sets `summary.bypassed` in the JSON report so CI can reject bypassed
runs rather than silently accepting them.

**Target identity.** Classes use the UML qualified name (`orders.Receipt`); module-level
Python functions additionally carry the module stem (`orders.billing.compute_tax`), since
two modules in a package may define the same name. Same-named siblings — overloads,
`@property` + its setter — are **grouped into one target**, so adding an overload to a
locked name is itself a violation.

### 2.4 Accepting known violations (`cdec baseline`)

Enforcement that can only ever say *no* gets switched off. `cdec baseline` is the other
half of the loop: read the report, decide which issues are acceptable, record the decision
**with a reason** in `.cdec/baseline.yaml`, and keep moving. The recorded decision is a
committed, reviewable diff — and it can be withdrawn later.

**Every issue prints a stable key.**

```
[no-new-classes] (error)
  - [V-DD3EA5B2] animals.Cat — animals/cat.py:1: New class 'animals.Cat' was added.
```

| Prefix | Engine | Waivable |
|--------|--------|----------|
| `V-` | `cdec check` (A — architectural drift) | yes |
| `F-` | `cdec enforce` (B — implementation conformance) | yes |
| `L-` | `cdec lock` (C — implementation freeze) | **no** — see below |

The key is a hash of *what* the issue is (engine, rule, element, discriminator), never of
*where* it is. Re-running over unchanged code always yields the same key, and inserting
lines above the offending element does not change it — so a waiver survives reformatting.
The flip side is deliberate: a key names an equivalence class, so two identical violations
of one rule on one element share a key and one waiver covers both.

#### Two ways in

**By file** — the review path, for a batch of issues:

```bash
cdec baseline review --out review.txt   # one markable line per issue
#  …edit review.txt, adding [ALLOW] to the lines you accept…
cdec baseline patch --file review.txt
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
cdec baseline allow V-DD3EA5B2 --reason "agreed in ARCH-42"
cdec baseline allow V-DD3EA5B2 F-5BBDCC93        # several at once
```

`--format json` on `check`, `enforce`, and `baseline review` all emit the keys, so an agent
or an MCP server can go report → decision → `allow` without parsing prose.

#### Subcommands

```
cdec baseline review [--config .cdec] [--out FILE] [--all] [--format text|json] \
                     [--source DIR] [--reference XMI] [--base-ref REF] [--repo .]
cdec baseline patch  --file FILE|-  [--reason TEXT] [--dry-run] [--ignore-unknown] …
cdec baseline allow  KEY...         [--reason TEXT] [--dry-run] …
cdec baseline remove KEY...         [--dry-run]
cdec baseline list   [--engine check|enforce] [--format human|json]
cdec baseline prune  [--dry-run]
```

| Command | What it does |
|---------|--------------|
| `review` | Writes every current issue as one markable line. `--all` includes already-accepted ones (mark them `[REMOVE]` to withdraw). |
| `patch` | Applies the `[ALLOW]` / `[REMOVE]` marks in a file. `--file -` reads stdin. |
| `allow` | Accepts issues named by key. |
| `remove` | Withdraws waivers by key, so the issue blocks again. Needs no source parse. |
| `list` | Shows what is accepted, with reason, date, and who granted it. |
| `prune` | Drops waivers whose issue no longer occurs — a stale waiver silently pre-approves a *future* violation of the same rule on the same element. Only prunes engines that actually ran. |

`review`, `patch`, `allow`, and `prune` re-run the engines, and take the same
baseline-resolution options as `cdec check` (`--source`, `--reference`, `--base-ref`,
`--repo`). Pass the same ones you passed to `check`, or the keys won't line up.

**A key that matches no current issue is an error, not a no-op** (exit `1`), because it
almost always means the report being quoted is stale. `--ignore-unknown` downgrades that on
`patch`.

#### Locks are not waivable

`cdec lock` violations appear in the report with an `L-` key, but `baseline allow` refuses
them and prints the privileged command instead:

```
cdec lock set --target orders.Receipt.formatted --force --reason "why"
```

That is by design. Accepting a changed frozen implementation is meant to produce a
reviewable diff on `.cdec/locks.yaml` behind a CODEOWNERS entry; routing it through a
waiver file would quietly undo that guarantee.

### 2.5 The reference gate (`cdec reference`)

A dedicated structural gate that fails on **any** deviation from a stored reference
snapshot — broader than `cdec check` because it also catches access-level changes,
modifier changes (`static`/`abstract`/`readonly`), and class-kind changes that the
signature-based diff does not surface. Designed to auto-reject PRs that alter the
architecture.

All three subcommands resolve their inputs from **explicit arguments with a `.cdec/`
fallback**: `SOURCE` falls back to `config.yaml` `source`, `--lang` to `config.yaml`
`language` (then auto-detection), and `--reference` to `.cdec/reference.xmi`.

#### `cdec reference test`

```
cdec reference test [SOURCE] [--reference XMI] [--lang L] [--config .cdec] \
                   [--json] [--output FILE]
```

| Option | Default | Meaning |
|--------|---------|---------|
| `SOURCE` | from config | Source tree to parse. |
| `--reference` | `.cdec/reference.xmi` | Reference snapshot to compare against. |
| `--lang` | from config / auto | Language. |
| `--config` | `.cdec` | Folder used to resolve omitted args. |
| `--json` | off | Emit the report as JSON instead of human-readable text. |
| `--output` | — | Also write the report (in the chosen format) to a file. |

**Detects:** added/removed classes · added/removed properties · added/removed methods ·
method signature changes · method return-type changes · access-level (visibility)
changes · `static` / `abstract` / `readonly` modifier changes · class-kind changes
(e.g. concrete→abstract) · base-class changes.

**Exit codes:** `0` clean · `1` one or more deviations · `2` reference XMI missing,
language mismatch, or unresolvable arguments.

```bash
# In CI: fail the job if the architecture changed
cdec reference test src/ --lang python --reference .cdec/reference.xmi

# Machine-readable for a pipeline artefact
cdec reference test --json --output reference-report.json
```

#### `cdec reference update`

Snapshot the current architecture into the reference XMI (the deliberate "accept these
changes" step a reviewer runs after approving an architectural change).

```
cdec reference update [SOURCE] [--reference XMI] [--lang L] [--config .cdec]
```

#### `cdec reference set`

Promote an **authored** model file (hand-written or agent-written, `.json` or `.xmi`) to be
the project's reference. This is the "accept the proposal" step of the design loop — where
`reference update` snapshots *what the code is*, `reference set` declares *what the code
should become*.

```
cdec reference set MODEL [--reference XMI] [--config .cdec]
```

After it runs, `cdec check` and `cdec reference test` immediately start constraining
development against the target architecture. Because the target usually contains classes
that do not exist yet, `cdec reference show` will render them as green "still to build".

#### `cdec reference show`

Parse the current code, diff it against the reference, and open the web viewer straight
to the diff — added/removed/changed elements highlighted, with the change walkthrough
populated.

Here the reference XMI is treated as the **target** architecture and the codebase as the
**current** state. So elements present in the reference but missing from the code show as
green additions ("the code still needs to grow this"), and elements in the code but absent
from the reference show as red removals. This is intentionally the inverse of `cdec
reference test` / `diff-vs-xmi`, where the reference is the *old* side.

```
cdec reference show [SOURCE] [--reference XMI] [--lang L] [--config .cdec] \
                   [--host 127.0.0.1] [--port 8765]
```

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

## 3. The `.cdec/` configuration folder

Created by `cdec init`. Commit everything except `cache/`.

```
.cdec/
├── config.yaml      # project settings (language, source, default baseline)
├── rules.yaml       # architectural-lint rule definitions
├── baseline.yaml    # accepted pre-existing violations (allowlist)
├── reference.xmi    # committed reference snapshot
├── README.md        # human notes (generated)
├── .gitignore       # ignores cache/
└── cache/           # transient parse artefacts (gitignored)
```

### 3.1 `config.yaml`

Project-level settings consumed by `cdec check` (and used as the `.cdec` fallback by
`cdec reference`).

```yaml
language: python                 # python | csharp | odin | lua | julia | typescript | svelte
source: .                        # source tree, relative to the project root
baseline:
  reference: .cdec/reference.xmi  # default baseline XMI; null to require --base-ref
output:
  json: null                     # optional default for --json-out
  log: null                      # optional default for --log-out
```

| Key | Required | Meaning |
|-----|----------|---------|
| `language` | yes | Parser to use: `python`, `csharp`, `odin`, `lua`, `julia`, `typescript` or `svelte`. |
| `source` | yes | Directory parsed by `cdec check`, resolved relative to the project root. |
| `baseline.reference` | no | Default baseline XMI. `null` means `cdec check` requires `--base-ref`. |
| `output.json` | no | Default path for the JSON report (`--json-out` overrides). |
| `output.log` | no | Default path for the teed human log (`--log-out` overrides). |

### 3.2 `rules.yaml`

The list of architectural-lint rules `cdec check` runs. Each entry:

```yaml
rules:
  - id: domain-must-not-depend-on-ui   # stable id, referenced from baseline.yaml
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
| `id` | Stable identifier; the key under which violations are listed in `baseline.yaml`. Must be unique. |
| `type` | Which rule to run (catalogue in §5). |
| `severity` | `error` (fails at default `--fail-on`), `warning`, or `off` (rule skipped entirely). |
| `scope` | `diff` rules need a baseline and inspect what changed; `snapshot` rules evaluate the current model. Each type has a sensible default. |
| `message` | Optional explanation printed when the rule fires. Supports `{placeholders}` (see the generated `rules.yaml` comments for the set available per type) and multi-line YAML block scalars. Write these for your teammates — say why the rule exists and how to satisfy it. |
| `ignore` | List of qualified-name globs exempted from the rule (`**` matches across dots). |
| *other keys* | Rule-specific options, e.g. `classes`, `from`/`to`, `base`/`name_pattern`, `allow`, `limit`. |

`rules: []` (the default scaffold) means no rules run — `cdec check` passes trivially
until you opt in.

### 3.3 `baseline.yaml`

The ledger of accepted violations — used to adopt the linter on an existing codebase
without fixing every pre-existing issue at once, and to keep evolving afterwards. Written
by [`cdec baseline`](#24-accepting-known-violations-cdec-baseline) (with a reason attached)
or wholesale by `cdec check --update-baseline`.

```yaml
violations:                              # Engine A — `cdec check`
  no-removed-classes:
    - qualified_name: myapp.legacy.OldThing
      key: V-7C1E90AB
      reason: replaced by myapp.core.Thing in ARCH-42
      added: '2026-08-04T09:00:00+00:00'
      added_by: fran
  frozen-members:
    - qualified_name: myapp.api.Client
      signature: "operation:fetch(url:str):dict"
      key: V-2F4A18DE
findings:                                # Engine B — `cdec enforce`
  no-instantiation:
    - qualified_name: myapp.billing.Ledger
      detail: "settle->Invoice"
      key: F-5BBDCC93
```

An entry is matched by its identity — `(rule, qualified_name, signature/detail)` — with
`key` as the human-quotable form of exactly that tuple. **Older baselines without `key:`
load unchanged**: the key is derived, so there is nothing to migrate. A matching violation
is reported as *suppressed* rather than failing the run; new violations of the same rule on
other elements still fail.

`reason`, `added`, and `added_by` are metadata only — they exist so the commit that accepts
a violation explains itself to the next reviewer.

Engine C (`cdec lock`) has no section here on purpose: a frozen implementation is
re-baselined through `cdec lock set --force`, which is separately reviewable.

### 3.4 `reference.xmi`

The committed XMI snapshot of the architecture. It is the baseline for:

- `cdec check`'s `diff`-scope rules (when `--base-ref` is not given), and
- `cdec reference test` / `cdec reference show`.

Regenerate it — the explicit "accept this change" action — with either:

```bash
cdec check --update-reference     # writes .cdec/reference.xmi
cdec reference update             # same destination, no rules.yaml required
```

Commit the regenerated file in the same PR that makes the architectural change, so
reviewers see the model delta in the diff.

### 3.5 `.gitignore` & `cache/`

`.cdec/.gitignore` ignores `cache/`, which holds transient parse artefacts. Everything
else in `.cdec/` should be committed.

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
| `no-instantiation` | `@no_instantiation` / `[NoInstantiation]` | class, method | `enforce` (body) | May not construct objects, except types listed in `allow`. |
| `factory` | `@factory` / `[Factory]` | class, method | `enforce` (body) | The designated constructor of the types in `creates`; construction elsewhere is forbidden. |
| `immutable` | `@immutable` / `[Immutable]` | class | `enforce` (body) | Fields may not be reassigned after construction. |
| `sealed` | `@sealed` / `[Sealed]` | class | `enforce` (structural) | May not be subclassed (composition over inheritance). |
| `no-side-effects` | `@no_side_effects` / `[NoSideEffects]` | method | drift only | Must be side-effect-free. Body analysis is deferred; the tag is still captured, visualised, and frozen. |
| `layer` | `@layer("name")` / `[Layer("name")]` | class | `check` (`layer-dependencies`) | Assigns the class to an architectural layer for dependency-direction checks. |
| `locked` | `@locked` / `[Locked]` | class, method, function | `lock check` (Engine C) | The implementation is frozen: any semantic change to the body fails CI until re-baselined. Optional `reason` / `owner` are recorded in the ledger and echoed in violations. |

Applying or removing the `locked` tag never changes a digest — the fingerprinters strip it
recursively, including a method-level lock nested inside a locked class — so tagging code
does not require an immediate re-baseline of everything around it.

To freeze the *presence* of these tags over time (so removing or weakening one fails CI),
add a `frozen-rules` entry to `rules.yaml` (see §5). That is drift detection on the tags
themselves — distinct from `cdec enforce`, which checks the code actually obeys them.

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
#
# Common fields on every entry:
#   id        unique, stable; the key violations appear under in baseline.yaml
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
      `cdec check --update-reference` to deliberately retire it.

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

  # An entry kept on the books but disabled — `off` skips it entirely.
  - id: experimental-rule
    type: dangling-classes
    severity: off
```

---

## 6. Exit codes

Every command returns `0` on success. Non-zero codes for CI gating:

| Command | `1` | `2` |
|---------|-----|-----|
| `cdec check` | Violations at/above `--fail-on`, or `--enforce` found conformance issues, or a lock was broken | Config/rules error, or language mismatch in a diff |
| `cdec enforce` | One or more conformance violations | — |
| `cdec baseline patch` / `allow` | A key matched no current issue, was malformed, or named a non-waivable lock | Config error, or an unreadable `baseline.yaml` |
| `cdec baseline remove` | A key wasn't waived in the first place | Unreadable `baseline.yaml` |
| `cdec lock check` | One or more lock violations (unless `--bypass`) | Unsupported language, or unreadable ledger |
| `cdec reference test` | One or more structural deviations | Reference XMI missing, language mismatch, or unresolvable arguments |
| `cdec render` | Requested diagram not found | Graphviz `dot` not installed |
| `cdec parse` / `diff*` / `convert` / `init` / `update*` | Operation error (e.g. refused overwrite, diff language mismatch) | — |

Note that `cdec check` folds Engine C in automatically: if the project has ledger entries
or `lock.targets:` globs, a broken lock fails `cdec check` even without `--enforce`. Use
`--no-locks` to opt out.

`cdec parse`, `cdec diff*`, and the parsers do **not** require Graphviz; only `cdec render`
and the viewer's SVG endpoint do.

---

## 7. CI/CD recipes

### 7.1 Which gate to run

- **Freeze the whole architecture** → `cdec reference test`. Any structural change fails
  until a reviewer runs `cdec reference update` and commits the new `reference.xmi`.
- **Targeted, rule-by-rule governance** → `cdec check` (drift) and/or `cdec enforce`
  (conformance), opting into specific rules in `rules.yaml`.
- **Freeze specific implementations** → tag them `@locked` and run `cdec lock check`
  (folded into `cdec check` automatically once the ledger is non-empty).
- You can combine them — `cdec check --enforce` runs Engines A, B and C in one invocation,
  and you can additionally run `cdec reference test` as a hard backstop.

A pragmatic default for a team onboarding external contributors:

```bash
cdec check --enforce          # Engines A + B + C, one exit code
cdec reference test           # hard structural backstop
```

All gates communicate purely through **exit codes**, so they slot into any CI system
without parsing output. Add `--json-out` / `--output` when you want a machine-readable
artefact too.

### 7.2 When a gate blocks a change you want to keep

The failing report names every issue with a stable key, so accepting one is a two-command
round trip that leaves a reviewable record:

```bash
cdec check --log-out check.log        # fails; every line carries a V-/F-/L- key
#  …mark the lines you accept with [ALLOW: why]…
cdec baseline patch --file check.log  # records them in .cdec/baseline.yaml
git add .cdec/baseline.yaml           # the decision goes through code review
```

Or, when you already know which issue you mean (and for agents driving the CLI):

```bash
cdec baseline allow V-DD3EA5B2 --reason "agreed in ARCH-42"
```

Two habits keep this from turning into a rubber stamp:

- **Require a reason.** It ends up in the diff a reviewer reads.
- **Run `cdec baseline prune` periodically.** A waiver for an issue that no longer exists
  silently pre-approves the next one just like it.

A lock violation (`L-`) is deliberately outside this loop — it needs
`cdec lock set --target … --force`, which produces its own reviewable diff.

### 7.2 Generated helper scripts

`cdec` can emit ready-made wrappers (`cdec-ci.sh` and `cdec-ci.bat`) that run `cdec check`
then `cdec enforce`, propagating non-zero exits. They are a good starting point for a CI
step:

```bash
#!/usr/bin/env bash
set -euo pipefail
python -m code_constraints.cli check --config .cdec --source .
python -m code_constraints.cli enforce . --lang python
echo "code-constraints checks passed."
```

### 7.3 GitHub Actions

**Reference gate** — reject PRs that change the architecture:

```yaml
name: architecture
on: [pull_request]

jobs:
  reference-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"        # or: pip install code-constraints
      - name: Reject architectural drift
        run: |
          cdec reference test src/ \
            --lang python \
            --reference .cdec/reference.xmi \
            --json --output reference-report.json
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: reference-report
          path: reference-report.json
```

When a change is intentional, the author runs `cdec reference update` locally, commits
the regenerated `.cdec/reference.xmi`, and the gate passes — the model delta is visible
in the PR diff for reviewers.

**Drift + conformance** with a baseline against the target branch:

```yaml
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }            # need history for --base-ref
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - name: Lint architecture vs target branch
        run: cdec check --base-ref origin/${{ github.base_ref }} --json-out lint.json
      - name: Enforce rule tags
        run: cdec enforce src/ --lang python
```

`fetch-depth: 0` matters whenever you use `--base-ref` — the runner needs the baseline
commit in history.

### 7.4 GitLab CI

```yaml
architecture:
  image: python:3.11
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  before_script:
    - pip install -e ".[dev]"
  script:
    - cdec reference test src/ --lang python --reference .cdec/reference.xmi
    - cdec check --base-ref origin/$CI_MERGE_REQUEST_TARGET_BRANCH_NAME
    - cdec enforce src/ --lang python
```

### 7.5 Pre-commit hook

Catch drift before it is even pushed:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: cdec-reference
        name: cdec reference test
        entry: cdec reference test src/ --lang python --reference .cdec/reference.xmi
        language: system
        pass_filenames: false
        always_run: true
```

### 7.6 Operating the gate day-to-day

1. A PR changes the code's structure → the gate fails, listing every deviation.
2. The reviewer evaluates whether the change is *intended*.
   - **Unintended** → the author reverts the structural change; the gate passes.
   - **Intended** → the author runs `cdec reference update` (or `cdec check
     --update-reference`), commits the new `.cdec/reference.xmi` in the same PR, and the
     gate passes. The reviewer sees the architectural delta as part of code review.

This makes every change to the architecture an explicit, reviewable event rather than
something that slips through unnoticed.
