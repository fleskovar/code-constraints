# Human-readable case folders

Every folder under here is a **hand-solvable proof of one constraint in one language**.
The whole contract is on disk — a source tree, an expected-findings file, and a `README.md`
whose walkthrough derives the second from the first by hand. A developer who has never seen
the engine can read the inputs, apply the rules in the README, and arrive at the output
without running anything. When they can't, the build turns red.

These sit *on top of* the ordinary unit tests in `tests/test_*.py`, they do not replace
them. The unit tests cover the input space (options, globs, edge cases) against synthetic
`Project` models; these cover the **canonical behaviour of each constraint against real
source**, readably.

## Addressing

A case is addressed by its folder path, `<engine>/<constraint>/<language>`:

```
tests/cases/check/subclass-naming/python/
tests/cases/enforce/sealed/csharp/
tests/cases/reference/gate/typescript/
```

That triple is a unique id, so single-case constraints need no further segment. **`lock/locked`
is the one constraint with several cases per language**, so it keeps a short fourth segment
named after the violation kind it proves:

```
tests/cases/lock/locked/python/changed     tests/cases/lock/locked/python/unlocked
tests/cases/lock/locked/python/reformat     tests/cases/lock/locked/python/missing
tests/cases/lock/locked/python/removed      tests/cases/lock/locked/python/glob
```

`<engine>` is one of `check` (A), `enforce` (B), `lock` (C), `reference` (D).

## Layout of one case folder

```
<case>/
    inputs/
        case.yaml         which engine + language to run (the ambient inputs, written down)
        src/              the source tree under test                    (required)
        baseline/         the "agreed" tree — reference / lock / diff   (when the engine needs one)
        rules.yaml        the .cdec/rules.yaml body                     (Engine A only)
    outputs/
        <engine>.json     the expected findings, canonicalised
    README.md             the walkthrough
```

Adding a case is **adding a folder** — `tests/test_case_folders.py` discovers them from
disk and never needs editing. `tests/case_runner.py` runs each engine and canonicalises its
output.

## Running

```bash
make test-cases                                   # all of them
make test-case  CASE=check/subclass-naming/python # one
make debug-case CASE=check/subclass-naming/python # one, under pdb
```

In VS Code, use the **"Debug one case folder"** launch configuration (`.vscode/launch.json`)
and paste the case id when prompted — it drops you into the runner with `justMyCode` off, so
you can step straight into the engine.

## What the baselines pin, and what they leave out

The expected-findings file records the **identity** of each finding — which rule/deviation
fired on which element, with the discriminator the review key is derived from. It
deliberately omits messages (prose that gets rewritten), file paths (a Windows/POSIX hazard)
and line numbers (they move when someone adds a comment). Each engine writes a differently
named file:

| Engine | File | Row shape |
| --- | --- | --- |
| `check` | `outputs/violations.json` | `{rule, severity, element, member?}` |
| `enforce` | `outputs/findings.json` | `{rule, element, detail}` |
| `lock` | `outputs/lock_violations.json` | `{kind, target}` |
| `reference` | `outputs/deviations.json` | `{category, element, member?}` |

**The lock cases contain no sha256.** `inputs/baseline/` is the source as it stood when the
lock was approved; the runner digests it to build the ledger, then verifies `inputs/src/`
against it. So a reader can reason about the freeze, and a fingerprinter change surfaces as a
real diff rather than a stale opaque hash.

## Regenerating a baseline

`UPDATE_BASELINES=1 make test-cases` (or `make update-cases`) rewrites every
`outputs/*.json` from current behaviour. This is a loaded gun:

1. A regenerated baseline is **a diff a human reads line by line** before committing.
2. **Never regenerate to turn a red build green.** A red case is a regression until proven
   otherwise; a genuine requirement change gets a *new* case, not an overwritten one.
3. The regenerating commit changes baselines and nothing else.

## Coverage

`docs/RULES_CATALOGUE.md` carries the full checklist — every constraint × language, with a
link to the case that proves it. That table is the source of truth for what exists here.
