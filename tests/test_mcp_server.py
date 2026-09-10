"""Tests for the MCP tool surface (`code_constraints.mcp`).

The properties that matter here are the ones a coding harness depends on and
that no other test covers:

* the tools resolve relative paths against the server's project root, so an
  agent can pass repo-relative paths without knowing where the harness launched
  the process;
* a tool call and the equivalent `cdec` invocation report the same issue keys —
  if they diverge, `cdec_allow` silently stops matching what `cdec_check` printed;
* the privilege boundaries survive the transport: locks are not acceptable as
  exceptions, and `cdec_accept(what=["locks"])` still refuses to re-baseline
  drifted code without `force`.
"""

from __future__ import annotations

import anyio
import pytest
import yaml
from typer.testing import CliRunner

from code_constraints.cli.__main__ import app

mcp_sdk = pytest.importorskip("mcp", reason="the MCP server needs the optional `mcp` extra")

from code_constraints.mcp.server import build_server  # noqa: E402

PY_SHIM = '''
def locked(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj


def no_instantiation(*args, **kwargs):
    if len(args) == 1 and not kwargs and callable(args[0]):
        return args[0]
    return lambda obj: obj
'''

BILLING = '''\
from cdec_rules import locked, no_instantiation


class Invoice:
    @locked(reason="agreed settlement order")
    def settle(self, amount):
        tax = amount * 0.2
        return amount + tax


class Ledger:
    @no_instantiation
    def record(self, amount):
        return Invoice()
'''

RULES = """\
language: python
source: src_tree
reference: .cdec/reference.xmi

rules:
  - id: no-new-classes
    type: no-new-classes

  - id: tags-must-be-honoured
    type: tag-conformance
    severity: error

  - id: frozen-implementations
    type: implementation-locks
    severity: error

  - id: public-shape-is-frozen
    type: reference-architecture
    severity: error
"""


@pytest.fixture()
def project(tmp_path):
    """A scaffolded project with one locked method and one seeded violation."""
    src = tmp_path / "src_tree"
    src.mkdir()
    (src / "cdec_rules.py").write_text(PY_SHIM, encoding="utf-8")
    (src / "billing.py").write_text(BILLING, encoding="utf-8")

    cdec = tmp_path / ".cdec"
    cdec.mkdir()
    (cdec / "rules.yaml").write_text(RULES, encoding="utf-8")

    _cli(["check", "--automatic-exceptions", "reference,locks"], tmp_path)
    return tmp_path


def _rules_doc(project):
    return yaml.safe_load((project / ".cdec" / "rules.yaml").read_text(encoding="utf-8"))


def _cli(args, cwd):
    """Run the real CLI in `cwd`, the way a developer would."""
    import os

    prev = os.getcwd()
    os.chdir(cwd)
    try:
        return CliRunner().invoke(app, args)
    finally:
        os.chdir(prev)


def _call(root, name, **arguments):
    """Invoke one MCP tool and return its structured payload."""
    server = build_server(root)

    async def go():
        return await server.call_tool(name, arguments)

    return anyio.run(go).structured_content


# ---------------- wiring ----------------

def test_every_tool_is_registered_and_described(tmp_path) -> None:
    """A tool with no description is unusable to a model, so guard both."""
    server = build_server(tmp_path)

    async def go():
        return await server.list_tools()

    tools = {t.name: t for t in anyio.run(go)}
    assert "cdec_check" in tools and "cdec_allow" in tools and "cdec_propose" in tools
    for name, tool in tools.items():
        assert name.startswith("cdec_"), f"{name} is missing the cdec_ prefix"
        assert tool.description, f"{name} has no description"


def test_status_reports_an_unconfigured_project(tmp_path) -> None:
    out = _call(tmp_path, "cdec_status")
    assert out["configured"] is False
    assert "cdec init" in out["hint"]


def test_status_reports_a_configured_project(project) -> None:
    out = _call(project, "cdec_status")
    assert out["configured"] is True
    assert out["language"] == "python"
    assert out["reference"]["exists"] is True
    assert out["locks"] == 1
    assert {r["type"] for r in out["rules"]} >= {
        "tag-conformance", "implementation-locks", "reference-architecture"
    }
    assert out["rules_file"].endswith("rules.yaml")


