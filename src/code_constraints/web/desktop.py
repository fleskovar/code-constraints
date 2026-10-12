"""Hand a source file to the desktop: the file manager, or an editor.

The canvas offers "Reveal in file explorer" and "Open in editor" on a class.
Both act on the machine that runs the server, so two rules hold here:

- **Never run the file.** "Open with the default application" runs a script on
  Windows when its extension is in `PATHEXT` (`.py` is, once Python is
  installed). Such a file is opened with the `edit` verb only, and the call
  fails with advice when no editor is registered for it.
- **Only a source file of the project.** `resolve_source_file` refuses a path
  that leaves the project root or that is not a file.

`web/app.py` adds the third rule: only a request from this machine may ask.

The editor is, in this order: the command in `CDEC_EDITOR`, VS Code when it
is installed, the application the desktop has for the file type.

`CDEC_EDITOR` names an editor command. `{file}` and `{line}` are replaced;
without `{file}` the path is added at the end. Example: `vim +{line} {file}`.
"""

from __future__ import annotations

import ipaddress
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

EDITOR_ENV = "CDEC_EDITOR"


class DesktopError(Exception):
    """The desktop action is refused or failed. The message is for the user."""


def is_loopback(host: str | None) -> bool:
    """True when `host` names this machine."""
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def resolve_source_file(root: Path, file: str) -> Path:
    """The absolute path of `file` (relative to the project root, as the model
    records it). Refuses a path outside the root and a path that is not a file."""
    base = root.resolve()
    if not base.is_dir():
        raise DesktopError("this diagram has no source folder on this machine")
    path = (base / file).resolve()
    if not path.is_relative_to(base):
        raise DesktopError(f"the file is outside the project: {file}")
    if not path.is_file():
        raise DesktopError(f"the file does not exist: {path}")
    return path


def _spawn(argv: list[str]) -> None:
    """Start a desktop program and do not wait for it."""
    try:
        subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise DesktopError(f"cannot start `{argv[0]}`: {exc}") from exc


def reveal(path: Path) -> None:
    """Show `path` in the file manager of the desktop, selected where the file
    manager supports that."""
    if sys.platform == "win32":
        # The switch and the path are two arguments. As one argument, a path
        # with a space is quoted together with the switch, and Explorer then
        # ignores it and opens the Documents folder.
        _spawn(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        _spawn(["open", "-R", str(path)])
    else:
        # No common "select this file" call on Linux. Open the folder.
        _spawn(["xdg-open", str(path.parent)])


def _editor_argv(command: str, path: Path, line: int | None) -> list[str]:
    """`CDEC_EDITOR` as an argument list for `path`."""
    windows = os.name == "nt"
    # POSIX rules read `\\` as an escape, which breaks a Windows path.
    parts = [p.strip('"') if windows else p for p in shlex.split(command, posix=not windows)]
    if not parts:
        raise DesktopError(f"{EDITOR_ENV} is empty")
    values = {"file": str(path), "line": str(line or 1)}
    argv = [p.replace("{file}", values["file"]).replace("{line}", values["line"]) for p in parts]
    if not any("{file}" in p for p in parts):
        argv.append(str(path))
    # `code` is `code.cmd` on Windows. Popen finds an .exe only, so resolve it.
    argv[0] = shutil.which(argv[0]) or argv[0]
    return argv


def _runs_when_opened(path: Path) -> bool:
    """True when "open" on this file runs it instead of showing it."""
    if sys.platform != "win32":
        return False
    executable = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").upper().split(";")
    return path.suffix.upper() in executable


def find_vscode() -> str | None:
    """The VS Code program, or None when VS Code is not installed.

    `code` on the PATH first, then the folders the installers use: the PATH of
    the server is not always the PATH of the user's shell.
    """
    candidates = [shutil.which("code")]
    if sys.platform == "win32":
        for var, sub in (
            ("LOCALAPPDATA", "Programs/Microsoft VS Code"),
            ("ProgramFiles", "Microsoft VS Code"),
            ("ProgramFiles(x86)", "Microsoft VS Code"),
        ):
            if os.environ.get(var):
                candidates.append(str(Path(os.environ[var]) / sub / "bin" / "code.cmd"))
    elif sys.platform == "darwin":
        candidates.append(
            "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
        )
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():
            continue
        if sys.platform == "win32":
            # `code` is a batch file there: `<install>/bin/code.cmd`. Start the
            # program next to it. A batch file goes through cmd.exe, which has
            # its own quoting rules for a path and opens a console window.
            exe = Path(candidate).parent.parent / "Code.exe"
            if exe.is_file():
                return str(exe)
        return candidate
    return None


def open_in_editor(path: Path, line: int | None = None) -> None:
    """Open `path` for editing. Never runs the file.

    The editor is the command in `CDEC_EDITOR` when it is set, else VS Code
    when it is installed (for every file type, at the line of the class), else
    the application the desktop has for the file type.
    """
    command = os.environ.get(EDITOR_ENV, "").strip()
    if command:
        _spawn(_editor_argv(command, path, line))
        return
    vscode = find_vscode()
    if vscode:
        # -g: go to file:line. VS Code uses the window that is open already.
        _spawn([vscode, "-g", f"{path}:{line or 1}"])
        return
    if sys.platform == "win32":
        runs = _runs_when_opened(path)
        try:
            # `startfile` exists on Windows only. Attribute access fails the
            # type check on every other platform, so use getattr.
            getattr(os, "startfile")(str(path), "edit" if runs else "open")  # noqa: B009
        except OSError as exc:
            if runs:
                raise DesktopError(
                    f"Windows runs a `{path.suffix}` file, it does not open it, and no "
                    f"editor is registered for it. Install VS Code, or set {EDITOR_ENV} to "
                    "the command of your editor, for example: notepad {file}"
                ) from exc
            raise DesktopError(
                f"no application is registered for `{path.suffix}` files. Install VS Code, "
                f"or set {EDITOR_ENV} to the command of your editor, for example: "
                "notepad {file}"
            ) from exc
    elif sys.platform == "darwin":
        # -t: the default text editor. Plain `open` can start Python Launcher.
        _spawn(["open", "-t", str(path)])
    else:
        _spawn(["xdg-open", str(path)])
