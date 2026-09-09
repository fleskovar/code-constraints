"""Runner for the human-readable case folders under `tests/cases/`.

A case folder is a self-contained, hand-solvable proof of one constraint in one
language. The whole contract is on disk:

    tests/cases/<engine>/<rule-id>/<language>/<case-name>/
        inputs/
            case.yaml       which engine + language to run (the ambient inputs,
                            written down so they are not ambient)
            src/            the source tree under test  (required)
            baseline/       the "agreed" source tree    (optional)
            rules.yaml      .cdec/rules.yaml body       (Engine A only)
        outputs/
            <engine>.json   the expected findings, canonicalised
        README.md           the walkthrough: why every element is there, and how
                            a reader gets from inputs/ to outputs/ by hand

Adding a case is adding a folder — no test file is edited. `test_case_folders.py`
discovers them from disk and parametrises one test per folder.

Design notes worth keeping:

* **Baselines carry no messages, files or line numbers.** A `message:` in
  `rules.yaml` is prose that gets rewritten; a file path is a Windows/POSIX
  hazard; a line number moves when someone adds a comment. What the baseline
  pins is the *identity* of each finding — which rule fired on which element —
  which is exactly what a reader derives by hand from the README.
* **The lock ledger is derived, never committed.** `inputs/baseline/` is the
  source as it stood when the lock was approved; the runner digests it to build
  the ledger, then verifies `inputs/src/` against that. So a case folder never
  contains an opaque sha256 that no human can check, and a fingerprinter change
  shows up as a real diff rather than as a stale digest.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CASES_ROOT = Path(__file__).parent / "cases"

#: Set `UPDATE_BASELINES=1` to rewrite every `outputs/*.json` from the current
#: behaviour. The result is a diff a human reads line by line before committing —
#: never a way to make a red build green.
UPDATE_ENV = "UPDATE_BASELINES"

#: engine id -> the baseline filename it writes into `outputs/`.
OUTPUT_FILE = {
    "check": "violations.json",
    "enforce": "findings.json",
    "lock": "lock_violations.json",
    "reference": "deviations.json",
}


class CaseError(RuntimeError):
    """The case folder itself is malformed — a broken test, not a failing one."""


@dataclass(frozen=True)
class Case:
    """One case folder, addressed the way a reader addresses it."""

    root: Path

    @property
    def name(self) -> str:
        """`check/subclass-naming/python/notifier-suffix` — the id used by
        `make test-case CASE=...` and by the pytest node name."""
        return self.root.relative_to(CASES_ROOT).as_posix()

    @property
    def inputs(self) -> Path:
        return self.root / "inputs"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    @property
    def src(self) -> Path:
        return self.inputs / "src"

    @property
    def baseline(self) -> Path | None:
        path = self.inputs / "baseline"
        return path if path.is_dir() else None

    @property
    def manifest(self) -> dict[str, Any]:
        path = self.inputs / "case.yaml"
        if not path.is_file():
            raise CaseError(f"{self.name}: missing inputs/case.yaml")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise CaseError(f"{self.name}: inputs/case.yaml must be a mapping")
        return raw

    @property
    def engine(self) -> str:
        engine = self.manifest.get("engine")
        if engine not in OUTPUT_FILE:
            raise CaseError(
                f"{self.name}: case.yaml 'engine' must be one of "
                f"{', '.join(sorted(OUTPUT_FILE))}; got {engine!r}"
            )
        return str(engine)

    @property
    def language(self) -> str:
        lang = self.manifest.get("language")
        if not lang:
            raise CaseError(f"{self.name}: case.yaml 'language' is required")
        return str(lang)

    @property
    def baseline_file(self) -> Path:
        return self.outputs / OUTPUT_FILE[self.engine]


def discover_cases(root: Path = CASES_ROOT) -> list[Case]:
    """Every folder holding an `inputs/case.yaml`, in a stable order."""
    if not root.is_dir():
        return []
    found = [Case(p.parent.parent) for p in sorted(root.rglob("inputs/case.yaml"))]
    return sorted(found, key=lambda c: c.name)


# ---------------------------------------------------------------- engines


def run_case(case: Case) -> list[dict[str, Any]]:
    """Run the case's engine over `inputs/` and return the canonical findings."""
    if not case.src.is_dir():
        raise CaseError(f"{case.name}: missing inputs/src/")
    engine = case.engine
    if engine == "check":
        return _run_check(case)
    if engine == "enforce":
        return _run_enforce(case)
    if engine == "lock":
        return _run_lock(case)
    return _run_reference(case)


