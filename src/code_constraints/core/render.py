"""Render DOT text to SVG via the Graphviz `dot` subprocess.

Resolution order for the `dot` binary:
1. Environment variable `CDEC_DOT_BIN`
2. `dot` (or `dot.exe`) on `$PATH`
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

CACHE_DIR_NAME = ".cdec_cache"


class GraphvizNotFound(RuntimeError):
    pass


def render_svg(dot_text: str, *, cache_dir: Path | None = None) -> bytes:
    """Render `dot_text` to SVG bytes. Uses an on-disk cache keyed by SHA256."""
    cached: Path | None = None
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(dot_text.encode("utf-8")).hexdigest()
        cached = cache_dir / f"{key}.svg"
        if cached.exists():
            return cached.read_bytes()

    cmd = _resolve_command()
    proc = subprocess.run(
        cmd,
        input=dot_text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"dot failed (exit {proc.returncode}): {proc.stderr.decode('utf-8', 'replace')}"
        )
    svg = proc.stdout
    if cached is not None:
        cached.write_bytes(svg)
    return svg


def _resolve_command() -> list[str]:
    env = os.environ.get("CDEC_DOT_BIN")
    if env and Path(env).exists():
        return [env, "-Tsvg"]
    on_path = shutil.which("dot")
    if on_path:
        return [on_path, "-Tsvg"]
    raise GraphvizNotFound(
        "Graphviz `dot` not found. Install Graphviz (https://graphviz.org/download/) "
        "or set $CDEC_DOT_BIN to the binary path."
    )
