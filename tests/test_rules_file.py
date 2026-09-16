"""`.cdec/rules.yaml` — one committed file holding four kinds of content.

The risk this file guards is specific. `rules:` is hand-written and carries the
explanations that make a failed build teach something; `exceptions:` and
`locks:` are written by the tool. A naive round-trip through PyYAML would delete
every comment and reflow every `message: |` block the first time anybody
accepted a violation, and nobody would notice until they read a diff.

So the writer is surgical, and these tests hold it to that.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from code_constraints.core.rulesdoc import (
    MANAGED_KEYS,
    RulesFileError,
    load_document,
    read_section,
    write_sections,
)
from code_constraints.lint.config import ConfigError, load_project_config, load_rules
from code_constraints.lock.model import LockEntry
from code_constraints.lock.store import load_locks, write_locks
from code_constraints.waivers.store import Waiver, load_waivers, save_waivers

HAND_WRITTEN = """\
# The settings a person edits.
language: python
source: src

# The laws, and why they exist.
rules:
  - id: domain-is-pure
    type: forbidden-package-references
    severity: error
    from: ["app.domain.**"]
    to: ["app.ui.**"]
    message: |
      Layering violation: '{source}' must not depend on '{target}'.
      Move the reference to whichever package owns the workflow.
"""


@pytest.fixture()
def rules_file(tmp_path: Path) -> Path:
    path = tmp_path / ".cdec" / "rules.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(HAND_WRITTEN, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The surgical write
# ---------------------------------------------------------------------------

def test_writing_a_managed_section_preserves_the_hand_written_part(rules_file):
    write_sections(rules_file, {"exceptions": [{"key": "V-1A2B3C4D", "reason": "why"}]})
    text = rules_file.read_text(encoding="utf-8")

    assert "# The settings a person edits." in text
    assert "# The laws, and why they exist." in text
    assert "Move the reference to whichever package owns the workflow." in text
    assert text.startswith(HAND_WRITTEN.rstrip("\n"))


def test_a_block_scalar_message_survives_verbatim(rules_file):
    write_sections(rules_file, {"exceptions": [{"key": "V-1A2B3C4D"}]})
    doc = load_document(rules_file)
    assert doc["rules"][0]["message"] == (
        "Layering violation: '{source}' must not depend on '{target}'.\n"
        "Move the reference to whichever package owns the workflow.\n"
    )


def test_the_two_managed_sections_do_not_overwrite_each_other(rules_file):
    """Exceptions and locks are written by different engines at different times."""
    write_sections(rules_file, {"exceptions": [{"key": "V-1A2B3C4D"}]})
    write_sections(rules_file, {"locks": [{"target": "a.B.c", "digest": "abc"}]})

    doc = load_document(rules_file)
    assert doc["exceptions"] == [{"key": "V-1A2B3C4D"}]
    assert doc["locks"] == [{"target": "a.B.c", "digest": "abc"}]


def test_an_empty_section_is_removed_rather_than_left_as_a_stub(rules_file):
    write_sections(rules_file, {"exceptions": [{"key": "V-1A2B3C4D"}]})
    write_sections(rules_file, {"exceptions": []})
    assert "exceptions" not in load_document(rules_file)


def test_rewriting_twice_is_idempotent(rules_file):
    write_sections(rules_file, {"exceptions": [{"key": "V-1A2B3C4D"}]})
    once = rules_file.read_text(encoding="utf-8")
    write_sections(rules_file, {"exceptions": [{"key": "V-1A2B3C4D"}]})
    assert rules_file.read_text(encoding="utf-8") == once


def test_a_hand_placed_managed_section_is_lifted_not_duplicated(tmp_path):
    """Someone will write `exceptions:` by hand above the marker. The write has
    to move it, not produce a second top-level key with the same name."""
    path = tmp_path / "rules.yaml"
    path.write_text(
        "language: python\n"
        "exceptions:\n"
        "  - key: V-DEADBEEF\n"
        "    reason: written by hand\n"
        "source: src\n"
        "rules: []\n",
        encoding="utf-8",
    )
    write_sections(path, {"exceptions": [{"key": "V-1A2B3C4D"}]})

    text = path.read_text(encoding="utf-8")
    assert text.count("exceptions:") == 1
    doc = load_document(path)  # would raise on a duplicate key
    assert doc["exceptions"] == [{"key": "V-1A2B3C4D"}]
    assert doc["language"] == "python" and doc["source"] == "src"


def test_writing_a_file_that_does_not_exist_yet_creates_it(tmp_path):
    path = tmp_path / "nested" / "rules.yaml"
    write_sections(path, {"locks": [{"target": "a.B", "digest": "d"}]})
    assert read_section(path, "locks") == [{"target": "a.B", "digest": "d"}]


def test_refuses_to_write_a_section_it_does_not_own(rules_file):
    """A typo must not let the writer clobber the hand-written `rules:` list."""
    with pytest.raises(RulesFileError, match="non-managed"):
        write_sections(rules_file, {"rules": []})
    assert MANAGED_KEYS == ("exceptions", "locks")


def test_invalid_yaml_is_reported_against_the_file(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("rules: [\n", encoding="utf-8")
    with pytest.raises(RulesFileError, match="not valid YAML"):
        load_document(path)


def test_a_missing_file_reads_as_empty(tmp_path):
    assert load_document(tmp_path / "absent.yaml") == {}
    assert read_section(tmp_path / "absent.yaml", "locks") is None


# ---------------------------------------------------------------------------
# Settings and rules read out of the same file
# ---------------------------------------------------------------------------

def test_settings_and_rules_load_from_one_file(rules_file):
    config_dir = rules_file.parent
    cfg = load_project_config(config_dir)
    assert cfg.language == "python"
    assert cfg.source == (config_dir.parent / "src").resolve()
    assert cfg.reference_path == config_dir / "reference.xmi"
    assert [r.rule_id for r in load_rules(config_dir).rules] == ["domain-is-pure"]


def test_a_missing_rules_file_says_how_to_create_one(tmp_path):
    with pytest.raises(ConfigError, match="cdec init"):
        load_project_config(tmp_path)


def test_legacy_config_yaml_still_supplies_the_settings(tmp_path):
    """An un-migrated project keeps working; it is told, not broken."""
    config_dir = tmp_path / ".cdec"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "language: csharp\nsource: src\nbaseline:\n  reference: .cdec/ref.xmi\n",
        encoding="utf-8",
    )
    (config_dir / "rules.yaml").write_text("rules: []\n", encoding="utf-8")

    cfg = load_project_config(config_dir)
    assert cfg.language == "csharp"
    assert cfg.reference_path == (tmp_path / ".cdec" / "ref.xmi").resolve()


def test_rules_yaml_settings_win_over_the_legacy_file(tmp_path):
    config_dir = tmp_path / ".cdec"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text(
        "language: csharp\nsource: old\n", encoding="utf-8"
    )
    (config_dir / "rules.yaml").write_text(
        "language: python\nsource: new\nrules: []\n", encoding="utf-8"
    )
    cfg = load_project_config(config_dir)
    assert cfg.language == "python"
    assert cfg.source.name == "new"


# ---------------------------------------------------------------------------
# The two ledgers
# ---------------------------------------------------------------------------

def test_exceptions_round_trip_through_rules_yaml(rules_file):
    config_dir = rules_file.parent
    store = load_waivers(config_dir)
    store.add(
        Waiver(
            engine="check",
            rule="domain-is-pure",
            qualified_name="app.domain.Order",
            detail="->app.ui.View",
            reason="legacy, ARCH-42",
        )
    )
    save_waivers(config_dir, store)

    reloaded = load_waivers(config_dir)
    assert [w.qualified_name for w in reloaded.waivers] == ["app.domain.Order"]
    assert reloaded.waivers[0].reason == "legacy, ARCH-42"
    # …and the rules are untouched.
    assert load_rules(config_dir).rules[0].rule_id == "domain-is-pure"


def test_a_legacy_baseline_yaml_still_loads(tmp_path):
    """The key is derived from the tuple, so an old ledger needs no migration."""
    config_dir = tmp_path / ".cdec"
    config_dir.mkdir()
    (config_dir / "rules.yaml").write_text(
        "language: python\nsource: src\nrules: []\n", encoding="utf-8"
    )
    (config_dir / "baseline.yaml").write_text(
        "violations:\n"
        "  no-new-classes:\n"
        "    - qualified_name: animals.Cat\n"
        "      reason: legacy\n"
        "findings:\n"
        "  no-instantiation:\n"
        "    - qualified_name: app.Ledger\n"
        "      detail: settle->Invoice\n",
        encoding="utf-8",
    )
    store = load_waivers(config_dir)
    assert store.matches("check", "no-new-classes", "animals.Cat")
    assert store.matches("enforce", "no-instantiation", "app.Ledger", "settle->Invoice")


def test_locks_round_trip_through_rules_yaml(rules_file):
    config_dir = rules_file.parent
    entry = LockEntry(
        target="orders.Receipt.formatted",
        kind="method",
        digest="deadbeef",
        algo="py-ast/1",
        reason="contractual wording",
    )
    written = write_locks(config_dir, [entry])
    assert written == rules_file

    reloaded = load_locks(config_dir)
    assert reloaded["orders.Receipt.formatted"].digest == "deadbeef"
    assert reloaded["orders.Receipt.formatted"].reason == "contractual wording"
    assert load_rules(config_dir).rules[0].rule_id == "domain-is-pure"


def test_a_legacy_locks_yaml_still_loads(tmp_path):
    config_dir = tmp_path / ".cdec"
    config_dir.mkdir()
    (config_dir / "rules.yaml").write_text("rules: []\n", encoding="utf-8")
    (config_dir / "locks.yaml").write_text(
        "version: 1\nlocks:\n- target: a.B.c\n  kind: method\n"
        "  algo: py-ast/1\n  digest: abc123\n",
        encoding="utf-8",
    )
    assert load_locks(config_dir)["a.B.c"].digest == "abc123"


def test_rules_yaml_wins_over_a_leftover_locks_yaml(tmp_path):
    """After migrating, a stale locks.yaml must not resurrect a released lock."""
    config_dir = tmp_path / ".cdec"
    config_dir.mkdir()
    (config_dir / "locks.yaml").write_text(
        "locks:\n- target: released.Thing\n  kind: method\n"
        "  algo: py-ast/1\n  digest: old\n",
        encoding="utf-8",
    )
    write_locks(
        config_dir,
        [LockEntry(target="kept.Thing", kind="method", digest="new", algo="py-ast/1")],
    )
    entries = load_locks(config_dir)
    assert set(entries) == {"kept.Thing"}


def test_the_ledgers_share_the_file_without_colliding(rules_file):
    """Two engines write the same file; neither may drop the other's section."""
    config_dir = rules_file.parent
    store = load_waivers(config_dir)
    store.add(Waiver(engine="check", rule="r", qualified_name="a.B"))
    save_waivers(config_dir, store)
    write_locks(
        config_dir,
        [LockEntry(target="a.B.c", kind="method", digest="d", algo="py-ast/1")],
    )
    save_waivers(config_dir, load_waivers(config_dir))

    doc = yaml.safe_load(rules_file.read_text(encoding="utf-8"))
    assert doc["exceptions"] and doc["locks"] and doc["rules"]



