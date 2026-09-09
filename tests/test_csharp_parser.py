"""Parse the csharp_demo fixture and assert the resulting model."""

from __future__ import annotations

from pathlib import Path

from code_constraints.core.model import Visibility
from code_constraints.csharp import parse_project

FIXTURE = Path(__file__).parent / "fixtures" / "csharp_demo"


def _find_class(project, qualified_name):
    return next(c for c in project.iter_classes() if c.qualified_name == qualified_name)


def test_namespaces_become_packages() -> None:
    project = parse_project(FIXTURE)
    all_qns: set[str] = set()

    def walk(pkgs):
        for p in pkgs:
            all_qns.add(p.qualified_name)
            walk(p.sub_packages)

    walk(project.packages)
    assert "Zoo" in all_qns
    assert "Zoo.Animals" in all_qns
    assert "Zoo.Store" in all_qns


def test_xml_doc_summary_becomes_class_description() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "Zoo.Animals.Animal")
    assert animal.description is not None
    assert "menagerie" in animal.description


def test_xml_doc_summary_becomes_method_description() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "Zoo.Animals.Animal")
    speak = next(op for op in animal.operations if op.name == "Speak")
    assert speak.description is not None
    assert "sound" in speak.description


def test_missing_xml_doc_yields_none() -> None:
    project = parse_project(FIXTURE)
    dog = _find_class(project, "Zoo.Animals.Dog")
    assert dog.description is None


def test_xml_doc_in_file_scoped_namespace() -> None:
    """File-scoped namespaces (`namespace X;`) host top-level classes as
    siblings of the namespace declaration, so the `prev_sibling` walk had to
    survive that arrangement."""
    project = parse_project(FIXTURE)
    cart = _find_class(project, "Zoo.Store.Cart")
    assert cart.description is not None
    assert "Shopping cart" in cart.description
    iface = _find_class(project, "Zoo.Store.IPayment")
    assert iface.description == "Anything that can take money from a customer."


def test_xml_doc_multi_line_summary_collapses_whitespace() -> None:
    project = parse_project(FIXTURE)
    cart = _find_class(project, "Zoo.Store.Cart")
    # The fixture's <summary> spans three lines; the extractor should join
    # them into a single space-separated string, not preserve the line breaks.
    assert "\n" not in (cart.description or "")
    assert "file-scoped namespace" in (cart.description or "")


def test_xml_doc_inner_tags_are_stripped(tmp_path) -> None:
    """<see cref="..."/> and <paramref name="..."/> inside a <summary> are
    XML-doc syntax; the prose around them is what the user wants to read."""
    src = (
        'namespace P;\n'
        '/// <summary>Save. See <see cref="P.Widget"/> for details.</summary>\n'
        'public class Widget { public void Save() {} }\n'
    )
    (tmp_path / "p.cs").write_text(src, encoding="utf-8")
    project = parse_project(tmp_path)
    widget = next(c for c in project.iter_classes() if c.name == "Widget")
    assert widget.description is not None
    assert "<see" not in widget.description
    assert "cref" not in widget.description
    assert "Save. See" in widget.description and "for details." in widget.description


def test_xml_doc_survives_attribute_decoration(tmp_path) -> None:
    """The very common `/// summary\\n[Attribute]\\nclass X { }` pattern must
    still attach the comment to the class — attributes sit on the declaration
    node, not between comment siblings."""
    src = (
        'namespace P;\n'
        '/// <summary>A serialisable widget.</summary>\n'
        '[System.Serializable]\n'
        'public class Widget\n'
        '{\n'
        '    /// <summary>Save the widget.</summary>\n'
        '    [System.Obsolete]\n'
        '    public void Save() {}\n'
        '}\n'
    )
    (tmp_path / "p.cs").write_text(src, encoding="utf-8")
    project = parse_project(tmp_path)
    widget = next(c for c in project.iter_classes() if c.name == "Widget")
    assert widget.description == "A serialisable widget."
    save = next(op for op in widget.operations if op.name == "Save")
    assert save.description == "Save the widget."


