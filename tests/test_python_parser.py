"""Parse the python_demo fixture and assert the resulting model."""

from __future__ import annotations

from pathlib import Path

from code_constraints.core.model import DiffStatus, Visibility
from code_constraints.python import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "python_demo"


def _find_class(project, qualified_name):
    return next(c for c in project.iter_classes() if c.qualified_name == qualified_name)


def test_packages_match_directory_layout() -> None:
    project = parse_project(FIXTURE)
    qns = {p.qualified_name for p in project.packages}
    sub_qns = {sub.qualified_name for p in project.packages for sub in p.sub_packages}
    all_qns = qns | sub_qns
    assert {"animals", "store"}.issubset(all_qns)


def test_classes_extracted_with_inheritance() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "animals.Animal")
    dog = _find_class(project, "animals.Dog")
    assert animal.kind == "abstract"  # inherits from ABC
    assert dog.bases == ["Animal"]


def test_instance_attributes_picked_up_from_init() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "store.Cart")
    names = {a.name for a in cart.attributes}
    assert {"items", "_total"}.issubset(names)
    total = next(a for a in cart.attributes if a.name == "_total")
    assert total.visibility == Visibility.PROTECTED


def test_operations_with_parameters_and_returns() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "store.Cart")
    add = next(op for op in cart.operations if op.name == "add")
    assert [p.name for p in add.parameters] == ["item", "price"]
    assert add.parameters[1].type == "float"


def test_class_docstring_becomes_description() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "animals.Animal")
    assert animal.description is not None
    assert "menagerie" in animal.description


def test_method_docstring_becomes_description() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "animals.Animal")
    speak = next(op for op in animal.operations if op.name == "speak")
    assert speak.description is not None
    assert "sound" in speak.description


def test_missing_docstring_yields_none() -> None:
    project = parse_project(FIXTURE)
    dog = _find_class(project, "animals.Dog")
    assert dog.description is None


def test_activity_tag_produces_activity() -> None:
    project = parse_project(FIXTURE)
    names = [a.name for a in project.activities]
    assert "dog_speak" in names
    act = next(a for a in project.activities if a.name == "dog_speak")
    assert any(n.kind == "decision" for n in act.nodes)
    assert any(n.kind == "initial" for n in act.nodes)
    assert any(n.kind == "final" for n in act.nodes)


def test_sequence_tag_produces_sequence() -> None:
    project = parse_project(FIXTURE)
    names = [s.name for s in project.sequences]
    assert "checkout_flow" in names
    seq = next(s for s in project.sequences if s.name == "checkout_flow")
    labels = [m.label for m in seq.messages]
    assert "authorize()" in labels
    assert "capture()" in labels


def test_sequence_call_order_is_inner_first(tmp_path) -> None:
    """`payment.charge(payment.total())` must emit `total()` before `charge()`."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "class C:\n"
        "    def go(self, payment):\n"
        "        # <uml-sequence name=\"order\" root=\"self\">\n"
        "        payment.charge(payment.total())\n"
        "        # </uml-sequence>\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "order")
    labels = [m.label for m in seq.messages]
    # total() (inner) must come before charge() (outer).
    assert labels.index("total()") < labels.index("charge()"), labels


def test_sequence_emits_return_after_each_call(tmp_path) -> None:
    """Each forward call must be followed by a paired return (receiver→sender)
    so the diagram shows the value coming back."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "class C:\n"
        "    def go(self, payment):\n"
        "        # <uml-sequence name=\"echo\" root=\"self\">\n"
        "        payment.ping()\n"
        "        # </uml-sequence>\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "echo")
    # forward: self -> payment : ping()
    # return:  payment -> self : (anonymous)
    assert len(seq.messages) == 2
    assert seq.messages[0].is_return is False
    assert seq.messages[0].sender == "self" and seq.messages[0].receiver == "payment"
    assert seq.messages[1].is_return is True
    assert seq.messages[1].sender == "payment" and seq.messages[1].receiver == "self"


def test_sequence_return_label_from_assignment(tmp_path) -> None:
    """For `result = obj.fn()` the outermost call's return is labeled `result`."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "class C:\n"
        "    def go(self, obj):\n"
        "        # <uml-sequence name=\"assign\" root=\"self\">\n"
        "        result = obj.fn(obj.inner())\n"
        "        # </uml-sequence>\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "assign")
    # 4 messages: inner() + ret(anon), fn() + ret("result")
    fwd_labels = [m.label for m in seq.messages if not m.is_return]
    ret_labels = [m.label for m in seq.messages if m.is_return]
    assert fwd_labels == ["inner()", "fn()"]
    # Inner return is anonymous; outer return labeled with assignment target.
    assert ret_labels == ["", "result"]


def test_sequence_fragment_per_if_branch(tmp_path) -> None:
    """If/else builds two adjacent fragments covering their respective rows."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "class C:\n"
        "    def go(self, obj):\n"
        "        # <uml-sequence name=\"alt\" root=\"self\">\n"
        "        result = obj.check()\n"
        "        if result == 'ok':\n"
        "            obj.commit()\n"
        "        else:\n"
        "            obj.rollback()\n"
        "        # </uml-sequence>\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "alt")
    assert len(seq.fragments) == 2
    if_frag, else_frag = seq.fragments
    assert if_frag.kind == "alt"
    assert if_frag.label == "result == 'ok'"
    assert else_frag.kind == "alt"
    assert "else" in else_frag.label
    # The two fragments cover non-overlapping consecutive row ranges.
    assert if_frag.end_row + 1 == else_frag.start_row


def test_sequence_final_return_self_message(tmp_path) -> None:
    """`return X` at the end of the tagged region emits a self-return on root."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "class C:\n"
        "    def go(self):\n"
        "        # <uml-sequence name=\"ends\" root=\"self\">\n"
        "        return self.status\n"
        "        # </uml-sequence>\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "ends")
    # one forward+return for self.status access? No — bare attribute access is
    # not a Call, so only the synthetic self-return for the `return` statement.
    assert len(seq.messages) == 1
    m = seq.messages[0]
    assert m.is_return is True
    assert m.sender == m.receiver == "self"
    assert m.label == "return self.status"


def test_sequence_guards_from_if_branch(tmp_path) -> None:
    """Calls inside `if cond: ...` carry guard='cond'; else gets `not (cond)`."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text(
        "class C:\n"
        "    def go(self, obj):\n"
        "        # <uml-sequence name=\"branchy\" root=\"self\">\n"
        "        result = obj.check()\n"
        "        if result == 'ok':\n"
        "            obj.commit()\n"
        "        else:\n"
        "            obj.rollback()\n"
        "        # </uml-sequence>\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "branchy")
    by_label = {m.label: m for m in seq.messages}
    assert by_label["check()"].guard == ""
    assert by_label["commit()"].guard == "result == 'ok'"
    assert by_label["rollback()"].guard == "not (result == 'ok')"
