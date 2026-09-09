"""Build a UML `Sequence` from a tagged C# region.

Mirrors the semantics of the Python parser — see that module for the
overall design (post-order calls, paired returns, fragments per if-branch,
self-return for `return X` at the end). This module just adapts the same
rules to tree-sitter's C# grammar.
"""

from __future__ import annotations

from tree_sitter import Node, Tree

from code_constraints.core.model import Fragment, Lifeline, Message, Sequence, SourceLocation
from code_constraints.core.tags import TagInstance


def build_sequence_from_tag(
    tag: TagInstance, tree: Tree, source: bytes, *, file: str
) -> Sequence | None:
    if not tag.name:
        return None
    root = tag.attributes.get("root", "this")
    stmts = _statements_in_range(tree.root_node, tag.start_line, tag.end_line)
    if not stmts:
        return None

    state = _State(root=root, source=source)
    _emit_messages(stmts, [], state)

    return Sequence(
        name=tag.name,
        lifelines=list(state.lifelines.values()),
        messages=state.messages,
        fragments=state.fragments,
        location=SourceLocation(file=file, start_line=tag.start_line, end_line=tag.end_line),
    )


class _State:
    def __init__(self, root: str, source: bytes) -> None:
        self.root = root
        self.source = source
        self.lifelines: dict[str, Lifeline] = {root: Lifeline(name=root, represents=root)}
        self.messages: list[Message] = []
        self.fragments: list[Fragment] = []

    def ensure_lifeline(self, name: str) -> None:
        if name not in self.lifelines:
            self.lifelines[name] = Lifeline(name=name, represents=name)


_BODY_HOLDERS = {
    "method_declaration",
    "constructor_declaration",
    "local_function_statement",
    "destructor_declaration",
}


def _statements_in_range(root: Node, start: int, end: int) -> list[Node]:
    best: list[Node] | None = None
    best_start = -1
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        if node.type in _BODY_HOLDERS:
            body = node.child_by_field_name("body")
            if body is not None and body.type == "block":
                node_def_line = node.start_point[0] + 1
                body_end_line = body.end_point[0] + 1
                if node_def_line < start and body_end_line >= start:
                    stmts = [
                        c
                        for c in body.named_children
                        if c.type != "comment"
                        and start < (c.start_point[0] + 1) < end
                    ]
                    if stmts and node_def_line > best_start:
                        best = stmts
                        best_start = node_def_line
        for c in node.children:
            stack.append(c)
    return best or []


def _emit_messages(
    stmts: list[Node],
    active_guards: list[str],
    state: _State,
) -> None:
    guard_str = " and ".join(active_guards)
    for stmt in stmts:
        if stmt.type == "if_statement":
            _emit_if(stmt, active_guards, state)
        elif stmt.type == "return_statement":
            value_node = _return_value(stmt)
            _emit_calls_in(value_node, guard_str, state, return_label="")
            value_text = _text(value_node, state.source).strip() if value_node else ""
            label = f"return {value_text}" if value_text else "return"
            state.messages.append(
                Message(
                    sender=state.root,
                    receiver=state.root,
                    label=label,
                    is_return=True,
                    guard=guard_str,
                )
            )
        elif stmt.type == "local_declaration_statement":
            # Walk variable_declarator(s); the initializer is the last named
            # child of the declarator. We pair the OUTERMOST call's return
            # with the variable name.
            for declarator, init_node in _iter_declarators(stmt):
                name = ""
                name_node = declarator.child_by_field_name("name")
                if name_node is not None:
                    name = _text(name_node, state.source).strip()
                _emit_calls_in(init_node, guard_str, state, return_label=name)
        elif stmt.type == "expression_statement":
            inner = stmt.named_child(0) if stmt.named_child_count else None
            # If it's an assignment_expression and the RHS is a single
            # invocation, treat it like a local declaration so the return
            # gets labeled with the LHS target name.
            if inner is not None and inner.type == "assignment_expression":
                left = inner.child_by_field_name("left")
                right = inner.child_by_field_name("right")
                target = _text(left, state.source).strip() if left else ""
                _emit_calls_in(right, guard_str, state, return_label=target)
            else:
                _emit_calls_in(stmt, guard_str, state, return_label="")
        else:
            _emit_calls_in(stmt, guard_str, state, return_label="")