def test_rule_types_lists_what_can_go_in_rules_yaml(tmp_path) -> None:
    """An agent writing a rule needs the real `type:` values, not a guess."""
    out = _call(tmp_path, "cdec_rule_types")
    by_type = {r["type"]: r for r in out["rule_types"]}
    assert "forbidden-package-references" in by_type
    assert by_type["tag-conformance"]["reads_source"] is True
    assert by_type["implementation-locks"]["baselines_itself"] is True
    assert by_type["no-new-classes"]["default_scope"] == "diff"


def test_rules_lists_the_catalogue(tmp_path) -> None:
    out = _call(tmp_path, "cdec_rules")
    ids = {r["id"] for r in out["rules"]}
    assert {"no-instantiation", "sealed", "locked"} <= ids
    assert "cdec_rules" in out["shims"]["python_import"]


# ---------------- path resolution ----------------

def test_relative_paths_resolve_against_the_project_root(project) -> None:
    """The harness decides the CWD; the agent should not have to know it."""
    out = _call(project, "cdec_parse", out="models/current.json")
    assert out["ok"] is True
    assert (project / "models" / "current.json").is_file()


def test_paths_outside_the_root_still_work_when_absolute(project, tmp_path) -> None:
    dest = tmp_path / "elsewhere" / "model.xmi"
    out = _call(project, "cdec_parse", out=str(dest))
    assert dest.is_file()
    assert out["classes"] >= 2


# ---------------- the gate ----------------

def test_check_runs_every_rule_in_one_call(project) -> None:
    """One tool, one verdict — the whole reason the surface was collapsed."""
    out = _call(project, "cdec_check")
    assert out["ok"] is False, "the seeded conformance violation should fail the gate"
    engines = {v["engine"] for v in out["violations"]}
    assert engines == {"enforce"}, "only the tag rule should fire on a clean tree"
    rules = {v["rule"] for v in out["violations"]}
    assert "no-instantiation" in rules


def test_check_passes_on_an_untouched_locked_body(project) -> None:
    """The lock rule is silent when it holds — nothing to report is a pass."""
    out = _call(project, "cdec_check")
    assert not [v for v in out["violations"] if v["engine"] == "lock"]


def test_check_fails_once_a_frozen_body_changes(project) -> None:
    billing = project / "src_tree" / "billing.py"
    billing.write_text(
        billing.read_text(encoding="utf-8").replace("amount * 0.2", "amount * 0.3"),
        encoding="utf-8",
    )
    out = _call(project, "cdec_check")
    assert out["ok"] is False
    locks = [v for v in out["violations"] if v["engine"] == "lock"]
    assert locks and locks[0]["qualified_name"] == "Invoice.settle"
    assert locks[0]["waivable"] is False


