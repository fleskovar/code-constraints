"""Digest properties for `cdec lock` (Engine C).

The whole feature rests on one contract: the digest must ignore *where* code
sits and *how* it is written, and must move on any semantic edit. These tests
pin both halves for Python and C#.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from code_constraints.csharp.fingerprint import collect_lockables as collect_csharp
from code_constraints.python.fingerprint import collect_lockables as collect_python

PY_SHIM = '''
def locked(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj


def sealed(obj):
    return obj
'''

CS_SHIM = """
using System;
namespace CodeConstraints.Rules
{
    [AttributeUsage(AttributeTargets.All)]
    public sealed class LockedAttribute : Attribute
    {
        public string Reason { get; set; } = "";
    }
}
"""


def _py_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "src"
    root.mkdir(exist_ok=True)
    (root / "cdec_rules.py").write_text(PY_SHIM, encoding="utf-8")
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _cs_tree(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "src"
    root.mkdir(exist_ok=True)
    (root / "CodeConstraintsRules.cs").write_text(CS_SHIM, encoding="utf-8")
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    return root


def _digest(targets, name: str) -> str:
    for t in targets:
        if t.target == name:
            return t.digest
    raise AssertionError(f"{name!r} not among {[t.target for t in targets]}")


def _find(targets, name: str):
    for t in targets:
        if t.target == name:
            return t
    raise AssertionError(f"{name!r} not among {[t.target for t in targets]}")


# ---------- Python: stability ----------

BILLING_V1 = '''\
from cdec_rules import locked


class Invoice:
    @locked(reason="agreed settlement order")
    def settle(self, amount):
        tax = amount * 0.2
        return amount + tax
'''


def test_python_digest_survives_code_inserted_above(tmp_path):
    """The headline requirement: a lock is an AST identity, not a line range."""
    root = _py_tree(tmp_path, {"billing.py": BILLING_V1})
    before = _digest(collect_python(root), "Invoice.settle")

    shifted = BILLING_V1.replace(
        "class Invoice:",
        "CONSTANT = 1\n\n\ndef helper():\n    return 2\n\n\nclass Invoice:",
    )
    (root / "billing.py").write_text(shifted, encoding="utf-8")
    assert _digest(collect_python(root), "Invoice.settle") == before


def test_python_digest_survives_reformatting_and_comments(tmp_path):
    root = _py_tree(tmp_path, {"billing.py": BILLING_V1})
    before = _digest(collect_python(root), "Invoice.settle")

    reformatted = BILLING_V1.replace(
        "        tax = amount * 0.2\n        return amount + tax\n",
        "        # a new explanatory comment\n"
        "        tax = (\n            amount\n            * 0.2\n        )\n"
        "        return amount + tax\n",
    )
    (root / "billing.py").write_text(reformatted, encoding="utf-8")
    assert _digest(collect_python(root), "Invoice.settle") == before


def test_python_digest_ignores_docstrings_by_default(tmp_path):
    root = _py_tree(tmp_path, {"billing.py": BILLING_V1})
    before = _digest(collect_python(root), "Invoice.settle")

    documented = BILLING_V1.replace(
        "    def settle(self, amount):\n",
        '    def settle(self, amount):\n        """Settle the invoice."""\n',
    )
    (root / "billing.py").write_text(documented, encoding="utf-8")
    assert _digest(collect_python(root), "Invoice.settle") == before
    # ...but opt in and the docstring counts.
    assert (
        _digest(collect_python(root, include_docstrings=True), "Invoice.settle")
        != before
    )


def test_python_digest_ignores_the_lock_tag_itself(tmp_path):
    """Adding or removing @locked must not change the digest, or every lock
    would be born stale the moment it was applied."""
    root = _py_tree(tmp_path, {"billing.py": BILLING_V1})
    before = _digest(collect_python(root), "Invoice.settle")

    untagged = BILLING_V1.replace('    @locked(reason="agreed settlement order")\n', "")
    (root / "billing.py").write_text(untagged, encoding="utf-8")
    assert _digest(collect_python(root), "Invoice.settle") == before


def test_python_class_digest_ignores_nested_lock_tags(tmp_path):
    """A method-level lock inside a locked class must not disturb the class
    digest — the two locks have to be independently applicable."""
    root = _py_tree(tmp_path, {"billing.py": BILLING_V1})
    before = _digest(collect_python(root), "Invoice")

    also_locked = BILLING_V1.replace("class Invoice:", "@locked\nclass Invoice:")
    (root / "billing.py").write_text(also_locked, encoding="utf-8")
    assert _digest(collect_python(root), "Invoice") == before


# ---------- Python: sensitivity ----------

@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(("amount * 0.2", "amount * 0.25"), id="constant"),
        pytest.param(("return amount + tax", "return amount - tax"), id="operator"),
        pytest.param(("tax = amount", "vat = amount"), id="local-rename"),
        pytest.param(("def settle(self, amount)", "def settle(self, amount, fee=0)"), id="signature"),
        pytest.param(
            ("        tax = amount * 0.2\n", "        log(amount)\n        tax = amount * 0.2\n"),
            id="added-statement",
        ),
    ],
)
def test_python_digest_moves_on_semantic_edit(tmp_path, mutation):
    old, new = mutation
    root = _py_tree(tmp_path, {"billing.py": BILLING_V1})
    before = _digest(collect_python(root), "Invoice.settle")

    mutated = BILLING_V1.replace(old, new)
    assert mutated != BILLING_V1, "test mutation did not apply"
    (root / "billing.py").write_text(mutated, encoding="utf-8")
    assert _digest(collect_python(root), "Invoice.settle") != before


def test_python_statement_reordering_is_a_change(tmp_path):
    """A lock on 'a specific sequence of steps' must notice a reordering."""
    src = '''\
from cdec_rules import locked


@locked
def pipeline(data):
    data = validate(data)
    data = normalize(data)
    return data
'''
    root = _py_tree(tmp_path, {"flow.py": src})
    before = _digest(collect_python(root), "flow.pipeline")

    swapped = src.replace(
        "    data = validate(data)\n    data = normalize(data)\n",
        "    data = normalize(data)\n    data = validate(data)\n",
    )
    (root / "flow.py").write_text(swapped, encoding="utf-8")
    assert _digest(collect_python(root), "flow.pipeline") != before


# ---------- Python: identity / grouping ----------

def test_python_targets_use_package_qualified_names(tmp_path):
    root = _py_tree(tmp_path, {"orders/billing.py": BILLING_V1})
    (root / "orders" / "__init__.py").write_text("", encoding="utf-8")
    names = {t.target for t in collect_python(root)}
    assert "orders.Invoice" in names
    assert "orders.Invoice.settle" in names


def test_python_module_functions_are_module_qualified(tmp_path):
    """Two modules in one package may define the same function name, so module
    functions carry the module stem while classes stay package-qualified."""
    root = _py_tree(
        tmp_path,
        {
            "orders/a.py": "def run():\n    return 1\n",
            "orders/b.py": "def run():\n    return 2\n",
        },
    )
    names = {t.target for t in collect_python(root)}
    assert {"orders.a.run", "orders.b.run"} <= names


def test_python_overloads_collapse_into_one_grouped_target(tmp_path):
    """Same-named siblings share a target whose digest covers the whole group,
    so adding an overload to a locked name is itself a change."""
    src = '''\
class Config:
    @property
    def value(self):
        return self._v
'''
    root = _py_tree(tmp_path, {"conf.py": src})
    targets = [t for t in collect_python(root) if t.target == "Config.value"]
    assert len(targets) == 1
    before = targets[0].digest

    with_setter = src + '''
    @value.setter
    def value(self, v):
        self._v = v
'''
    (root / "conf.py").write_text(with_setter, encoding="utf-8")
    after = [t for t in collect_python(root) if t.target == "Config.value"]
    assert len(after) == 1
    assert after[0].digest != before


def test_python_declared_flag_and_params(tmp_path):
    root = _py_tree(tmp_path, {"billing.py": BILLING_V1})
    target = _find(collect_python(root), "Invoice.settle")
    assert target.declared is True
    assert target.reason == "agreed settlement order"
    assert _find(collect_python(root), "Invoice").declared is False


def test_python_tag_only_counts_from_the_shim(tmp_path):
    """A user's own `locked` decorator must never be mistaken for the tag."""
    src = '''\
from mylib import locked


@locked
def helper():
    return 1
'''
    root = _py_tree(tmp_path, {"other.py": src})
    assert _find(collect_python(root), "other.helper").declared is False


