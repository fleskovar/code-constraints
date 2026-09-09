"""Heuristic source-language detection for `cdec serve parse`.

When the user doesn't pass `--lang`, we guess the project's language from the
mix of file extensions in the tree. The rule (per spec):

  1. ANY `.svelte` file present  -> "svelte"  (Svelte projects also carry .ts,
     so .svelte wins over typescript).
  2. otherwise the language with the most files among python/.py,
     csharp/.cs, typescript/.ts|.tsx, odin/.odin, lua/.lua, julia/.jl.
  3. nothing recognised           -> None (the caller asks for --lang).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Directories never worth walking for language detection.
IGNORE_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        ".svelte-kit",
        "obj",
        "bin",
        "__pycache__",
        ".cdec_cache",
    }
)

# Extension -> language. `.svelte` is handled as an override, not via counting.
EXT_TO_LANG = {
    ".py": "python",
    ".cs": "csharp",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".odin": "odin",
    ".lua": "lua",
    ".jl": "julia",
}

# Deterministic tie-break order when counts are equal.
_PRIORITY = ("python", "csharp", "typescript", "odin", "lua", "julia")


def detect_language(root: Path) -> Optional[str]:
    """Return the detected language for the tree at `root`, or None."""
    counts: dict[str, int] = {}
    saw_svelte = False

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored directories in place so os.walk doesn't descend.
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext == ".svelte":
                saw_svelte = True
                continue
            lang = EXT_TO_LANG.get(ext)
            if lang is not None:
                counts[lang] = counts.get(lang, 0) + 1

    if saw_svelte:
        return "svelte"
    if not counts:
        return None
    best = max(counts.values())
    for lang in _PRIORITY:
        if counts.get(lang, 0) == best:
            return lang
    # Fallback (shouldn't happen given _PRIORITY covers EXT_TO_LANG values).
    return max(counts, key=lambda k: counts[k])
