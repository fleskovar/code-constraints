"""`cdec hcm` — hand the bundled agent configuration to hcm.

code-constraints ships an hcm bundle as package data (`cli/_assets/hcm_bundle/`):
the skills, the subagent, the command and the context section that tell a coding
agent how to work in a project gated by `cdec`. hcm (the harness config manager)
installs such a bundle into Claude Code, Copilot, OpenCode and friends.

Everything here drives the `hcm` command as a subprocess. Nothing imports hcm or
writes under `~/.hcm/`: the registry format belongs to hcm, and the user's hcm
may be a different version from the one this was written against.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

BUNDLE_NAME = "code-constraints"
# Package data, beside this module — so in an editable install it is the
# checkout, which is what makes `--dev` useful.
BUNDLE_DIR = Path(__file__).resolve().parent / "_assets" / "hcm_bundle"

HCM_HOMEPAGE = "https://github.com/fleskovar/harness_config_manager"


class HcmError(Exception):
    """Raised when hcm is missing or one of its commands fails.

    `code` is the exit status to hand back: hcm's own when it ran and failed,
    so a script wrapping `cdec hcm` sees the same answer it would from hcm.
    """

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def find_hcm() -> str:
    # `shutil.which` also resolves `hcm.cmd`, which is how npm installs it on
    # Windows and which `subprocess` cannot find by bare name without a shell.
    hcm = shutil.which("hcm")
    if hcm is None:
        raise HcmError(
            "hcm is not installed. Install it with:\n"
            "    npm install -g harness-config-manager\n"
            f"See {HCM_HOMEPAGE}"
        )
    return hcm


def _run(hcm: str, *args: str) -> None:
    """Run one hcm command, streaming its output. Raise HcmError on failure."""
    result = subprocess.run([hcm, *args], check=False)
    if result.returncode != 0:
        raise HcmError(f"`hcm {' '.join(args)}` failed.", code=result.returncode)


def registered_in_dev_mode(hcm: str) -> bool:
    """True when the registry entry reads a working copy in place (`--dev`)."""
    result = subprocess.run(
        [hcm, "registry", "list", "--json"], capture_output=True, text=True, check=False
    )
    try:
        entries = json.loads(result.stdout)
    except ValueError:
        return False
    if not isinstance(entries, list):
        return False
    return any(
        isinstance(entry, dict) and entry.get("name") == BUNDLE_NAME and bool(entry.get("dev"))
        for entry in entries
    )


def register(*, dev: bool = False, echo: Callable[[str], object] = print) -> Path:
    """Register the bundled bundle with hcm. Returns the folder registered.

    Idempotent: registering again keeps the entry's id and replaces the stored
    copy, which is also how a newer code-constraints publishes a newer bundle.
    """
    hcm = find_hcm()
    if not (BUNDLE_DIR / "hcm.yaml").is_file():
        raise HcmError(
            f"the hcm bundle is missing from this installation ({BUNDLE_DIR}). "
            "Reinstall code-constraints."
        )
    if dev and "site-packages" in BUNDLE_DIR.parts:
        # An installed copy never sees edits made in a checkout, so `--dev`
        # would register a folder nobody is editing.
        echo(
            f"warning: {BUNDLE_DIR} is an installed copy, not a working copy. "
            "Run `pip install -e .` in your checkout first."
        )
    # An absolute path on purpose: hcm reads `a/b/c` as a GitHub reference.
    _run(hcm, "registry", "add", str(BUNDLE_DIR), *(["--dev"] if dev else []))
    return BUNDLE_DIR


def update(
    extra_args: Sequence[str] = (), *, echo: Callable[[str], object] = print
) -> None:
    """Publish this installation's bundle, then update the current project.

    `extra_args` go to `hcm update` untouched (`-t`, `-s`, `--no-prompt`, …).
    """
    hcm = find_hcm()
    if registered_in_dev_mode(hcm):
        # hcm already reads the working copy in place. Registering again
        # without `--dev` would silently swap it for a stored snapshot.
        echo(f"{BUNDLE_NAME} is registered in development mode; hcm reads it in place.")
    else:
        register(echo=echo)
    _run(hcm, "update", BUNDLE_NAME, *extra_args)