def test_xml_doc_fallback_strips_tags_when_no_summary(tmp_path) -> None:
    """If the developer wrote bare `///` text without a <summary> wrapper, take
    the text — but strip any other XML tags they may have used."""
    src = (
        'namespace P;\n'
        '/// A bare doc comment with <c>code</c> inside.\n'
        'public class Widget { }\n'
    )
    (tmp_path / "p.cs").write_text(src, encoding="utf-8")
    project = parse_project(tmp_path)
    widget = next(c for c in project.iter_classes() if c.name == "Widget")
    assert widget.description == "A bare doc comment with code inside."


def test_static_class_gets_static_kind(tmp_path) -> None:
    """A `static class` is distinguished from a plain class so the viewer can
    colour-code it."""
    src = (
        'namespace P;\n'
        'public static class MathUtils { public static int Add(int a, int b) => a + b; }\n'
        'public class Widget { }\n'
    )
    (tmp_path / "p.cs").write_text(src, encoding="utf-8")
    project = parse_project(tmp_path)
    utils = next(c for c in project.iter_classes() if c.name == "MathUtils")
    widget = next(c for c in project.iter_classes() if c.name == "Widget")
    assert utils.kind == "static"
    assert widget.kind == "class"


def test_class_with_inheritance() -> None:
    project = parse_project(FIXTURE)
    dog = _find_class(project, "Zoo.Animals.Dog")
    assert dog.bases == ["Animal"]
    animal = _find_class(project, "Zoo.Animals.Animal")
    assert animal.kind == "abstract"


def test_properties_and_fields_become_attributes() -> None:
    project = parse_project(FIXTURE)
    animal = _find_class(project, "Zoo.Animals.Animal")
    names = {a.name for a in animal.attributes}
    assert "Name" in names
    assert "Legs" in names
    legs = next(a for a in animal.attributes if a.name == "Legs")
    assert legs.visibility == Visibility.PROTECTED


def test_field_declarations_carry_types() -> None:
    """Regression: tree-sitter exposes `type` on variable_declaration, NOT on
    field_declaration. Reading the wrong node silently produces typeless
    attributes — most visible on structs with bare public fields."""
    project = parse_project(FIXTURE)
    animal = _find_class(project, "Zoo.Animals.Animal")
    legs = next(a for a in animal.attributes if a.name == "Legs")
    assert legs.type == "int"

    cart = _find_class(project, "Zoo.Store.Cart")
    total = next(a for a in cart.attributes if a.name == "_total")
    assert total.type == "double"


def test_interface_extracted() -> None:
    project = parse_project(FIXTURE)
    ipayment = _find_class(project, "Zoo.Store.IPayment")
    assert ipayment.kind == "interface"
    names = {op.name for op in ipayment.operations}
    assert {"Authorize", "Capture"}.issubset(names)


def test_activity_tag_in_csharp() -> None:
    project = parse_project(FIXTURE)
    names = [a.name for a in project.activities]
    assert "dog_speak" in names
    act = next(a for a in project.activities if a.name == "dog_speak")
    assert any(n.kind == "decision" for n in act.nodes)


def test_sequence_tag_in_csharp() -> None:
    project = parse_project(FIXTURE)
    names = [s.name for s in project.sequences]
    assert "checkout_flow" in names
    seq = next(s for s in project.sequences if s.name == "checkout_flow")
    labels = [m.label for m in seq.messages]
    assert "Authorize()" in labels
    assert "Capture()" in labels


