"""Rule: the implementation must honour the constraint tags written on it.

This is the adapter for the conformance engine (`code_constraints.enforce`,
"Engine B"). Every other rule in this package reads only the model; this one
re-parses the source and inspects method bodies, which is why it needs
`ctx.source` and `ctx.language`.

The engine stays an independent package with its own result type — the rule
imports it lazily and translates `Finding`s into `Violation`s. What the
`rules.yaml` entry buys is uniformity: tag conformance is now configured,
reported, ignored and excepted exactly like every other law in the file, instead
of through a second command with a second report and a second exit code.

Violations key under the `enforce` engine (`F-…`), not under the rules entry, so
renaming the entry never invalidates a granted exception.
"""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import SourceLocation
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, RuleSkipped, Violation

#: Languages whose parsers recognise constraint tags. The other supported
#: languages parse and diff fine but have no tag syntax, so a `tag-conformance`
#: rule there would report "clean" while checking nothing.
TAGGED_LANGUAGES = ("python", "csharp", "odin", "lua", "julia")


@register("tag-conformance")
class TagConformance(Rule):
    """Options:
      rules:  optional list[str] of catalog ids to check (default: all of them),
              e.g. ["no-instantiation", "factory"] to adopt one tag at a time.
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        if ctx.source is None or not ctx.language:
            raise RuleSkipped("no source tree resolved")
        if ctx.language not in TAGGED_LANGUAGES:
            raise RuleSkipped(
                f"{ctx.language} has no constraint-tag syntax; supported: "
                f"{', '.join(TAGGED_LANGUAGES)}"
            )
        from code_constraints.enforce import enforce as run_enforce

        only = {str(r) for r in (self.options.get("rules") or [])}
        findings = run_enforce(ctx.source, ctx.language)
        for finding in findings:
            if only and finding.rule not in only:
                continue
            if self.is_ignored(finding.qualified_name):
                continue
            location = (
                SourceLocation(file=finding.file, start_line=finding.line, end_line=finding.line)
                if finding.file
                else None
            )
            yield Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                qualified_name=finding.qualified_name,
                message=self.message_for(
                    qualified_name=finding.qualified_name,
                    rule=finding.rule,
                    detail=finding.detail,
                    message=finding.message,
                )
                or finding.message,
                location=location,
                signature=finding.detail,
                key_engine="enforce",
                key_rule=finding.rule,
            )
