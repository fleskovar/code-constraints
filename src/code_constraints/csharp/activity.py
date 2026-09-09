"""Build a UML `Activity` from a tagged C# region.

Mirrors `code_constraints.python.activity` but operates on tree-sitter nodes. Only the
control-flow granularity is fully featured; statement/calls fall back to
flat action sequences.
"""

from __future__ import annotations

from tree_sitter import Node, Tree

from code_constraints.core.model import Activity, ActivityEdge, ActivityNode, SourceLocation
from code_constraints.core.tags import TagInstance


def build_activity_from_tag(
    tag: TagInstance, tree: Tree, source: bytes, *, file: str
) -> Activity | None:
    if not tag.name:
        return None
    granularity = tag.attributes.get("granularity", "control-flow")
    if granularity not in {"control-flow", "statement", "calls"}:
        granularity = "control-flow"

    stmts = _statements_in_range(tree.root_node, tag.start_line, tag.end_line)
    if not stmts:
        return None

    builder = _ActivityBuilder()
    builder.start()
    if granularity == "statement":
        for s in stmts:
            builder.action(_short(_text(s, source)))
    elif granularity == "calls":
        for s in stmts:
            for call in _walk_calls(s):
                builder.action(_short(_text(call, source)))
    else:
        for s in stmts:
            _emit_control_flow(builder, s, source)
    builder.finish()

    return Activity(
        name=tag.name,
        nodes=builder.nodes,
        edges=builder.edges,
        granularity=granularity,  # type: ignore[arg-type]
        location=SourceLocation(
            file=file, start_line=tag.start_line, end_line=tag.end_line
        ),
    )


_BODY_HOLDERS = {
    "method_declaration",
    "constructor_declaration",
    "local_function_statement",
    "destructor_declaration",
}


def _statements_in_range(root: Node, start: int, end: int) -> list[Node]:
    """Find the body that contains the tag region, then return its top-level
    statements whose first line falls strictly inside [start, end]."""
    best: list[Node] | None = None
    best_start = -1

    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        if node.type in _BODY_HOLDERS:
            body = node.child_by_field_name("body")
            if body is not None and body.type == "block":
                first_stmt = next(
                    (c for c in body.named_children if not _is_comment(c)), None
                )
                if first_stmt is None:
                    continue
                body_start_line = first_stmt.start_point[0] + 1
                body_end_line = body.end_point[0] + 1
                node_def_line = node.start_point[0] + 1
                if node_def_line < start and body_end_line >= start:
                    stmts = [
                        c
                        for c in body.named_children
                        if not _is_comment(c)
                        and start < (c.start_point[0] + 1) < end
                    ]
                    if stmts and node_def_line > best_start:
                        best = stmts
                        best_start = node_def_line
        for child in node.children:
            stack.append(child)
    return best or []


def _is_comment(node: Node) -> bool:
    return node.type == "comment"


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

    def action(self, label: str) -> str:
        return self._add(ActivityNode(id=self._new_id("a"), kind="action", label=label))

    def decision(self, label: str) -> str:
        node = ActivityNode(id=self._new_id("d"), kind="decision", label=label)
        if self._last_id is not None:
            self.edges.append(ActivityEdge(source=self._last_id, target=node.id))
        self.nodes.append(node)
        self._last_id = node.id
        return node.id


def _emit_control_flow(builder: _ActivityBuilder, stmt: Node, source: bytes) -> None:
    if stmt.type == "if_statement":
        _emit_if(builder, stmt, source)
    elif stmt.type in ("for_statement", "for_each_statement", "while_statement"):
        _emit_loop(builder, stmt, source)
    elif stmt.type == "return_statement":
        builder.action(_short("return " + _text(stmt, source)))
    elif stmt.type == "throw_statement":
        builder.action(_short("throw " + _text(stmt, source)))
    elif stmt.type == "try_statement":
        builder.action("try")
        # catch clauses are surfaced as follow-on actions
        for c in stmt.named_children:
            if c.type == "catch_clause":
                builder.action("catch")
    else:
        builder.action(_short(_text(stmt, source)))


def _emit_if(builder: _ActivityBuilder, stmt: Node, source: bytes) -> None:
    cond = stmt.child_by_field_name("condition")
    cond_text = _short(_text(cond, source)) if cond is not None else "?"
    decision_id = builder.decision(cond_text)
    merge_id = builder._new_id("m")
    merge = ActivityNode(id=merge_id, kind="merge")

    consequence = stmt.child_by_field_name("consequence")
    alternative = stmt.child_by_field_name("alternative")

    builder._last_id = decision_id
    prev = len(builder.edges)
    if consequence is not None:
        _emit_block_like(builder, consequence, source)
    if len(builder.edges) > prev:
        builder.edges[prev].guard = "yes"
    if builder._last_id is not None:
        builder.edges.append(ActivityEdge(source=builder._last_id, target=merge_id))

    builder._last_id = decision_id
    prev = len(builder.edges)
    if alternative is not None:
        _emit_block_like(builder, alternative, source)
        if len(builder.edges) > prev:
            builder.edges[prev].guard = "no"
        if builder._last_id is not None:
            builder.edges.append(ActivityEdge(source=builder._last_id, target=merge_id))
    else:
        builder.edges.append(
            ActivityEdge(source=decision_id, target=merge_id, guard="no")
        )

    builder.nodes.append(merge)
    builder._last_id = merge_id


def _emit_loop(builder: _ActivityBuilder, stmt: Node, source: bytes) -> None:
    cond = stmt.child_by_field_name("condition")
    label = "loop"
    if cond is not None:
        label = _short(_text(cond, source))
    else:
        label = _short(_text(stmt, source).split("{")[0])
    decision_id = builder.decision(label)
    merge_id = builder._new_id("m")
    merge = ActivityNode(id=merge_id, kind="merge")

    body = stmt.child_by_field_name("body")
    builder._last_id = decision_id
    prev = len(builder.edges)
    if body is not None:
        _emit_block_like(builder, body, source)
    if len(builder.edges) > prev:
        builder.edges[prev].guard = "loop"
    if builder._last_id is not None:
        builder.edges.append(ActivityEdge(source=builder._last_id, target=decision_id))

    builder.edges.append(
        ActivityEdge(source=decision_id, target=merge_id, guard="exit")
    )
    builder.nodes.append(merge)
    builder._last_id = merge_id


def _emit_block_like(builder: _ActivityBuilder, node: Node, source: bytes) -> None:
    if node.type == "block":
        for child in node.named_children:
            if _is_comment(child):
                continue
            _emit_control_flow(builder, child, source)
    else:
        _emit_control_flow(builder, node, source)


def _walk_calls(node: Node) -> list[Node]:
    out: list[Node] = []
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "invocation_expression":
            out.append(n)
        for c in n.children:
            stack.append(c)
    return out


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _short(text: str, limit: int = 60) -> str:
    first = next((line for line in text.splitlines() if line.strip()), text).strip()
    return first[:limit] + ("…" if len(first) > limit else "")