# ---------------------------------------------------------------------------
# `.cdec/rules/` — the second layout, and why the two never mix
# ---------------------------------------------------------------------------

SETTINGS_ONLY = "language: python\nsource: src\n"

DANGLING = (
    "rules:\n"
    "  - id: no-dangling\n"
    "    type: dangling-classes\n"
    "    severity: error\n"
)

FANOUT = (
    "rules:\n"
    "  - id: fanout\n"
    "    type: max-class-fanout\n"
    "    severity: warning\n"
    "    limit: 5\n"
)


def _folder_file(config_dir: Path, name: str, body: str) -> Path:
    folder = config_dir / "rules"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(body, encoding="utf-8")
    return path


def _drop_rules_list(config_dir: Path) -> None:
    """Leave rules.yaml holding the settings only — the folder layout."""
    (config_dir / "rules.yaml").write_text(SETTINGS_ONLY, encoding="utf-8")


def test_a_project_with_only_rules_yaml_still_works(rules_file):
    """The original layout is untouched: no folder, no change."""
    assert [r.rule_id for r in load_rules(rules_file.parent).rules] == ["domain-is-pure"]


def test_the_folder_is_the_other_layout(rules_file):
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "b_fanout.yaml", FANOUT)
    _folder_file(config_dir, "a_dangling.yml", DANGLING)

    # Name order, so the report reads the same on every machine. The settings
    # still come from rules.yaml.
    assert [r.rule_id for r in load_rules(config_dir).rules] == ["no-dangling", "fanout"]
    assert load_project_config(config_dir).language == "python"


