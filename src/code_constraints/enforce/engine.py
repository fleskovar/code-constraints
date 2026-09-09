"""Dispatcher for `cdec enforce` — the implementation-conformance engine.

This re-parses the current source independently and inspects method bodies. It
never consults the reference model or the diff metadata (that's Engine A / `cdec check`).
Findings are filtered against the waiver ledger by the *caller* (the CLI), so the engine
itself stays a pure function of the source.

Per-language body analysis (`no-instantiation`, `factory`, `immutable`) lives in
the language packages' `conformance` modules. The `sealed` check is structural
and cross-file, so it's evaluated here against the parsed `Project` model.
"""

from __future__ import annotations

from pathlib import Path

from code_constraints.core.model import Project
from code_constraints.enforce.model import Finding

SEALED_RULE = "sealed"


def enforce(root: str | Path, lang: str) -> list[Finding]:
    root_path = Path(root).resolve()
    project = _parse(root_path, lang)
    findings: list[Finding] = []
    findings.extend(_check_sealed(project))
    findings.extend(_analyze_bodies(root_path, lang, project))
    return findings


def _check_sealed(project: Project) -> list[Finding]:
    """A `@sealed` class may not be subclassed.

    Tree-sitter / ast give us textual base names (not resolved qnames), so match
    a sealed class by short name against every other class's base list.
    """
    sealed_names: dict[str, object] = {
        cls.name: cls
        for cls in project.iter_classes()
        if any(r.name == SEALED_RULE for r in cls.rules)
    }
    if not sealed_names:
        return []
    findings: list[Finding] = []
    for cls in project.iter_classes():
        for base in cls.bases:
            short = base.rsplit(".", 1)[-1]
            if short in sealed_names and short != cls.name:
                loc = cls.location
                findings.append(
                    Finding(
                        rule=SEALED_RULE,
                        qualified_name=cls.qualified_name,
                        message=(
                            f"'{cls.qualified_name}' subclasses sealed class "
                            f"'{short}'; sealed types may not be subclassed."
                        ),
                        detail=f"base:{short}",
                        file=loc.file if loc else "",
                        line=loc.start_line if loc else 0,
                    )
                )
    return findings


def _analyze_bodies(root: Path, lang: str, project: Project) -> list[Finding]:
    if lang == "python":
        from code_constraints.python.conformance import analyze

        return analyze(root, project)
    if lang == "csharp":
        from code_constraints.csharp.conformance import analyze

        return analyze(root, project)
    if lang == "odin":
        from code_constraints.odin.conformance import analyze

        return analyze(root, project)
    if lang == "lua":
        from code_constraints.lua.conformance import analyze

        return analyze(root, project)
    if lang == "julia":
        from code_constraints.julia.conformance import analyze

        return analyze(root, project)
    # Other languages have no body analyzer yet.
    return []


def _parse(root: Path, lang: str) -> Project:
    if lang == "python":
        from code_constraints.python import parse_project

        return parse_project(root)
    if lang == "csharp":
        from code_constraints.csharp import parse_project

        return parse_project(root)
    if lang == "typescript":
        from code_constraints.typescript import parse_project

        return parse_project(root)
    if lang == "svelte":
        from code_constraints.svelte import parse_project

        return parse_project(root)
    if lang == "odin":
        from code_constraints.odin import parse_project

        return parse_project(root)
    if lang == "lua":
        from code_constraints.lua import parse_project

        return parse_project(root)
    if lang == "julia":
        from code_constraints.julia import parse_project

        return parse_project(root)
    raise ValueError(f"unsupported language: {lang}")
