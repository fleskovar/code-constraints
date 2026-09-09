"""Architectural-lint engine for `cdec check`.

Reads rule definitions from a project-root `.cdec/` folder, runs them against
the current `Project` (optionally diffed against a reference), and emits a
report. Designed to gate CI on rule violations.
"""

from code_constraints.lint.engine import run_checks  # noqa: F401
from code_constraints.lint.report import Report  # noqa: F401
from code_constraints.lint.rules.base import Severity, Violation  # noqa: F401