def _parse(case: Case, path: Path):
    from code_constraints.lint.pipeline import parse_source

    return parse_source(path, case.language)


def _run_check(case: Case) -> list[dict[str, Any]]:
    """Engine A — `cdec check`. Diff-scope rules need `inputs/baseline/`."""
    from code_constraints.core.diff import diff_projects
    from code_constraints.lint.config import load_rules
    from code_constraints.lint.engine import run_checks

    if not (case.inputs / "rules.yaml").is_file():
        raise CaseError(f"{case.name}: Engine A cases need inputs/rules.yaml")

    head = _parse(case, case.src)
    baseline_dir = case.baseline
    if baseline_dir is not None:
        base = _parse(case, baseline_dir)
        project, has_diff = diff_projects(base, head), True
    else:
        base, project, has_diff = None, head, False

    rules = load_rules(case.inputs).rules
    report = run_checks(project, rules, has_diff=has_diff, baseline_project=base)
    return sorted(
        (
            {
                "rule": v.rule_id,
                "severity": v.severity.value,
                "element": v.qualified_name,
                **({"member": v.signature} if v.signature else {}),
            }
            for v in report.violations
        ),
        key=lambda d: (d["rule"], d["element"], d.get("member", "")),
    )


def _run_enforce(case: Case) -> list[dict[str, Any]]:
    """Engine B — `cdec enforce`. Bodies only; no baseline, ever."""
    from code_constraints.enforce.engine import enforce

    return sorted(
        (
            {"rule": f.rule, "element": f.qualified_name, "detail": f.detail}
            for f in enforce(case.src, case.language)
        ),
        key=lambda d: (d["rule"], d["element"], d["detail"]),
    )


def _run_lock(case: Case) -> list[dict[str, Any]]:
    """Engine C — `cdec lock check`.

    The ledger is built by digesting `inputs/baseline/` (the approved source),
    then `inputs/src/` is verified against it. With no `baseline/` the ledger is
    empty, which is how a `missing` violation is staged.
    """
    from code_constraints.lock.engine import LockOptions, check_locks, update_locks

    manifest = case.manifest
    options = LockOptions(
        include_docstrings=bool(manifest.get("include_docstrings", False)),
        patterns=[str(t) for t in manifest.get("targets", [])],
    )

    entries: dict[str, Any] = {}
    baseline_dir = case.baseline
    if baseline_dir is not None:
        entries, _ = update_locks(baseline_dir, case.language, {}, options)

    report = check_locks(case.src, case.language, entries, options)
    return sorted(
        ({"kind": v.kind, "target": v.target} for v in report.violations),
        key=lambda d: (d["kind"], d["target"]),
    )


def _run_reference(case: Case) -> list[dict[str, Any]]:
    """Engine D — `cdec reference test`. `inputs/baseline/` is the reference."""
    from code_constraints.reference.compare import compare_to_reference

    baseline_dir = case.baseline
    if baseline_dir is None:
        raise CaseError(
            f"{case.name}: the reference gate needs inputs/baseline/ "
            f"(the committed shape) to compare against"
        )
    deviations = compare_to_reference(_parse(case, baseline_dir), _parse(case, case.src))
    return sorted(
        (
            {
                "category": d.category,
                "element": d.qualified_name,
                **({"member": d.member} if d.member else {}),
            }
            for d in deviations
        ),
        key=lambda d: (d["element"], d.get("member", ""), d["category"]),
    )


# ---------------------------------------------------------------- baselines


def load_baseline(case: Case) -> list[dict[str, Any]]:
    path = case.baseline_file
    if not path.is_file():
        raise CaseError(
            f"{case.name}: missing {path.relative_to(case.root).as_posix()}. "
            f"A case with no baseline cannot fail; derive one by hand, or "
            f"regenerate with {UPDATE_ENV}=1 and review every line."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def write_baseline(case: Case, findings: list[dict[str, Any]]) -> None:
    case.outputs.mkdir(parents=True, exist_ok=True)
    case.baseline_file.write_text(
        json.dumps(findings, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def updating() -> bool:
    return os.environ.get(UPDATE_ENV, "") not in ("", "0", "false", "False")
