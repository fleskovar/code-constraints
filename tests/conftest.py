"""Suite-wide test setup."""

from __future__ import annotations

import os

# Typer forces Rich terminal output when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS
# is set, even with CliRunner. The CLI text then carries ANSI escape codes, and
# an assertion such as `" ui " in result.output` fails on CI only. A dumb
# terminal gets plain text everywhere.
os.environ["TERM"] = "dumb"
