"""Dependency fingerprinting for the install/update flows.

Each heavy install step (pip install, npm install, npm run build) hashes the
files that determine its output and stores that hash in a *stamp file*. On the
next run the step is skipped when the freshly-computed hash matches the stamp —
so re-running `cdec update`, the standalone installers, or `scripts/bootstrap.*`
no longer reinstalls everything when nothing relevant has changed.

This module is intentionally pure-stdlib so it can be used two ways:

* imported by ``code_constraints.cli.update`` (``from code_constraints.cli import depstamp``), and
* run by file path from the shell installers
  (``python /path/to/depstamp.py check --stamp <file> <inputs...>``) — which
  works even before the package is pip-installed, i.e. on a first install.

A directory passed as an input is expanded to every file beneath it (sorted),
so a source tree like ``frontend/src`` produces a stable, content-addressed
hash that changes whenever any file under it is added, removed, or edited.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

# Bumped if the hashing scheme ever changes, to invalidate old stamps.
_SCHEME = "cdec-depstamp-v1"


def _iter_files(path: Path):
    """Yield the files contributing to the fingerprint for ``path``.

    A file yields itself; a directory yields every file beneath it (recursively).
    Missing paths yield nothing — a manifest that doesn't exist simply doesn't
    contribute, which keeps the hash defined even on a partial checkout.
    """
    if path.is_dir():
        yield from (p for p in sorted(path.rglob("*")) if p.is_file())
    elif path.is_file():
        yield path


def fingerprint(inputs: list[Path], *, base: Path | None = None) -> str:
    """Return a SHA256 hex digest over the contents of ``inputs``.

    The digest folds in each contributing file's path (relative to ``base`` when
    given, so the hash is stable regardless of the absolute checkout location)
    and its bytes. File order is normalised by sorting, so the result depends
    only on the set of files and their contents.
    """
    h = hashlib.sha256()
    h.update(_SCHEME.encode())

    entries: list[tuple[str, Path]] = []
    for raw in inputs:
        for f in _iter_files(raw):
            try:
                rel = f.relative_to(base) if base else f
            except ValueError:
                rel = f
            entries.append((rel.as_posix(), f))

    for rel_str, f in sorted(entries, key=lambda e: e[0]):
        h.update(rel_str.encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")

    return h.hexdigest()


def is_changed(stamp: Path, inputs: list[Path], *, base: Path | None = None) -> bool:
    """True if the step should run: stamp missing, unreadable, or hash differs."""
    if not stamp.is_file():
        return True
    try:
        previous = stamp.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    return previous != fingerprint(inputs, base=base)


def write_stamp(stamp: Path, inputs: list[Path], *, base: Path | None = None) -> None:
    """Record the current fingerprint of ``inputs`` into ``stamp``."""
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(fingerprint(inputs, base=base), encoding="utf-8")


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dependency fingerprint stamps.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("check", "write"):
        p = sub.add_parser(name)
        p.add_argument("--stamp", required=True, type=Path, help="Stamp file path.")
        p.add_argument(
            "--base",
            type=Path,
            default=None,
            help="Base dir to relativise input paths against (for stable hashing).",
        )
        p.add_argument("inputs", nargs="+", type=Path, help="Files/dirs to fingerprint.")

    args = parser.parse_args(argv)

    if args.command == "check":
        # Exit 0 = changed (run the step); exit 1 = unchanged (skip). This maps
        # onto shell `if` truthiness so callers can write `if python ... check`.
        return 0 if is_changed(args.stamp, args.inputs, base=args.base) else 1

    write_stamp(args.stamp, args.inputs, base=args.base)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