# ---------- C# ----------

CS_V1 = """\
using CodeConstraints.Rules;

namespace Orders
{
    public class Invoice
    {
        [Locked(Reason = "agreed settlement order")]
        public decimal Settle(decimal amount)
        {
            var tax = amount * 0.2m;
            return amount + tax;
        }
    }
}
"""


def test_csharp_digest_survives_code_inserted_above(tmp_path):
    root = _cs_tree(tmp_path, {"Invoice.cs": CS_V1})
    before = _digest(collect_csharp(root), "Orders.Invoice.Settle")

    shifted = CS_V1.replace(
        "    public class Invoice",
        "    public class Helper { public int N() { return 1; } }\n\n    public class Invoice",
    )
    (root / "Invoice.cs").write_text(shifted, encoding="utf-8")
    assert _digest(collect_csharp(root), "Orders.Invoice.Settle") == before


def test_csharp_digest_survives_reformatting_and_comments(tmp_path):
    root = _cs_tree(tmp_path, {"Invoice.cs": CS_V1})
    before = _digest(collect_csharp(root), "Orders.Invoice.Settle")

    reformatted = CS_V1.replace(
        "            var tax = amount * 0.2m;\n",
        "            // explain the rate\n            var tax =\n                amount * 0.2m;\n",
    )
    (root / "Invoice.cs").write_text(reformatted, encoding="utf-8")
    assert _digest(collect_csharp(root), "Orders.Invoice.Settle") == before


