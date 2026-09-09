"""Engine B (`cdec enforce`) and Engine C (`cdec lock`) for Odin, Lua and Julia.

The parser tests cover the model; these cover the two engines that read bodies.
The lock cases are the important ones: they assert the *invariants* that make a
lock an AST identity rather than a line range, per language, because each one
strips its tag differently (comment vs. macro wrapper) and each grammar names
its comment nodes differently.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from code_constraints.enforce.engine import enforce
from code_constraints.lock.engine import collect_targets

FIXTURES = Path(__file__).parent / "fixtures"

# (lang, fixture dir, source file, the locked target's qualified name)
CASES = [
    ("odin", "odin_demo", "billing/invoice.odin", "billing.Invoice.formatted"),
    ("lua", "lua_demo", "billing/invoice.lua", "billing.Invoice.formatted"),
    ("julia", "julia_demo", "billing/invoice.jl", "billing.Billing.Invoice.formatted"),
]

# How to strip the `@locked` tag, per language.
TAG_LINES = {
    "odin": '//@cdec locked(reason = "agreed rounding")\n',
    "lua": '---@cdec locked(reason = "agreed rounding")\n',
    "julia": '@locked reason="agreed rounding" ',
}

# (body text to find, a comment-only edit, a semantic edit)
BODY_EDITS = {
    "odin": ("\treturn inv.id", "\t// note\n\treturn inv.id", '\treturn inv.id + "x"'),
    "lua": ("  return self.id", "  -- note\n  return self.id", '  return self.id .. "x"'),
    "julia": ("    return inv.id", "    # note\n    return inv.id", '    return inv.id * "x"'),
}

# Something harmless inserted at the top of the file, to prove a lock is not a
# line range.
PREAMBLE = {
    "odin": ("package billing\n", "package billing\n\nUNRELATED :: 1\n"),
    "lua": (
        'local Money = require("billing.money")\n',
        'local Money = require("billing.money")\nlocal UNRELATED = 1\n',
    ),
    "julia": ("using CdecRules\n", "using CdecRules\n\nconst UNRELATED = 1\n"),
}


def _digest(root, lang, target):
    for t in collect_targets(str(root), lang):
        if t.target == target:
            return t.digest
    raise AssertionError(f"{lang}: no lock target named {target}")


def _edited(tmp_path, fixture, rel, old, new):
    dest = tmp_path / "project"
    shutil.copytree(FIXTURES / fixture, dest)
    path = dest / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture text drifted; not found: {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return dest


# ---------- Engine C: lock fingerprints ----------

@pytest.mark.parametrize("lang,fixture,rel,target", CASES)
def test_locked_element_is_discovered_with_its_tag_metadata(lang, fixture, rel, target):
    found = [t for t in collect_targets(str(FIXTURES / fixture), lang) if t.declared]
    assert [t.target for t in found] == [target]
    assert found[0].reason == "agreed rounding"


@pytest.mark.parametrize("lang,fixture,rel,target", CASES)
def test_applying_or_removing_the_tag_does_not_change_the_digest(
    tmp_path, lang, fixture, rel, target
):
    # The whole feature depends on this: if the tag were part of the digest,
    # `cdec lock set` could never record a stable baseline for it.
    base = _digest(FIXTURES / fixture, lang, target)
    edited = _edited(tmp_path, fixture, rel, TAG_LINES[lang], "")
    assert _digest(edited, lang, target) == base


@pytest.mark.parametrize("lang,fixture,rel,target", CASES)
def test_comment_edits_do_not_change_the_digest(tmp_path, lang, fixture, rel, target):
    base = _digest(FIXTURES / fixture, lang, target)
    old, commented, _semantic = BODY_EDITS[lang]
    edited = _edited(tmp_path, fixture, rel, old, commented)
    assert _digest(edited, lang, target) == base


@pytest.mark.parametrize("lang,fixture,rel,target", CASES)
def test_inserting_code_above_does_not_change_the_digest(
    tmp_path, lang, fixture, rel, target
):
    # A lock is an AST identity, not a line range.
    base = _digest(FIXTURES / fixture, lang, target)
    old, new = PREAMBLE[lang]
    edited = _edited(tmp_path, fixture, rel, old, new)
    assert _digest(edited, lang, target) == base


@pytest.mark.parametrize("lang,fixture,rel,target", CASES)
def test_a_semantic_body_change_does_change_the_digest(
    tmp_path, lang, fixture, rel, target
):
    base = _digest(FIXTURES / fixture, lang, target)
    old, _commented, semantic = BODY_EDITS[lang]
    edited = _edited(tmp_path, fixture, rel, old, semantic)
    assert _digest(edited, lang, target) != base


_ALGOS = {"odin": "odin-ts/1", "lua": "lua-ts/1", "julia": "jl-ts/1"}


@pytest.mark.parametrize("lang,fixture,rel,target", CASES)
def test_digest_algo_is_language_specific_and_versioned(lang, fixture, rel, target):
    # Changing a serialiser must bump this id, so a mismatch reads as
    # "re-baseline" rather than as a false "implementation changed".
    algos = {t.algo for t in collect_targets(str(FIXTURES / fixture), lang)}
    assert algos == {_ALGOS[lang]}


def test_julia_keeps_non_rule_macros_significant(tmp_path):
    # The Julia digest is taken over the *unwrapped* definition, so foreign
    # macros are folded in separately. Without that, adding `@inline` to a locked
    # function would be invisible.
    target = "billing.Billing.Invoice.formatted"
    base = _digest(FIXTURES / "julia_demo", "julia", target)
    edited = _edited(
        tmp_path,
        "julia_demo",
        "billing/invoice.jl",
        '@locked reason="agreed rounding" function formatted',
        '@locked reason="agreed rounding" @inline function formatted',
    )
    assert _digest(edited, "julia", target) != base


def test_lua_class_target_does_not_inherit_a_method_tag():
    # A Lua class digests its methods too, but a `---@cdec locked` above
    # `function T:m()` locks the method — not the class.
    targets = {t.target: t for t in collect_targets(str(FIXTURES / "lua_demo"), "lua")}
    assert targets["billing.Invoice"].declared is False
    assert targets["billing.Invoice.formatted"].declared is True


# ---------- Engine B: conformance ----------

@pytest.mark.parametrize(
    "lang,fixture",
    [("odin", "odin_demo"), ("lua", "lua_demo"), ("julia", "julia_demo")],
)
def test_fixtures_produce_no_body_analysis_findings(lang, fixture):
    # The fixtures tag `no_instantiation(allow=[...])` on a method that only
    # constructs the allowed type, so a body finding here means the analyzer is
    # over-reporting. (`sealed` is structural, not body analysis, and the Odin
    # and Lua fixtures deliberately do subtype their sealed `Invoice` — see
    # `test_fixtures_report_their_sealed_subtype`.)
    body_rules = {"no-instantiation", "factory", "immutable"}
    findings = [f for f in enforce(FIXTURES / fixture, lang) if f.rule in body_rules]
    assert findings == []


@pytest.mark.parametrize("lang,fixture", [("odin", "odin_demo"), ("lua", "lua_demo")])
def test_fixtures_report_their_sealed_subtype(lang, fixture):
    # Both fixtures declare `Detailed` on top of a `@sealed Invoice`, via each
    # language's own subtyping mechanism (Odin `using` embedding, a Lua
    # `__index` metatable). Engine B must see through both to the same finding.
    sealed = [f for f in enforce(FIXTURES / fixture, lang) if f.rule == "sealed"]
    assert [f.qualified_name for f in sealed] == ["billing.Detailed"]


EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.mark.parametrize(
    "lang,demo",
    [("odin", "odin_demo"), ("lua", "lua_demo"), ("julia", "julia_demo")],
)
def test_demo_reports_exactly_the_seeded_violation(lang, demo):
    # Each example carries one intentional violation in `quick_receipt`, which
    # trips both `no-instantiation` and `factory`. This is the canonical
    # end-to-end demo, so it is worth asserting exactly.
    findings = enforce(EXAMPLES / demo, lang)
    assert {f.rule for f in findings} == {"no-instantiation", "factory"}
    assert all(f.qualified_name.endswith("CheckoutService") for f in findings)
    assert all("quick_receipt" in f.detail for f in findings)


@pytest.mark.parametrize(
    "lang,demo",
    [("odin", "odin_demo"), ("lua", "lua_demo"), ("julia", "julia_demo")],
)
def test_a_type_may_construct_itself(lang, demo):
    # The `T.new(...)` / inner-constructor idiom constructs the owning type; that
    # is never a `factory` or `no_instantiation` violation, or every Lua
    # constructor would be flagged.
    findings = enforce(EXAMPLES / demo, lang)
    assert not any(f.detail.endswith("->Receipt") and "new" in f.detail for f in findings)


def test_sealed_is_enforced_structurally(tmp_path):
    # `sealed` needs no body analysis: it compares the tag against every other
    # class's base list, so it works the moment a language has a parser.
    src = tmp_path / "billing"
    src.mkdir()
    (src / "a.odin").write_text(
        "package billing\n"
        "//@cdec sealed\n"
        "Base :: struct { id: int }\n"
        "Derived :: struct { using base: Base, extra: int }\n",
        encoding="utf-8",
    )
    findings = enforce(tmp_path, "odin")
    assert [f.rule for f in findings] == ["sealed"]
    assert findings[0].qualified_name == "billing.Derived"
