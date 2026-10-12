# Rule types for `.cdec/rules.yaml`

Each entry has the common fields `id`, `type`, `severity`, `scope`, `message` and `ignore`.
The tables below give the options of each type. A `{name}` is a placeholder that you can
use in `message:`.

| Type | Default scope | What fails |
| --- | --- | --- |
| [`no-new-classes`](#no-new-classes) | diff | A class that is not in the baseline |
| [`no-removed-classes`](#no-removed-classes) | diff | A baseline class that is gone |
| [`frozen-members`](#frozen-members) | diff | A member that was added, removed or changed |
| [`frozen-rules`](#frozen-rules) | diff | A constraint tag that was removed or changed |
| [`forbidden-references`](#forbidden-references) | snapshot | A class that refers to a forbidden class |
| [`forbidden-package-references`](#forbidden-package-references) | snapshot | A package that refers to a forbidden package |
| [`no-cyclic-package-dependencies`](#no-cyclic-package-dependencies) | snapshot | A cycle between packages |
| [`layer-dependencies`](#layer-dependencies) | snapshot | A reference between layers that the matrix does not permit |
| [`dangling-classes`](#dangling-classes) | snapshot | A class that nothing refers to |
| [`subclass-naming`](#subclass-naming) | snapshot | A subclass whose name does not match a pattern |
| [`max-class-fanout`](#max-class-fanout) | snapshot | A class that refers to too many classes |
| [`tag-conformance`](#tag-conformance) | — | Code that does not obey its constraint tags |
| [`implementation-locks`](#implementation-locks) | — | A frozen implementation that changed |
| [`reference-architecture`](#reference-architecture) | — | Any structural difference from the reference |

## What a reference is

Class A refers to class B when one of these resolves to B:

- The type of an attribute of A. Collection wrappers are removed: `List<B>`, `B[]`,
  `dict[str, B]` and `Optional[B]` all resolve to B.
- The type of a parameter or the return type of a method of A.
- A use of B in a method body of A.
- A base class of A.

A package refers to a package when one of its classes refers to a class of the other
package. There is no separate import graph.

---

## Structural drift

These rules compare the code with a baseline. They need `.cdec/reference.xmi` or
`--base-ref`.

### `no-new-classes`

Fails when a class is in the code and not in the baseline. Use it on a frozen subsystem or
on generated code. On most codebases, use `severity: warning`.

| Option | Default | Meaning |
| --- | --- | --- |
| `ignore` | `[]` | Qualified-name globs that are exempt. |

Placeholders: `{qualified_name}`

```yaml
  - id: no-new-classes
    type: no-new-classes
    severity: warning
    ignore: ["tests.**"]
    message: |
      New class '{qualified_name}' appeared. Agree each new type in this
      subsystem first: add it to the model and run `cdec propose`.
```

### `no-removed-classes`

Fails when a baseline class is gone. A rename also fails, because a rename is a removed
class and an added class.

| Option | Default | Meaning |
| --- | --- | --- |
| `ignore` | `[]` | Qualified-name globs that are exempt. |

Placeholders: `{qualified_name}`

```yaml
  - id: no-removed-classes
    type: no-removed-classes
    severity: error
    message: |
      Class '{qualified_name}' was removed. That breaks each caller that imports it.
      Deprecate it for one release, or get the removal approved as a design change.
```

### `frozen-members`

Fails when an attribute or a method of a matched class is added, removed or changed.
Members are matched by signature. A changed parameter list shows as one removed member and
one added member.

| Option | Default | Meaning |
| --- | --- | --- |
| `classes` | `["*"]` | The classes that are frozen. |
| `members` | `["*"]` | The members, matched against the name or the full signature. |
| `kinds` | `[attribute, operation]` | Limit the rule to one kind of member. |
| `ignore` | `[]` | Classes that are exempt. |

Placeholders: `{qualified_name}`, `{member}`, `{kind}`, `{action}` (`added`, `removed` or `changed`)

```yaml
  - id: notification-contract-is-frozen
    type: frozen-members
    severity: error
    classes: ["notifications.Notification"]
    kinds: [operation]
    members: ["send*"]
    message: |
      The {kind} '{member}' on '{qualified_name}' was {action}. Notification is a
      public contract, and each notifier implements it. Keep the signature stable.
```

This rule does not see a change of visibility, of `static` or `abstract`, or of the class
kind. Use `reference-architecture` for those.

### `frozen-rules`

Fails when a constraint tag of the baseline is removed from the same element, or when its
arguments change. Without this rule, a developer can delete a tag to make a check pass.

A tag is satisfied only by an identical tag: the same name and the same arguments. Each
change of an argument is reported as `weakened`, also when the change makes the tag stricter.

| Option | Default | Meaning |
| --- | --- | --- |
| `classes` | `["*"]` | The classes whose tags are frozen. This includes the tags on their methods. |
| `ignore` | `[]` | Classes that are exempt. |

The scope must be `diff`.

Placeholders: `{qualified_name}`, `{rule}`, `{member}`, `{action}` (`removed` or `weakened`)

```yaml
  - id: freeze-architectural-tags
    type: frozen-rules
    severity: error
    message: |
      The tag '{rule}' on '{member}' of '{qualified_name}' was {action}. These tags
      record deliberate design constraints. Put the tag back, or get the change
      approved as a design change.
```

---

## Dependencies and layers

These rules look at the current code. They need no baseline.

### `forbidden-references`

Fails when a class that matches `from` refers to a class that matches `to`. Use it when the
forbidden edge is between specific types.

| Option | Default | Meaning |
| --- | --- | --- |
| `from` | — | Globs of the source classes. Mandatory. |
| `to` | — | Globs of the forbidden target classes. Mandatory. |
| `ignore` | `[]` | Applies to the two ends of the edge. |

With `scope: diff`, the rule examines only the classes that were added or changed.

Placeholders: `{qualified_name}`, `{source}`, `{target}`

```yaml
  - id: domain-does-not-use-the-http-client
    type: forbidden-references
    severity: error
    from: ["shop.domain.**"]
    to:   ["shop.infrastructure.HttpClient"]
    message: |
      '{source}' references '{target}'. The domain does not call the network.
      Define a port in the domain and implement it in the infrastructure.
```

### `forbidden-package-references`

Fails when a class in a package that matches `from` refers to a class in a package that
matches `to`. One class edge is sufficient. A package can always refer to itself.

| Option | Default | Meaning |
| --- | --- | --- |
| `from` | — | Globs of the source packages. Mandatory. |
| `to` | — | Globs of the forbidden target packages. Mandatory. |
| `ignore` | `[]` | Applies to the two ends. The values are package names. |

Placeholders: `{qualified_name}` (the source package), `{source}`, `{target}`

```yaml
  - id: catalog-is-a-leaf-package
    type: forbidden-package-references
    severity: error
    from: ["catalog"]
    to:   ["orders", "users", "notifications"]
    message: |
      Layering violation: '{source}' must not depend on '{target}'. `catalog` stays
      at the bottom of the dependency graph. Move the reference to the package that
      owns the workflow.
```

The report gives the package name and no file. The edge can come from any class of the
package.

The glob `shop.domain.**` matches the package `shop.domain` and each of its sub-packages.

### `no-cyclic-package-dependencies`

Fails when the package graph has a cycle. Each cycle is reported one time, with the full
chain. This rule is a good default for each project with more than a few packages.

| Option | Default | Meaning |
| --- | --- | --- |
| `ignore` | `[]` | Matched against the first package of the cycle, in alphabetical order. |

Placeholders: `{cycle}`, for example `orders -> users -> orders`

```yaml
  - id: no-cyclic-package-dependencies
    type: no-cyclic-package-dependencies
    severity: error
    message: |
      Cyclic package dependency: {cycle}. Move the shared types to a leaf package,
      or invert one direction: define the interface in the lower package and
      implement it in the higher package.
```

### `layer-dependencies`

Fails when a class in layer A refers to a class in layer B, and B is not in the list of A.
The layers come from the `layer` tag in the code. Use this rule when the layers are not
the folders.

| Option | Default | Meaning |
| --- | --- | --- |
| `allow` | `{}` | A mapping from each layer to the layers that it can depend on. |
| `ignore` | `[]` | Applies to the two ends. The values are class names. |

- A reference in the same layer is always permitted.
- A layer that is not a key of `allow` has no constraint. To say "this layer depends on
  nothing", write the key with an empty list.
- A reference to a class with no `layer` tag is ignored.

Placeholders: `{qualified_name}`, `{source}`, `{target}`, `{source_layer}`, `{target_layer}`

```yaml
  - id: layering
    type: layer-dependencies
    severity: error
    allow:
      presentation:   [application, domain]
      application:    [domain]
      domain:         []
      infrastructure: [domain]
    message: |
      Layering violation: '{source}' ({source_layer}) references '{target}'
      ({target_layer}). Define the interface in the lower layer and implement it in
      the higher layer.
```

---

## Shape and complexity

These rules use `scope: snapshot` by default. With `scope: diff`, they examine only the
classes that were added or changed. Use that to adopt a rule on old code.

### `dangling-classes`

Fails when no other class of the project refers to a class. It finds dead code. It cannot
see a class that a framework creates, so it has two options for those.

| Option | Default | Meaning |
| --- | --- | --- |
| `entry_points` | `[]` | Globs of exempt classes, matched against the qualified name and the short name. |
| `framework_bases` | A list of Unity base classes, for example `MonoBehaviour` | Base classes whose subclasses are exempt. Your value replaces the default list. |
| `ignore` | `[]` | Classes that are exempt. |

Placeholders: `{qualified_name}`

```yaml
  - id: no-dangling-classes
    type: dangling-classes
    severity: warning
    entry_points:
      - "orders.CheckoutService"      # the DI container creates it
      - "*Controller"
    framework_bases: ["BaseCommand"]
    message: |
      Class '{qualified_name}' has no incoming reference. If bootstrap code creates
      it, add it to `entry_points`. If not, it is dead code. Delete it.
```

### `subclass-naming`

Fails when a class inherits from a base that matches `base`, and the class name does not
match `name_pattern`.

| Option | Default | Meaning |
| --- | --- | --- |
| `base` | — | A glob or a list of globs, matched against each declared base. Mandatory. |
| `name_pattern` | — | A regular expression for the full class name. Mandatory. |
| `ignore` | `[]` | Classes that are exempt. |

The rule examines only the bases that a class declares directly.

Placeholders: `{qualified_name}`, `{name}`, `{base}`, `{pattern}`

```yaml
  - id: notifiers-end-in-notifier
    type: subclass-naming
    severity: error
    base: "Notification"
    name_pattern: ".*Notifier$"
    message: |
      Class '{qualified_name}' inherits from `{base}`, but its name ({name}) does
      not match /{pattern}/. Rename the class, for example `SlackNotifier`.
```

### `max-class-fanout`

Fails when a class refers to more than `limit` different classes of the project. A high
number shows a hub.

| Option | Default | Meaning |
| --- | --- | --- |
| `limit` | `10` | The maximum number of different classes. |
| `ignore` | `[]` | Classes that are exempt, for example a composition root. |

Placeholders: `{qualified_name}`, `{fanout}`, `{limit}`

```yaml
  - id: bounded-class-fanout
    type: max-class-fanout
    severity: warning
    limit: 6
    ignore: ["app.CompositionRoot"]
    message: |
      Class '{qualified_name}' references {fanout} classes (limit: {limit}). Split
      its responsibilities, or make it depend on interfaces.
```

---

## Rules that read the source

These three rules read the code again, not only the model.

### `tag-conformance`

Fails when the code does not obey its constraint tags. It checks `sealed`, `immutable`,
`factory` and `no-instantiation`. The tags are in `./tags.md`. It supports Python, C#,
Odin, Lua and Julia. On TypeScript and Svelte, the rule is skipped.

| Option | Default | Meaning |
| --- | --- | --- |
| `rules` | all tags | A list of tag ids to check, for example `[sealed, immutable]`. |
| `ignore` | `[]` | Elements that are exempt. |

Placeholders: `{qualified_name}`, `{rule}`, `{detail}`, `{message}`

```yaml
  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error
    message: |
      [{rule}] {message}
      A constraint tag is a promise that the code must keep. Use the designated
      collaborator. Do not delete the tag.
```

### `implementation-locks`

Fails when the body of a frozen class, method or function changes. The lock is on the
syntax tree, not on the lines. Moved code, a new format and edited comments do not fail. A
renamed local variable, a changed literal and a new statement fail.

| Option | Default | Meaning |
| --- | --- | --- |
| `targets` | `[]` | Qualified-name globs to freeze code that has no `locked` tag. |
| `include_docstrings` | `false` | `true`: a docstring edit is a change. |

Placeholders: `{qualified_name}`, `{kind}`, `{message}`

```yaml
  - id: frozen-implementations
    type: implementation-locks
    severity: error
    targets:
      - "tests.acceptance.**"       # freeze this package without tags
```

After you add a `locked` tag or a target, record the digests with
`cdec check --automatic-exceptions locks`. The digests go into the `locks:` section. This
command only adds digests. A changed digest needs `--force`, and only a lead approves that.
With `--target <glob>`, `--force` accepts only the elements that match. Without it,
`--force` accepts each lock that changed.

The rule reports five kinds of issue: `changed`, `missing` (a tag with no digest),
`removed`, `unlocked` (the tag was deleted) and `algo-mismatch`. An exception cannot
accept a lock issue.

### `reference-architecture`

Fails on each structural difference between the code and `.cdec/reference.xmi`. It has no
list of laws. Any difference fails.

| Option | Default | Meaning |
| --- | --- | --- |
| `reference` | The `reference:` setting | The path of the reference model. |
| `categories` | all | A list of the categories to enforce. |
| `ignore` | `[]` | Classes that are exempt. |

The categories are `class-added`, `class-removed`, `class-kind-changed`,
`class-bases-changed`, `attribute-added`, `attribute-removed`, `attribute-changed`,
`operation-added`, `operation-removed`, `operation-signature-changed`,
`operation-return-type-changed` and `operation-modifier-changed`.

Placeholders: `{qualified_name}`, `{category}`, `{member}`, `{message}`

```yaml
  - id: public-shape-is-frozen
    type: reference-architecture
    severity: error
    categories: [class-removed, operation-removed, operation-signature-changed]
```

Two commands write the reference:

| Command | Meaning |
| --- | --- |
| `cdec reference set <model>` | Declare what the code must become. Use it for an approved design. |
| `cdec check --automatic-exceptions reference` | Record what the code is now. Use it for an approved change that is already in the code. |

---

## Two layouts for the rules

Keep each rule in the `rules:` list of `.cdec/rules.yaml`. That is the default.

Or divide the rules into `.cdec/rules/*.yaml`, with one `rules:` list in each file and
nothing else. Then `cdec check` runs each file, and `cdec check --rules-file fast` runs
one file. Use one layout only. If the two layouts have rules, the run fails. The settings,
`exceptions:` and `locks:` always stay in `.cdec/rules.yaml`. A rule `id` is unique across
all files.