def test_csharp_digest_ignores_the_lock_attribute(tmp_path):
    root = _cs_tree(tmp_path, {"Invoice.cs": CS_V1})
    before = _digest(collect_csharp(root), "Orders.Invoice.Settle")

    untagged = CS_V1.replace(
        '        [Locked(Reason = "agreed settlement order")]\n', ""
    )
    (root / "Invoice.cs").write_text(untagged, encoding="utf-8")
    assert _digest(collect_csharp(root), "Orders.Invoice.Settle") == before


def test_csharp_digest_keeps_other_attributes(tmp_path):
    """Only the lock tag is stripped — a real attribute is part of the code."""
    root = _cs_tree(tmp_path, {"Invoice.cs": CS_V1})
    before = _digest(collect_csharp(root), "Orders.Invoice.Settle")

    annotated = CS_V1.replace(
        '        [Locked(Reason = "agreed settlement order")]\n',
        '        [Locked(Reason = "agreed settlement order")]\n        [Obsolete]\n',
    )
    (root / "Invoice.cs").write_text(annotated, encoding="utf-8")
    assert _digest(collect_csharp(root), "Orders.Invoice.Settle") != before


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(("amount * 0.2m", "amount * 0.25m"), id="constant"),
        pytest.param(("return amount + tax", "return amount - tax"), id="operator"),
        pytest.param(("var tax", "var vat"), id="local-rename"),
    ],
)
def test_csharp_digest_moves_on_semantic_edit(tmp_path, mutation):
    old, new = mutation
    root = _cs_tree(tmp_path, {"Invoice.cs": CS_V1})
    before = _digest(collect_csharp(root), "Orders.Invoice.Settle")

    mutated = CS_V1.replace(old, new)
    assert mutated != CS_V1, "test mutation did not apply"
    (root / "Invoice.cs").write_text(mutated, encoding="utf-8")
    assert _digest(collect_csharp(root), "Orders.Invoice.Settle") != before


def test_csharp_declared_flag_and_params(tmp_path):
    root = _cs_tree(tmp_path, {"Invoice.cs": CS_V1})
    target = _find(collect_csharp(root), "Orders.Invoice.Settle")
    assert target.declared is True
    assert target.reason == "agreed settlement order"


def test_csharp_tag_requires_the_shim_namespace(tmp_path):
    """Without `using CodeConstraints.Rules;` a same-named attribute is not the tag."""
    src = CS_V1.replace("using CodeConstraints.Rules;\n", "")
    root = _cs_tree(tmp_path, {"Invoice.cs": src})
    assert _find(collect_csharp(root), "Orders.Invoice.Settle").declared is False


def test_csharp_overloads_collapse_into_one_grouped_target(tmp_path):
    root = _cs_tree(tmp_path, {"Invoice.cs": CS_V1})
    before = _digest(collect_csharp(root), "Orders.Invoice.Settle")

    overloaded = CS_V1.replace(
        "        }\n    }\n}",
        "        }\n\n        public decimal Settle(decimal a, decimal b) { return a + b; }\n    }\n}",
    )
    (root / "Invoice.cs").write_text(overloaded, encoding="utf-8")
    targets = [t for t in collect_csharp(root) if t.target == "Orders.Invoice.Settle"]
    assert len(targets) == 1
    assert targets[0].digest != before


def test_csharp_file_scoped_namespace(tmp_path):
    src = """\
using CodeConstraints.Rules;

namespace Orders;

public class Receipt
{
    [Locked]
    public string Format() => "x";
}
"""
    root = _cs_tree(tmp_path, {"Receipt.cs": src})
    assert _find(collect_csharp(root), "Orders.Receipt.Format").declared is True