def _iter_declarators(local_decl: Node):
    """Yield (declarator, initializer_expr) pairs in `local_declaration_statement`."""
    var_decl = None
    for c in local_decl.named_children:
        if c.type == "variable_declaration":
            var_decl = c
            break
    if var_decl is None:
        return
    for declarator in var_decl.named_children:
        if declarator.type != "variable_declarator":
            continue
        # The initializer expression is the named child that isn't `name`.
        name_node = declarator.child_by_field_name("name")
        init = None
        for c in declarator.named_children:
            if c is name_node:
                continue
            init = c
        yield declarator, init


def _return_value(return_stmt: Node) -> Node | None:
    """Get the optional expression child of a `return_statement`."""
    for c in return_stmt.named_children:
        if c.type != "comment":
            return c
    return None


def _emit_if(stmt: Node, active_guards: list[str], state: _State) -> None:
    cond_node = stmt.child_by_field_name("condition")
    cond_text = _text(cond_node, state.source).strip() if cond_node else ""

    # Calls inside the condition execute unconditionally (relative to the
    # enclosing context) — keep current guards.
    if cond_node is not None:
        _emit_calls_in(cond_node, " and ".join(active_guards), state, return_label="")

    consequence = stmt.child_by_field_name("consequence")
    has_else = stmt.child_by_field_name("alternative") is not None
    if consequence is not None:
        body_start = len(state.messages)
        _emit_messages(
            _branch_stmts(consequence),
            active_guards + [cond_text] if cond_text else active_guards,
            state,
        )
        body_end = len(state.messages) - 1
        if body_end >= body_start:
            state.fragments.append(
                Fragment(
                    kind="alt" if has_else else "opt",
                    label=cond_text,
                    start_row=body_start,
                    end_row=body_end,
                )
            )

    alternative = stmt.child_by_field_name("alternative")
    if alternative is not None:
        neg = f"!({cond_text})" if cond_text else ""
        else_start = len(state.messages)
        _emit_messages(
            _branch_stmts(alternative),
            active_guards + [neg] if neg else active_guards,
            state,
        )
        else_end = len(state.messages) - 1
        if else_end >= else_start:
            state.fragments.append(
                Fragment(
                    kind="alt",
                    label=f"else ({cond_text} is false)",
                    start_row=else_start,
                    end_row=else_end,
                )
            )


def _branch_stmts(node: Node) -> list[Node]:
    if node.type == "block":
        return [c for c in node.named_children if c.type != "comment"]
    return [node]


def _emit_calls_in(
    node: Node | None,
    guard: str,
    state: _State,
    *,
    return_label: str,
) -> None:
    if node is None:
        return
    invs = _invocations_post_order(node)
    if not invs:
        return
    last_idx = len(invs) - 1
    for i, inv in enumerate(invs):
        rl = return_label if i == last_idx else ""
        _emit_call(inv, state.root, guard, state, return_label=rl)


def _invocations_post_order(node: Node) -> list[Node]:
    out: list[Node] = []

    def visit(n: Node) -> None:
        for c in n.children:
            visit(c)
        if n.type == "invocation_expression":
            out.append(n)

    visit(node)
    return out


def _emit_call(
    inv: Node,
    root: str,
    guard: str,
    state: _State,
    *,
    return_label: str,
) -> None:
    sender, receiver, label = _resolve_invocation(inv, state.source, root)
    state.ensure_lifeline(receiver)
    state.ensure_lifeline(sender)
    state.messages.append(
        Message(sender=sender, receiver=receiver, label=label, guard=guard)
    )
    state.messages.append(
        Message(
            sender=receiver,
            receiver=sender,
            label=return_label,
            is_return=True,
            guard=guard,
        )
    )


def _resolve_invocation(
    inv: Node, source: bytes, root: str
) -> tuple[str, str, str]:
    func = inv.child_by_field_name("function")
    if func is None:
        return root, "module", "()"
    if func.type == "member_access_expression":
        expr = func.child_by_field_name("expression")
        name = func.child_by_field_name("name")
        receiver = _text(expr, source) if expr else "obj"
        label = (_text(name, source) if name else "method") + "()"
        return root, receiver, label
    return root, "module", _text(func, source) + "()"


def _text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
