"""Build a UML `Sequence` from a tagged Python region.

Three semantics worth pinning down:

1. **Call evaluation order is preserved.** Calls within a single statement
   are emitted innermost-first (post-order), matching Python's evaluation
   order. For `cart.checkout(cart.total())` we emit `total()` before
   `checkout()` — the argument is computed before the outer dispatch.

2. **Each call has a paired return arrow.** Right after the forward
   `root → receiver` message we emit a dashed `receiver → root` return
   message. The return is anonymous (empty label) by default; when the
   call is the *outermost* call in an `Assign` statement we use the
   assignment target as the return label (e.g. `result = cart.checkout(...)`
   produces a return labelled `result`).

3. **Branches become combined fragments + guard prefixes.** For
   `if cond: ...` we attach `cond` to every message inside the body as a
   guard string AND emit a `Fragment(kind="alt", label=cond, …)` covering
   the body's message rows; the `else` branch gets a sibling fragment with
   the negation. `return X` at the top level emits a self-return on the
   root with label `return X`, giving the diagram an explicit endpoint.
"""

from __future__ import annotations

import ast

from code_constraints.core.model import Fragment, Lifeline, Message, Sequence, SourceLocation
from code_constraints.core.tags import TagInstance


def build_sequence_from_tag(
    tag: TagInstance, tree: ast.Module, source: str, *, file: str
) -> Sequence | None:
    if not tag.name:
        return None
    root = tag.attributes.get("root", "self")

    stmts = _statements_in_range(tree, tag.start_line, tag.end_line)
    if not stmts:
        return None

    state = _State(root=root)
    _emit_messages(stmts, [], state)

    return Sequence(
        name=tag.name,
        lifelines=list(state.lifelines.values()),
        messages=state.messages,
        fragments=state.fragments,
        location=SourceLocation(file=file, start_line=tag.start_line, end_line=tag.end_line),
    )


class _State:
    """Mutable accumulator threaded through the recursive emitter."""

    def __init__(self, root: str) -> None:
        self.root = root
        self.lifelines: dict[str, Lifeline] = {root: Lifeline(name=root, represents=root)}
        self.messages: list[Message] = []
        self.fragments: list[Fragment] = []

    def ensure_lifeline(self, name: str) -> None:
        if name not in self.lifelines:
            self.lifelines[name] = Lifeline(name=name, represents=name)


def _emit_messages(
    stmts: list[ast.stmt],
    active_guards: list[str],
    state: _State,
) -> None:
    """Walk top-level `stmts`, dispatching ifs/returns into special handlers
    and letting any other statement contribute its calls in post-order."""
    guard_str = " and ".join(active_guards)
    for stmt in stmts:
        if isinstance(stmt, ast.If):
            _emit_if(stmt, active_guards, state)
        elif isinstance(stmt, ast.Return):
            _emit_calls_in(stmt.value, guard_str, state, return_label="")
            value_text = _safe_unparse(stmt.value) if stmt.value is not None else ""
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
        elif isinstance(stmt, ast.Assign):
            target = ""
            if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                target = stmt.targets[0].id
            _emit_calls_in(stmt.value, guard_str, state, return_label=target)
        elif isinstance(stmt, ast.AnnAssign):
            target = ""
            if isinstance(stmt.target, ast.Name):
                target = stmt.target.id
            if stmt.value is not None:
                _emit_calls_in(stmt.value, guard_str, state, return_label=target)
        else:
            _emit_calls_in(stmt, guard_str, state, return_label="")


def _emit_if(stmt: ast.If, active_guards: list[str], state: _State) -> None:
    cond_text = _safe_unparse(stmt.test)
    # Calls in the condition execute unconditionally — keep the current guards.
    _emit_calls_in(stmt.test, " and ".join(active_guards), state, return_label="")

    # Body: capture row range so we can emit a fragment covering it.
    body_start = len(state.messages)
    _emit_messages(stmt.body, active_guards + [cond_text], state)
    body_end = len(state.messages) - 1
    if body_end >= body_start:
        state.fragments.append(
            Fragment(
                kind="alt" if stmt.orelse else "opt",
                label=cond_text,
                start_row=body_start,
                end_row=body_end,
            )
        )

    if stmt.orelse:
        else_start = len(state.messages)
        _emit_messages(stmt.orelse, active_guards + [f"not ({cond_text})"], state)
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


def _emit_calls_in(
    node: ast.AST | None,
    guard: str,
    state: _State,
    *,
    return_label: str,
) -> None:
    """Emit forward + return messages for every Call inside `node`.

    `return_label` decorates the return of the OUTERMOST call only (the one
    yielded last by post-order). Inner calls always get an anonymous return.
    """
    if node is None:
        return
    calls = list(_calls_post_order(node))
    if not calls:
        return
    last_idx = len(calls) - 1
    for i, call in enumerate(calls):
        rl = return_label if i == last_idx else ""
        _emit_call(call, state.root, guard, state, return_label=rl)


def _emit_call(
    call: ast.Call,
    root: str,
    guard: str,
    state: _State,
    *,
    return_label: str,
) -> None:
    sender, receiver, label = _resolve_call(call, root)
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


def _calls_post_order(node: ast.AST):
    """Yield Call nodes inside `node` in inner-first (post-order) order."""
    for child in ast.iter_child_nodes(node):
        yield from _calls_post_order(child)
    if isinstance(node, ast.Call):
        yield node


def _safe_unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _statements_in_range(tree: ast.Module, start: int, end: int) -> list[ast.stmt]:
    out: list[ast.stmt] = []
    candidates: list[tuple[int, list[ast.stmt]]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            f_start = getattr(node, "lineno", 0)
            if not node.body:
                continue
            body_end = max(
                (getattr(s, "end_lineno", getattr(s, "lineno", 0)) or 0)
                for s in node.body
            )
            if f_start < start and body_end >= start:
                stmts = [s for s in node.body if start < getattr(s, "lineno", 0) < end]
                if stmts:
                    candidates.append((f_start, stmts))
    if candidates:
        candidates.sort(key=lambda c: c[0])
        return candidates[-1][1]
    for stmt in tree.body:
        s_start = getattr(stmt, "lineno", 0)
        if start < s_start < end:
            out.append(stmt)
    return out


def _resolve_call(call: ast.Call, root: str) -> tuple[str, str, str]:
    func = call.func
    if isinstance(func, ast.Attribute):
        receiver_name = _receiver_name(func.value, root)
        label = func.attr + "()"
        return root, receiver_name, label
    if isinstance(func, ast.Name):
        return root, "module", f"{func.id}()"
    try:
        return root, "module", f"{ast.unparse(func)}()"
    except Exception:
        return root, "module", "call()"


def _receiver_name(node: ast.AST, root: str) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        try:
            return ast.unparse(node)
        except Exception:
            return node.attr
    try:
        return ast.unparse(node)
    except Exception:
        return "obj"
