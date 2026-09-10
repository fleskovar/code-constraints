"""Check that the built distributions are complete before they are published.

A wheel that is missing the web UI still installs and still serves the API, so
nothing fails until a user opens `/` and gets a JSON placeholder. PyPI does not
allow re-uploading a version, so that mistake is permanent. This script turns it
into a failed build.

Run from the repository root, after `python -m build`:

    python .github/scripts/verify_dist.py
"""

from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path

STATIC = "code_constraints/web/_static"
SHIMS = "code_constraints/cli/_assets/shims"

problems: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def ok(msg: str) -> None:
    notes.append(msg)


def find_one(pattern: str) -> Path | None:
    matches = sorted(Path("dist").glob(pattern))
    if not matches:
        fail(f"no {pattern} in dist/")
        return None
    if len(matches) > 1:
        fail(f"expected one {pattern} in dist/, found {len(matches)}: "
             f"{[m.name for m in matches]} — stale artifacts would be published too")
        return None
    return matches[0]


wheel = find_one("*.whl")
sdist = find_one("*.tar.gz")

if wheel is not None:
    names = set(zipfile.ZipFile(wheel).namelist())
    z = zipfile.ZipFile(wheel)

    index = f"{STATIC}/index.html"
    if index not in names:
        fail(f"{wheel.name}: no {index} — the web UI was not built or not embedded. "
             f"Run `npm run build` in frontend/, then `make frontend-embed`.")
    else:
        html = z.read(index).decode("utf-8")

        # Every asset the page asks for must actually be in the wheel, or the
        # app loads to a blank screen.
        refs = [r for r in re.findall(r'(?:src|href)="([^"]+)"', html) if r.startswith("/")]
        if not refs:
            fail(f"{wheel.name}: index.html references no local assets — suspect build output")
        for ref in refs:
            member = STATIC + ref
            if member not in names:
                fail(f"{wheel.name}: index.html references {ref}, which is not in the wheel")
        ok(f"web UI present, {len(refs)} referenced asset(s) all resolve")

        # A dev-server entry point would 'work' locally and break for users.
        for marker in ("/@vite/client", "/src/main", "__vite_ping"):
            if marker in html:
                fail(f"{wheel.name}: index.html contains {marker!r} — this is a dev build, "
                     f"not a production bundle")

        js = [n for n in names if n.startswith(f"{STATIC}/assets/") and n.endswith(".js")]
        if not js:
            fail(f"{wheel.name}: no JS bundle under {STATIC}/assets/")
        else:
            ok(f"JS bundle: {', '.join(Path(n).name for n in sorted(js))}")

    shims = sorted(n for n in names if n.startswith(SHIMS))
    if len(shims) != 5:
        fail(f"{wheel.name}: expected 5 rule shims under {SHIMS}, found {len(shims)}: {shims}")
    else:
        ok("all 5 rule shims present")

    # These were removed with the Graphviz dependency; catch an accidental revival.
    for gone in ("code_constraints/core/dot.py", "code_constraints/core/render.py"):
        if gone in names:
            fail(f"{wheel.name}: {gone} is back — the project must not depend on Graphviz")

if sdist is not None:
    sdist_names = set(tarfile.open(sdist).getnames())
    # `python -m build` builds the wheel FROM the sdist, so the embedded UI has
    # to travel in the sdist or the wheel above was a lucky local build.
    if not any(f"/src/{STATIC}/index.html" in n for n in sdist_names):
        fail(f"{sdist.name}: the embedded web UI is missing from the sdist, so a wheel "
             f"built from this sdist would have no UI")
    else:
        ok("sdist carries the embedded web UI")

for line in notes:
    print(f"  ok    {line}")
for line in problems:
    print(f"  FAIL  {line}", file=sys.stderr)

if problems:
    print(f"\n{len(problems)} packaging problem(s) — refusing to publish.", file=sys.stderr)
    sys.exit(1)

print("\nDistributions look complete.")
