"""How a constraint tag is written in each language — the text a person pastes.

`core/rules.py` says which tags exist. This module spells one tag, with its
arguments, for one language. The tag wizard of the web app shows the result, so
a user does not look up five syntaxes. `tests/test_journey.py` checks the output
against the forms that the docs give.
"""

from __future__ import annotations

from code_constraints.core.rules import CSHARP_SHIM_NAMESPACE, RULE_CATALOG

#: Languages that have tags. TypeScript and Svelte have none.
TAG_LANGUAGES = ("python", "csharp", "julia", "lua", "odin")

# Arguments that hold a list of type names. Every other argument is one string.
_LIST_PARAMS = ("allow", "creates")


def tag_snippet(tag_id: str, lang: str, values: dict[str, str] | None = None) -> dict[str, str]:
    """`{"tag": ..., "import": ...}` for one tag in one language.

    `values` maps an argument name to its text. A list argument takes names
    separated by commas. An empty value leaves the argument out.
    """
    spec = RULE_CATALOG.get(tag_id)
    if spec is None:
        raise ValueError(f"unknown tag {tag_id!r}; known: {', '.join(RULE_CATALOG)}")
    if lang not in TAG_LANGUAGES:
        raise ValueError(f"{lang} has no constraint tags")
    given = {k: v.strip() for k, v in (values or {}).items() if k in spec.params and v.strip()}

    args: list[str] = []
    for name in spec.params:
        if name not in given:
            continue
        if name in _LIST_PARAMS:
            items = ", ".join(f'"{n.strip()}"' for n in given[name].split(",") if n.strip())
            value = {
                "csharp": f"new[] {{ {items} }}",
                "lua": f"{{{items}}}",
            }.get(lang, f"[{items}]")
        else:
            value = '"' + given[name].replace('"', '\\"') + '"'
        if name == "name":  # `layer` takes its one argument by position
            args.append(value)
        elif lang == "csharp":
            args.append(f"{name.capitalize()} = {value}")
        elif lang in ("lua", "odin"):
            args.append(f"{name} = {value}")
        else:
            args.append(f"{name}={value}")

    if lang == "python":
        tag = f"@{spec.python_name}" + (f"({', '.join(args)})" if args else "")
        how = f"from cdec_rules import {spec.python_name}"
    elif lang == "csharp":
        tag = f"[{spec.csharp_name}" + (f"({', '.join(args)})" if args else "") + "]"
        how = f"using {CSHARP_SHIM_NAMESPACE};"
    elif lang == "julia":
        # Julia separates macro arguments with spaces. Parentheses are an error.
        tag = f"@{spec.julia_name}" + "".join(f" {a}" for a in args)
        how = "using CdecRules"
    else:
        marker = "---@cdec" if lang == "lua" else "//@cdec"
        tag = f"{marker} {spec.annotation_name}" + (f"({', '.join(args)})" if args else "")
        how = ""
    return {"tag": tag, "import": how}


#: The rule type that makes each kind of tag binding.
ENFORCED_BY = {
    "implementation": "tag-conformance",
    "lock": "implementation-locks",
    "architectural": "layer-dependencies",
    "drift": "frozen-rules",
}
