# The JSON model format

A model file is one JSON object. `cdec parse`, `cdec convert`, `cdec propose` and
`cdec reference set` all read and write this format. A field that you omit gets its
default value.

## Project (the top level)

| Field | Type | Meaning |
| --- | --- | --- |
| `source_language` | string | `python`, `csharp`, `typescript`, `svelte`, `odin`, `lua` or `julia`. |
| `packages` | list of package | The top-level packages. |
| `associations` | list of association | Explicit associations. Most models leave this list empty. |
| `activities`, `sequences` | list | Activity and sequence diagrams. Keep what `cdec parse` wrote. |
| `root_path` | string | The source folder of the parse. Keep what `cdec parse` wrote. |

## Package

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | The last segment, for example `billing`. |
| `qualified_name` | string | The full name with dots, for example `orders.billing`. |
| `classes` | list of class | The classes of the package. |
| `sub_packages` | list of package | The nested packages. |
| `description` | string | Optional text. |

A package name is a module name in Python, a namespace segment in C#, and a folder in
TypeScript and Svelte. Use no spaces and no hyphens.

## Class

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | The short name, for example `Invoice`. |
| `qualified_name` | string | The package name, a dot, and the short name: `billing.Invoice`. |
| `kind` | string | `class`, `interface`, `abstract`, `enum`, `struct`, `record` or `static`. The default is `class`. |
| `bases` | list of string | The base classes. Each one draws an inheritance edge. Write each name as the source writes it. |
| `attributes` | list of attribute | The fields and properties. |
| `operations` | list of operation | The methods. |
| `rules` | list of rule tag | The constraint tags on the class. |
| `dependencies` | list of string | Classes that the method bodies use. `cdec parse` fills this list. |
| `description` | string | Why the class exists. Write it for each new class. |

The class is matched with the code by `qualified_name`. A different qualified name is a
removed class and an added class.

The parser keeps a base name as source text. `class EmailNotifier(Notification)` gives
`"bases": ["Notification"]`, not `notifications.Notification`. Use the same form for a new
class, or the reference gate reports that the bases changed.

## Attribute

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | The name. |
| `type` | string | The type as source text, for example `float` or `list[Invoice]`. |
| `visibility` | string | `public`, `protected`, `private` or `package`. The default is `public`. |
| `is_static`, `is_readonly` | boolean | The default is `false`. |
| `default` | string | The default value as source text. |
| `description` | string | Optional text. |

A `type` that names a class of the model draws an association edge. The viewer removes
collection wrappers first, so `list[Invoice]`, `List<Invoice>` and `Invoice[]` all point
to `Invoice`.

## Operation

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | The method name. |
| `parameters` | list of `{ "name", "type", "default" }` | Do not list `self` or `this`. |
| `return_type` | string | The return type as source text. |
| `visibility` | string | `public`, `protected`, `private` or `package`. The default is `public`. |
| `is_static`, `is_abstract` | boolean | The default is `false`. |
| `rules` | list of rule tag | The constraint tags on the method. |
| `description` | string | Optional text. |

Members are matched with the code by signature. The signature of an attribute is
`name:type`. The signature of an operation is `name(p:T,q:U):return_type`. Write the types
exactly as the parser writes them, or the diff shows a removed member and an added member.

## Rule tag

```json
{ "name": "sealed" }
{ "name": "layer", "args": ["'domain'"] }
{ "name": "factory", "kwargs": { "creates": "['Receipt']" } }
{ "name": "no-instantiation", "kwargs": { "allow": "['AuditEntry']" } }
{ "name": "locked", "kwargs": { "reason": "'the wording is contractual'" } }
```

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | The catalogue id: `layer`, `sealed`, `immutable`, `factory`, `no-instantiation`, `no-side-effects` or `locked`. |
| `args` | list of string | The positional arguments, as source text. |
| `kwargs` | object of string | The keyword arguments, as source text. |

The id uses hyphens (`no-instantiation`), not the Python spelling (`no_instantiation`).

**The arguments are source text, and the comparison is exact.** The `frozen-rules` rule
compares the tag in the reference with the tag in the code, character by character. A
string argument keeps its quotes. To get the exact form, tag one class in the code, run
`cdec parse`, and copy what the parser wrote. For Python, the parser writes single quotes:
`'domain'` and `['Receipt']`.

The meaning of each tag, and the element that each tag can go on, is in the
`cdec-guardrails` skill.

## Association

Most associations come from attribute types, and you do not write them. Use an explicit
entry only for a relation that no attribute shows.

| Field | Type | Meaning |
| --- | --- | --- |
| `source`, `target` | string | The qualified names of the two classes. |
| `name` | string | Optional label. |
| `source_multiplicity`, `target_multiplicity` | string | Optional, for example `1` or `0..*`. |
| `source_role`, `target_role` | string | Optional role names. |

## Fields that you do not write

`cdec parse` also writes `status`, `location` and `layout`. Do not edit them, and do not
add them to a new element. `status` is the output of a diff. `location` is the place of
the element in the source. `layout` is for the canvas.

## Naming rules

- Class names use PascalCase.
- Members use the convention of the language: snake_case in Python, camelCase or
  PascalCase in C#, camelCase in TypeScript.
- Qualified names use a dot as the separator.
- In Svelte, one `.svelte` file is one component class. Its name is the file name.
- In Odin and Julia, a procedure belongs to the type of its first parameter. In Lua, a
  method belongs to its table.
- In Odin, Lua and Julia, a function with no receiver goes in a `static` class with the
  name of the file.