def test_rules_in_both_places_are_refused(rules_file):
    """Two populated layouts have no answer to "which rules apply".

    Picking one would silently drop the other set of laws, which is the one
    failure mode a gate must never have.
    """
    config_dir = rules_file.parent
    _folder_file(config_dir, "shape.yaml", DANGLING)
    with pytest.raises(ConfigError) as exc:
        load_rules(config_dir)
    # The message names both places and says how to resolve it.
    assert "two places" in str(exc.value)
    assert "shape.yaml" in str(exc.value)
    assert "rules.yaml" in str(exc.value)


def test_an_empty_rules_list_is_not_a_second_layout(rules_file):
    """`cdec init` scaffolds `rules: []`; adding a folder file must just work."""
    config_dir = rules_file.parent
    (config_dir / "rules.yaml").write_text(SETTINGS_ONLY + "rules: []\n", encoding="utf-8")
    _folder_file(config_dir, "shape.yaml", DANGLING)
    assert [r.rule_id for r in load_rules(config_dir).rules] == ["no-dangling"]


def test_an_empty_folder_leaves_rules_yaml_in_charge(rules_file):
    """`cdec init` scaffolds the folder empty, and a README is just as likely."""
    config_dir = rules_file.parent
    _folder_file(config_dir, ".gitkeep", "")
    _folder_file(config_dir, "README.md", "# how we split our rules\n")
    assert [r.rule_id for r in load_rules(config_dir).rules] == ["domain-is-pure"]


