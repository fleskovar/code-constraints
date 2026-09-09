"""Tests for the shared `@cdec` annotation-comment parser.

The tag carrier for Lua and Odin. These lock the parsing contract that both
languages' `rules_extract` modules depend on — argument shapes, the forgiving
behaviour on malformed input, and the line-adjacency rule that makes a comment
block read like a stack of decorators.
"""

from __future__ import annotations

import tree_sitter_lua
from tree_sitter import Language, Parser

from code_constraints.core.annotations import (
    literal_set,
    parse_annotation,
    rules_before_node,
    rules_from_comments,
)

_PARSER = Parser(Language(tree_sitter_lua.language()))


def test_bare_tag_needs_no_parentheses():
    rule = parse_annotation("---@cdec sealed")
    assert rule is not None
    assert rule.name == "sealed"
    assert rule.args == []
    assert rule.kwargs == {}


def test_positional_argument_keeps_source_text():
    # Values round-trip verbatim so `layer_dependencies._layer_of` can strip the
    # quotes the same way it does for Python and C#.
    rule = parse_annotation('//@cdec layer("domain")')
    assert rule is not None
    assert rule.name == "layer"
    assert rule.args == ['"domain"']


def test_keyword_arguments_are_split_on_the_first_equals():
    rule = parse_annotation('---@cdec locked(reason = "why = how", owner = "ann")')
    assert rule is not None
    assert rule.kwargs == {"reason": '"why = how"', "owner": '"ann"'}


def test_list_arguments_survive_nested_commas():
    rule = parse_annotation('//@cdec no_instantiation(allow = ["A", "B"])')
    assert rule is not None
    assert rule.kwargs == {"allow": '["A", "B"]'}
    assert literal_set(rule.kwargs["allow"]) == {"A", "B"}


def test_lua_table_literal_parses_as_a_name_set():
    # Lua writes lists as `{...}`, which is a Python set literal — so the same
    # `literal_set` reads Lua, Odin, Julia and C# argument values.
    assert literal_set('{"Money", "Cart"}') == {"Money", "Cart"}


def test_trailing_comment_after_a_tag_is_not_an_argument():
    rule = parse_annotation('---@cdec layer("domain")  -- the core of it')
    assert rule is not None
    assert rule.args == ['"domain"']


def test_unknown_rule_name_is_skipped():
    assert parse_annotation("---@cdec no_such_rule") is None


def test_plain_comment_is_not_a_tag():
    assert parse_annotation("-- just a note about @cdec tags") is None


def test_malformed_tag_is_skipped_not_raised():
    # The parser is deliberately forgiving: a typo must never fail a whole file.
    assert parse_annotation("---@cdec") is None
    assert rules_from_comments(["---@cdec (", "---@cdec sealed"]) == [
        r for r in [parse_annotation("---@cdec sealed")] if r
    ]


def test_unbalanced_parenthesis_still_yields_the_rule():
    rule = parse_annotation('---@cdec layer("domain"')
    assert rule is not None
    assert rule.name == "layer"


def _node_after(src: str):
    tree = _PARSER.parse(src.encode())
    return tree.root_node.named_children[-1], src.encode()


def test_stacked_tags_keep_source_order():
    node, source = _node_after(
        '---@cdec sealed\n---@cdec layer("domain")\nlocal T = {}\n'
    )
    rules = rules_before_node(node, source)
    assert [r.name for r in rules] == ["sealed", "layer"]


def test_a_blank_line_detaches_the_tag():
    # Without line adjacency there is no way to tell a decorator-style tag from
    # unrelated prose earlier in the file, so the gap has to break the chain.
    node, source = _node_after("---@cdec sealed\n\nlocal T = {}\n")
    assert rules_before_node(node, source) == []


def test_untagged_comments_in_the_block_are_ignored_but_do_not_break_it():
    node, source = _node_after(
        "---@cdec sealed\n-- an ordinary note\n---@cdec immutable\nlocal T = {}\n"
    )
    assert [r.name for r in rules_before_node(node, source)] == ["sealed", "immutable"]
