"""Rule: enforce allowed dependency directions between architectural layers.

Classes declare their layer with the `@layer("name")` tag. This rule takes an
allowed-direction matrix and flags any reference from a class in layer A to a
class in layer B when B is not in A's allow-list. Same-layer references are
always permitted.

Pure architectural check (Engine A): it reads tags + the structural reference
graph (`ctx.outgoing_refs`); it never inspects method bodies.
"""

from __future__ import annotations

from typing import Iterable

from code_constraints.core.model import DiffStatus
from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation

_LAYER_RULE_ID = "layer"


def _layer_of(cls) -> str | None:
    """The layer name declared by `@layer("name")`, or None.

    The first positional arg is the layer name as raw source text, so it may be
    wrapped in quotes (`'domain'` from Python, `"domain"` from C#) — strip them.
    """
    for rule in cls.rules:
        if rule.name == _LAYER_RULE_ID and rule.args:
            return rule.args[0].strip().strip("'\"")
    return None


@register("layer-dependencies")
class LayerDependencies(Rule):
    """Options:
      allow:  mapping of layer -> list of layers it MAY depend on. A class whose
              layer is not a key in `allow` is left unconstrained. An empty list
              means the layer may not depend on any *other* layer.
    """

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        allow_raw = self.options.get("allow") or {}
        allow: dict[str, set[str]] = {
            str(k): {str(v) for v in (vals or [])} for k, vals in allow_raw.items()
        }
        if not allow:
            return

        layer_by_qn: dict[str, str] = {}
        for cls in ctx.project.iter_classes():
            if cls.status == DiffStatus.REMOVED:
                continue
            lyr = _layer_of(cls)
            if lyr is not None:
                layer_by_qn[cls.qualified_name] = lyr

        for cls in ctx.project.iter_classes():
            if cls.status == DiffStatus.REMOVED:
                continue
            src_qn = cls.qualified_name
            if self.is_ignored(src_qn):
                continue
            src_layer = layer_by_qn.get(src_qn)
            if src_layer is None or src_layer not in allow:
                continue
            allowed = allow[src_layer]
            for tgt_qn in ctx.outgoing_refs.get(src_qn, set()):
                if self.is_ignored(tgt_qn):
                    continue
                tgt_layer = layer_by_qn.get(tgt_qn)
                if tgt_layer is None or tgt_layer == src_layer:
                    continue
                if tgt_layer in allowed:
                    continue
                yield self.emit(
                    qualified_name=src_qn,
                    signature=f"{src_layer}->{tgt_layer}:{tgt_qn}",
                    message=self.message_for(
                        qualified_name=src_qn,
                        source=src_qn,
                        target=tgt_qn,
                        source_layer=src_layer,
                        target_layer=tgt_layer,
                    )
                    or (
                        f"layer '{src_layer}' may not depend on layer "
                        f"'{tgt_layer}' ('{src_qn}' -> '{tgt_qn}')."
                    ),
                    location=cls.location,
                )