def test_csharp_sequence_call_order_is_inner_first(tmp_path) -> None:
    """`Cart.Checkout(Cart.Total())` must emit `Total()` before `Checkout()`."""
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public class C {\n"
        "  public int Go(Cart cart) {\n"
        "    // <uml-sequence name=\"order\" root=\"this\">\n"
        "    var result = cart.Checkout(cart.Total());\n"
        "    // </uml-sequence>\n"
        "    return 0;\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "order")
    labels = [m.label for m in seq.messages]
    assert labels.index("Total()") < labels.index("Checkout()"), labels


def test_csharp_sequence_emits_paired_returns(tmp_path) -> None:
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public class C {\n"
        "  public void Go(Payment p) {\n"
        "    // <uml-sequence name=\"echo\" root=\"this\">\n"
        "    p.Ping();\n"
        "    // </uml-sequence>\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "echo")
    assert len(seq.messages) == 2
    assert seq.messages[0].is_return is False
    assert seq.messages[1].is_return is True
    assert seq.messages[1].sender == "p" and seq.messages[1].receiver == "this"


def test_csharp_sequence_return_label_from_var_decl(tmp_path) -> None:
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public class C {\n"
        "  public void Go(Obj o) {\n"
        "    // <uml-sequence name=\"assign\" root=\"this\">\n"
        "    var result = o.Fn(o.Inner());\n"
        "    // </uml-sequence>\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "assign")
    fwd = [m.label for m in seq.messages if not m.is_return]
    ret = [m.label for m in seq.messages if m.is_return]
    assert fwd == ["Inner()", "Fn()"]
    assert ret == ["", "result"]


def test_csharp_sequence_fragments_per_if_branch(tmp_path) -> None:
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public class C {\n"
        "  public void Go(Obj obj) {\n"
        "    // <uml-sequence name=\"alt\" root=\"this\">\n"
        "    var result = obj.Check();\n"
        "    if (result == \"ok\") {\n"
        "      obj.Commit();\n"
        "    } else {\n"
        "      obj.Rollback();\n"
        "    }\n"
        "    // </uml-sequence>\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "alt")
    assert len(seq.fragments) == 2
    if_frag, else_frag = seq.fragments
    assert if_frag.kind == "alt"
    assert if_frag.label == 'result == "ok"'
    assert "else" in else_frag.label
    assert if_frag.end_row + 1 == else_frag.start_row


def test_csharp_sequence_final_return_self_message(tmp_path) -> None:
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public class C {\n"
        "  public int Go() {\n"
        "    // <uml-sequence name=\"ends\" root=\"this\">\n"
        "    return 42;\n"
        "    // </uml-sequence>\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "ends")
    assert len(seq.messages) == 1
    m = seq.messages[0]
    assert m.is_return is True
    assert m.sender == m.receiver == "this"
    assert m.label == "return 42"


def test_csharp_sequence_guards_from_if_branch(tmp_path) -> None:
    """C# `if (cond) { ... } else { ... }` attaches `cond` / `!(cond)` guards."""
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public class C {\n"
        "  public void Go(Obj obj) {\n"
        "    // <uml-sequence name=\"branchy\" root=\"this\">\n"
        "    var result = obj.Check();\n"
        "    if (result == \"ok\") {\n"
        "      obj.Commit();\n"
        "    } else {\n"
        "      obj.Rollback();\n"
        "    }\n"
        "    // </uml-sequence>\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    seq = next(s for s in project.sequences if s.name == "branchy")
    by_label = {m.label: m for m in seq.messages}
    assert by_label["Check()"].guard == ""
    assert by_label["Commit()"].guard == 'result == "ok"'
    assert by_label["Rollback()"].guard == '!(result == "ok")'


def test_method_body_static_call_populates_dependencies(tmp_path) -> None:
    """A static-call receiver inside a method body is captured in `dependencies`."""
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public static class ControlUtils {\n"
        "  public static int Trigger() { return 1; }\n"
        "}\n"
        "public class Transitions {\n"
        "  public int Evaluate() {\n"
        "    return ControlUtils.Trigger();\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    transitions = _find_class(project, "N.Transitions")
    assert "ControlUtils" in transitions.dependencies


def test_method_body_dependencies_exclude_owning_class(tmp_path) -> None:
    """The class's own name is not listed as a self-dependency."""
    (tmp_path / "M.cs").write_text(
        "namespace N;\n"
        "public class Foo {\n"
        "  public Foo Make() { return new Foo(); }\n"
        "}\n",
        encoding="utf-8",
    )
    project = parse_project(tmp_path)
    foo = _find_class(project, "N.Foo")
    assert "Foo" not in foo.dependencies