def test_lock_identity_is_ast_based_not_line_based(project) -> None:
    """Inserting code above a locked element must not trip the lock."""
    billing = project / "src_tree" / "billing.py"
    billing.write_text(
        "# a new comment\nCONSTANT = 1\n\n" + billing.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    out = _call(project, "cdec_check")
    assert not [v for v in out["violations"] if v["engine"] == "lock"]


def test_locks_separates_tagged_from_baselined(project) -> None:
    out = _call(project, "cdec_locks")
    by_target = {row["target"]: row for row in out["targets"]}
    assert by_target["Invoice.settle"]["tagged"] is True
    assert by_target["Invoice.settle"]["baselined"] is True
    assert by_target["Ledger.record"]["tagged"] is False
    assert out["rule_configured"] is True


def test_check_reports_a_rule_it_could_not_run(tmp_path) -> None:
    """A rule that silently checks nothing looks exactly like one that passed."""
    src = tmp_path / "src_tree"
    src.mkdir()
    (src / "a.ts").write_text("export class Alpha {}\n", encoding="utf-8")
    (tmp_path / ".cdec").mkdir()
    (tmp_path / ".cdec" / "rules.yaml").write_text(
        "language: typescript\nsource: src_tree\n\n"
        "rules:\n  - id: frozen-implementations\n"
        "    type: implementation-locks\n    severity: error\n",
        encoding="utf-8",
    )
    out = _call(tmp_path, "cdec_check")
    assert out["ok"] is True
    assert out["skipped"][0]["rule_id"] == "frozen-implementations"


# ---------------- the review loop ----------------

def test_issues_keys_match_what_the_cli_reports(project) -> None:
    """The whole review loop rests on this: a key an agent reads over MCP has to
    be the key `cdec exceptions allow` accepts on the command line."""
    from_mcp = {i["key"] for i in _call(project, "cdec_issues")["issues"]}
    result = _cli(["exceptions", "review"], project)
    assert from_mcp, "expected at least one open issue"
    for key in from_mcp:
        assert key in result.stdout


def test_allow_records_a_waiver_and_silences_the_issue(project) -> None:
    key = next(
        i["key"] for i in _call(project, "cdec_issues")["issues"] if i["engine"] == "enforce"
    )
    out = _call(project, "cdec_allow", keys=[key], reason="agreed in ARCH-42")
    assert out["ok"] is True and out["written"] is True

    doc = _rules_doc(project)
    assert any(e["reason"] == "agreed in ARCH-42" for e in doc["exceptions"])
    assert doc["rules"], "the hand-written rules must survive the write"

    assert key not in {i["key"] for i in _call(project, "cdec_issues")["issues"]}
    assert key in {
        w["key"] for w in _call(project, "cdec_exceptions_list")["exceptions"]
    }


def test_dry_run_reports_without_writing(project) -> None:
    key = next(
        i["key"] for i in _call(project, "cdec_issues")["issues"] if i["engine"] == "enforce"
    )
    before = (project / ".cdec" / "rules.yaml").read_text(encoding="utf-8")
    out = _call(project, "cdec_allow", keys=[key], reason="nope", dry_run=True)
    assert out["allowed"] and out["written"] is False
    assert (project / ".cdec" / "rules.yaml").read_text(encoding="utf-8") == before


def test_a_stale_key_is_an_error_not_a_silent_no_op(project) -> None:
    out = _call(project, "cdec_allow", keys=["V-DEADBEEF"])
    assert out["ok"] is False
    assert out["unknown"] == ["V-DEADBEEF"]


def test_removing_a_waiver_makes_the_issue_block_again(project) -> None:
    key = next(
        i["key"] for i in _call(project, "cdec_issues")["issues"] if i["engine"] == "enforce"
    )
    _call(project, "cdec_allow", keys=[key], reason="temporary")
    out = _call(project, "cdec_exception_remove", keys=[key])
    assert out["ok"] is True and out["removed"] == [key]
    assert key in {i["key"] for i in _call(project, "cdec_issues")["issues"]}


def test_prune_drops_waivers_whose_issue_is_gone(project) -> None:
    key = next(
        i["key"] for i in _call(project, "cdec_issues")["issues"] if i["engine"] == "enforce"
    )
    _call(project, "cdec_allow", keys=[key], reason="for now")

    billing = project / "src_tree" / "billing.py"
    billing.write_text(
        billing.read_text(encoding="utf-8").replace("return Invoice()", "return None"),
        encoding="utf-8",
    )
    out = _call(project, "cdec_exceptions_prune")
    assert [w["key"] for w in out["pruned"]] == [key]


# ---------------- privilege boundaries ----------------

def test_locks_are_not_acceptable_over_mcp(project) -> None:
    """Accepting a changed frozen implementation must stay a ledger diff, not an
    exception — the refusal has to survive the transport."""
    billing = project / "src_tree" / "billing.py"
    billing.write_text(
        billing.read_text(encoding="utf-8").replace("amount * 0.2", "amount * 0.9"),
        encoding="utf-8",
    )
    key = next(
        i["key"] for i in _call(project, "cdec_issues")["issues"] if i["engine"] == "lock"
    )
    out = _call(project, "cdec_allow", keys=[key])
    assert out["ok"] is False
    assert out["refused"] and out["refused"][0]["key"] == key
    assert "--automatic-exceptions locks --force" in out["refused"][0]["reason"]


def test_accept_locks_will_not_rebaseline_drift_without_force(project) -> None:
    billing = project / "src_tree" / "billing.py"
    before = _rules_doc(project)["locks"][0]["digest"]
    billing.write_text(
        billing.read_text(encoding="utf-8").replace("amount * 0.2", "amount * 0.5"),
        encoding="utf-8",
    )
    out = _call(project, "cdec_accept", what=["locks"])
    assert any("CHANGED" in line for line in out["recorded"]["locks"])
    assert _rules_doc(project)["locks"][0]["digest"] == before
    assert _call(project, "cdec_check")["ok"] is False


def test_accept_locks_with_force_rebaselines_and_leaves_a_diff(project) -> None:
    billing = project / "src_tree" / "billing.py"
    before = _rules_doc(project)["locks"][0]["digest"]
    billing.write_text(
        billing.read_text(encoding="utf-8").replace("amount * 0.2", "amount * 0.5"),
        encoding="utf-8",
    )
    out = _call(project, "cdec_accept", what=["locks"], force=True)
    assert any("rebased" in line for line in out["recorded"]["locks"])
    assert _rules_doc(project)["locks"][0]["digest"] != before
    assert not [
        v for v in _call(project, "cdec_check")["violations"] if v["engine"] == "lock"
    ]


def test_accept_rules_never_grandfathers_a_lock(project) -> None:
    billing = project / "src_tree" / "billing.py"
    billing.write_text(
        billing.read_text(encoding="utf-8").replace("amount * 0.2", "amount * 0.5"),
        encoding="utf-8",
    )
    out = _call(project, "cdec_accept", what=["rules"])
    assert out["not_grandfathered"], "the lock must be reported, not swallowed"
    assert "force=True" in out["hint"]
    assert _call(project, "cdec_check")["ok"] is False


# ---------------- the model pipeline ----------------

def _reference_violations(project):
    return [
        v for v in _call(project, "cdec_check")["violations"] if v["engine"] == "reference"
    ]


def test_the_reference_rule_reports_structural_deviation(project) -> None:
    assert not _reference_violations(project)

    (project / "src_tree" / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    deviations = _reference_violations(project)
    assert len(deviations) == 1
    assert deviations[0]["key"].startswith("R-")


def test_accept_reference_resnapshots_the_current_code(project) -> None:
    (project / "src_tree" / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    assert _reference_violations(project)

    out = _call(project, "cdec_accept", what=["reference"])
    assert out["recorded"]["reference"]
    assert not _reference_violations(project)


def test_reference_set_promotes_an_authored_model(project) -> None:
    _call(project, "cdec_parse", out="target.json")
    (project / "src_tree" / "extra.py").write_text("class Extra:\n    pass\n", encoding="utf-8")
    assert _reference_violations(project)

    out = _call(project, "cdec_reference_set", model="target.json")
    assert out["ok"] is True
    # The promoted model predates `extra.py`, so the deviation must persist.
    assert _reference_violations(project)


def test_convert_round_trips_a_model(project) -> None:
    _call(project, "cdec_parse", out="model.xmi")
    out = _call(project, "cdec_convert", src="model.xmi", dest="model.json")
    assert (project / "model.json").is_file()
    assert out["classes"] == _call(project, "cdec_convert", src="model.json", dest="rt.xmi")[
        "classes"
    ]


# ---------------- error reporting ----------------

def test_a_missing_project_is_a_clean_tool_error(tmp_path) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="rules.yaml"):
        _call(tmp_path, "cdec_check")


def test_a_bad_source_path_is_a_clean_tool_error(project) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="not a directory"):
        _call(project, "cdec_locks", source="does_not_exist")


def test_propose_refuses_rather_than_blocking_when_no_viewer_runs(project) -> None:
    """The tool must never start a blocking server inside the MCP process."""
    from mcp.server.mcpserver.exceptions import ToolError

    _call(project, "cdec_parse", out="target.json")
    with pytest.raises(ToolError, match="no code-constraints viewer"):
        _call(project, "cdec_propose", model="target.json", start_viewer=False, port=8791)
