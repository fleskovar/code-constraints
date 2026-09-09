"""Rule: forbid cycles in the package-dependency graph."""

from __future__ import annotations

from typing import Iterable

from code_constraints.lint.rules import register
from code_constraints.lint.rules.base import Rule, RuleContext, Violation


@register("no-cyclic-package-dependencies")
class NoCyclicPackageDependencies(Rule):
    """No options. Walks the derived package-edge graph and reports every
    elementary cycle as a single violation against the alphabetically-first
    package in the cycle."""

    def check(self, ctx: RuleContext) -> Iterable[Violation]:
        graph = {src: set(t for t in tgts if t != src) for src, tgts in ctx.outgoing_pkg_refs.items()}
        reported: set[tuple[str, ...]] = set()
        for cycle in _find_cycles(graph):
            cycle = tuple(cycle)
            # Canonicalise: rotate so the lex-smallest node is first, so
            # `[A,B,C]` and `[B,C,A]` collapse to one report.
            min_idx = min(range(len(cycle)), key=lambda i: cycle[i])
            normalised = cycle[min_idx:] + cycle[:min_idx]
            if normalised in reported:
                continue
            reported.add(normalised)
            head = normalised[0]
            if self.is_ignored(head):
                continue
            chain = " -> ".join(list(normalised) + [normalised[0]])
            yield self.emit(
                qualified_name=head,
                signature=chain,
                message=self.message_for(cycle=chain)
                or f"Cyclic package dependency: {chain}.",
            )


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan-style enumeration of simple cycles. Keeps things small — only
    used over a package graph whose node count is order-of-magnitudes smaller
    than the class graph."""
    cycles: list[list[str]] = []
    nodes = list(graph.keys())
    blocked: set[str] = set()
    stack: list[str] = []

    def dfs(node: str, start: str) -> bool:
        found = False
        stack.append(node)
        blocked.add(node)
        for nb in graph.get(node, set()):
            if nb == start and len(stack) >= 1:
                cycles.append(list(stack))
                found = True
            elif nb not in blocked:
                if dfs(nb, start):
                    found = True
        stack.pop()
        if found:
            blocked.discard(node)
        return found

    for start in nodes:
        blocked.clear()
        dfs(start, start)
    return cycles
