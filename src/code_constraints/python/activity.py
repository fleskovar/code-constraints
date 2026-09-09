"""Translate the AST inside a tagged region into a UML `Activity`.

Three granularities are supported (chosen via the tag's `granularity` attribute):
- `control-flow` (default): `if/while/for/try` become decision/merge nodes;
  other statements collapse into action nodes.
- `statement`: every statement becomes an action node, linked sequentially.
- `calls`: only `Call` expressions inside the tagged region become action nodes.
"""

from __future__ import annotations

import ast
from typing import Iterable

from code_constraints.core.model import (
    Activity,
    ActivityEdge,
    ActivityNode,
    SourceLocation,
)
from code_constraints.core.tags import TagInstance


def build_activity_from_tag(
    tag: TagInstance, tree: ast.Module, source: str, *, file: str
) -> Activity | None:
    if not tag.name:
        return None
    granularity = tag.attributes.get("granularity", "control-flow")
    if granularity not in {"control-flow", "statement", "calls"}:
        granularity = "control-flow"

    body = _statements_in_range(tree, tag.start_line, tag.end_line)
    if not body:
        return None

    builder = _ActivityBuilder()
    builder.start()
    if granularity == "statement":
        builder.linear(body, label_fn=_statement_label)
    elif granularity == "calls":
        calls = [c for stmt in body for c in _walk_calls(stmt)]
        builder.linear(calls, label_fn=_call_label)
    else:
        builder.control_flow(body)
    builder.finish()

    return Activity(
        name=tag.name,
        nodes=builder.nodes,
        edges=builder.edges,
        granularity=granularity,  # type: ignore[arg-type]
        location=SourceLocation(file=file, start_line=tag.start_line, end_line=tag.end_line),
    )