def test_a_subset_runs_only_the_named_files(rules_file):
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "dangling.yaml", DANGLING)
    _folder_file(config_dir, "fanout.yaml", FANOUT)

    # The name resolves with or without the extension, and order follows the
    # selection.
    assert [r.rule_id for r in load_rules(config_dir, ["dangling"]).rules] == ["no-dangling"]
    assert [r.rule_id for r in load_rules(config_dir, ["fanout.yaml"]).rules] == ["fanout"]
    assert [r.rule_id for r in load_rules(config_dir, ["fanout", "dangling"]).rules] == [
        "fanout",
        "no-dangling",
    ]


def test_a_subset_of_one_is_allowed_in_the_single_file_layout(rules_file):
    """`-R rules.yaml` is a no-op there, not an error — scripts stay uniform."""
    assert [r.rule_id for r in load_rules(rules_file.parent, ["rules.yaml"]).rules] == [
        "domain-is-pure"
    ]


def test_an_unknown_rules_file_lists_the_real_ones(rules_file):
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "dangling.yaml", DANGLING)
    with pytest.raises(ConfigError, match="dangling.yaml"):
        load_rules(config_dir, ["typo"])


def test_rules_yaml_is_not_selectable_in_the_folder_layout(rules_file):
    """It holds no rules there, so naming it would silently check nothing."""
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "dangling.yaml", DANGLING)
    with pytest.raises(ConfigError, match="no rule file named"):
        load_rules(config_dir, ["rules.yaml"])


def test_a_file_without_a_rules_list_is_rejected(rules_file):
    """A folder file that is not a rule document must say so.

    Loading nothing out of it would look exactly like a clean run.
    """
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "notes.yaml", "# just a note\nfoo: bar\n")
    with pytest.raises(ConfigError, match="needs a top-level 'rules:' list"):
        load_rules(config_dir)


def test_settings_in_a_folder_file_are_rejected(rules_file):
    """Settings and the managed sections belong to rules.yaml only.

    The tool writes `exceptions:` and `locks:` into rules.yaml, so honouring
    them here would be a promise the writer does not keep.
    """
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "extra.yaml", DANGLING + "language: csharp\n")
    with pytest.raises(ConfigError, match="only 'rules:' is allowed"):
        load_rules(config_dir)

    _folder_file(config_dir, "extra.yaml", DANGLING + "exceptions: []\n")
    with pytest.raises(ConfigError, match="only 'rules:' is allowed"):
        load_rules(config_dir)


def test_a_duplicate_id_across_files_is_rejected(rules_file):
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "one.yaml", DANGLING)
    _folder_file(config_dir, "two.yaml", DANGLING)
    with pytest.raises(ConfigError, match="duplicate rule id"):
        load_rules(config_dir)


def test_exceptions_still_land_in_rules_yaml_in_the_folder_layout(rules_file):
    """The tool writes one file, whichever layout the rules use."""
    config_dir = rules_file.parent
    _drop_rules_list(config_dir)
    _folder_file(config_dir, "shape.yaml", DANGLING)

    store = load_waivers(config_dir)
    store.add(Waiver(engine="check", rule="no-dangling", qualified_name="app.Thing",
                     detail="", reason="agreed"))
    save_waivers(config_dir, store)

    assert read_section(config_dir / "rules.yaml", "exceptions")
    assert not (config_dir / "rules" / "shape.yaml").read_text(
        encoding="utf-8"
    ).count("exceptions")