def _statements_in_range(tree: ast.Module, start: int, end: int) -> list[ast.stmt]:
    """Return top-level-ish statements whose source range overlaps [start, end]
    and whose first line is strictly inside the tag span (so the tag comment
    lines themselves don't get included)."""
    out: list[ast.stmt] = []
    # Prefer the innermost function whose body contains the tag region.
    candidates: list[tuple[int, list[ast.stmt]]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            f_start = getattr(node, "lineno", 0)
            # Use the first body statement to know where the body starts,
            # and the last body statement's end_lineno for where it ends.
            if not node.body:
                continue
            body_start = getattr(node.body[0], "lineno", f_start)
            body_end = max(
                (getattr(s, "end_lineno", getattr(s, "lineno", 0)) or 0)
                for s in node.body
            )
            # Function envelopes the tag if its def line is before the tag
            # start and any of its body extends to or past the tag start.
            if f_start < start and body_end >= start:
                stmts = [
                    s for s in node.body if start < getattr(s, "lineno", 0) < end
                ]
                if stmts:
                    candidates.append((f_start, stmts))
    if candidates:
        # Innermost = the one whose body_start is latest among containers.
        candidates.sort(key=lambda c: c[0])
        return candidates[-1][1]
    # Otherwise look at module-level statements in range.
    for stmt in tree.body:
        s_start = getattr(stmt, "lineno", 0)
        if start < s_start < end:
            out.append(stmt)
    return out


class _ActivityBuilder:
    def __init__(self) -> None:
        self.nodes: list[ActivityNode] = []
        self.edges: list[ActivityEdge] = []
        self._counter = 0
        self._last_id: str | None = None

    def _new_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    def _add(self, node: ActivityNode) -> str:
        self.nodes.append(node)
        if self._last_id is not None:
            self.edges.append(ActivityEdge(source=self._last_id, target=node.id))
        self._last_id = node.id
        return node.id

    def start(self) -> None:
        self._add(ActivityNode(id=self._new_id("init"), kind="initial"))

    def finish(self) -> None:
        self._add(ActivityNode(id=self._new_id("final"), kind="final"))

    def linear(self, items: Iterable, *, label_fn) -> None:
        for item in items:
            self._add(
                ActivityNode(
                    id=self._new_id("a"),
                    kind="action",
                    label=label_fn(item),
                )
            )

    def control_flow(self, stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            self._handle_stmt(stmt)

    def _handle_stmt(self, stmt: ast.stmt) -> None:
        if isinstance(stmt, ast.If):
            self._handle_if(stmt)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            self._handle_loop(stmt)
        elif isinstance(stmt, ast.Try):
            self._handle_try(stmt)
        elif isinstance(stmt, ast.Return):
            self._add(
                ActivityNode(
                    id=self._new_id("a"),
                    kind="action",
                    label=f"return {_unparse(stmt.value)}".strip(),
                )
            )
        elif isinstance(stmt, ast.Raise):
            self._add(
                ActivityNode(
                    id=self._new_id("a"),
                    kind="action",
                    label=f"raise {_unparse(stmt.exc)}".strip(),
                )
            )
        else:
            self._add(
                ActivityNode(
                    id=self._new_id("a"),
                    kind="action",
                    label=_statement_label(stmt),
                )
            )

    def _handle_if(self, stmt: ast.If) -> None:
        decision_id = self._new_id("d")
        decision = ActivityNode(
            id=decision_id, kind="decision", label=_unparse(stmt.test)
        )
        if self._last_id is not None:
            self.edges.append(ActivityEdge(source=self._last_id, target=decision_id))
        self.nodes.append(decision)
        merge_id = self._new_id("m")
        merge = ActivityNode(id=merge_id, kind="merge")

        # then branch
        self._last_id = decision_id
        # tag the next edge with guard "yes"
        prev_edges_count = len(self.edges)
        for s in stmt.body:
            self._handle_stmt(s)
        # mark first edge of branch as "yes"
        if len(self.edges) > prev_edges_count:
            self.edges[prev_edges_count].guard = "yes"
        if self._last_id is not None:
            self.edges.append(ActivityEdge(source=self._last_id, target=merge_id))

        # else branch
        self._last_id = decision_id
        prev_edges_count = len(self.edges)
        for s in stmt.orelse:
            self._handle_stmt(s)
        if not stmt.orelse:
            # empty else: direct edge from decision to merge
            self.edges.append(
                ActivityEdge(source=decision_id, target=merge_id, guard="no")
            )
        else:
            if len(self.edges) > prev_edges_count:
                self.edges[prev_edges_count].guard = "no"
            if self._last_id is not None:
                self.edges.append(ActivityEdge(source=self._last_id, target=merge_id))

        self.nodes.append(merge)
        self._last_id = merge_id

    def _handle_loop(self, stmt: ast.AST) -> None:
        if isinstance(stmt, (ast.For, ast.AsyncFor)):
            label = f"for {_unparse(stmt.target)} in {_unparse(stmt.iter)}"
        else:
            assert isinstance(stmt, ast.While)
            label = f"while {_unparse(stmt.test)}"

        decision_id = self._new_id("d")
        decision = ActivityNode(id=decision_id, kind="decision", label=label)
        if self._last_id is not None:
            self.edges.append(ActivityEdge(source=self._last_id, target=decision_id))
        self.nodes.append(decision)

        merge_id = self._new_id("m")
        merge = ActivityNode(id=merge_id, kind="merge")

        # loop body
        self._last_id = decision_id
        prev_edges_count = len(self.edges)
        body = stmt.body if hasattr(stmt, "body") else []  # type: ignore[attr-defined]
        for s in body:
            self._handle_stmt(s)
        if len(self.edges) > prev_edges_count:
            self.edges[prev_edges_count].guard = "loop"
        if self._last_id is not None:
            self.edges.append(ActivityEdge(source=self._last_id, target=decision_id))

        # exit edge
        self.edges.append(
            ActivityEdge(source=decision_id, target=merge_id, guard="exit")
        )
        self.nodes.append(merge)
        self._last_id = merge_id

    def _handle_try(self, stmt: ast.Try) -> None:
        # Simplified: a try is a single action followed by branches per handler.
        try_id = self._new_id("a")
        self._add(ActivityNode(id=try_id, kind="action", label="try"))
        for handler in stmt.handlers:
            exc = _unparse(handler.type) if handler.type else "*"
            self._add(
                ActivityNode(
                    id=self._new_id("a"),
                    kind="action",
                    label=f"except {exc}",
                )
            )


def _statement_label(stmt: ast.stmt) -> str:
    text = _unparse(stmt).strip()
    # First non-empty line, truncated
    first = next((line for line in text.splitlines() if line.strip()), text)
    return first[:60] + ("…" if len(first) > 60 else "")


def _walk_calls(stmt: ast.stmt) -> list[ast.Call]:
    return [n for n in ast.walk(stmt) if isinstance(n, ast.Call)]


def _call_label(call: ast.Call) -> str:
    return _unparse(call)[:60]


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""
