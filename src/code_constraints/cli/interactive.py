"""The modern interactive `cdec` session.

Launched when `cdec` is run with no subcommand. Detects whether the current
folder is an initialized harness project (presence of `.cdec/`), walks the user
through onboarding if not, then offers a menu of the common actions.

Built on `rich` (styled output) + `questionary` (arrow-key prompts). All the
real work lives in `code_constraints.cli.scaffold` and the existing subcommands; this module
is purely the conversational shell.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from shutil import which
from urllib.parse import quote

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from code_constraints.cli.detect import detect_language
from code_constraints.cli.scaffold import (
    SUPPORTED_LANGS,
    ScaffoldError,
    copy_agents,
    copy_shims,
    has_shim,
    init_cdec_config,
    write_ci_scripts,
)

console = Console()


def run_interactive(path: Path) -> None:
    """Entry point for a bare `cdec` invocation rooted at `path`."""
    if not sys.stdin.isatty():
        console.print(
            "[yellow]cdec[/] needs an interactive terminal. "
            "Run a subcommand instead, e.g. [bold]cdec --help[/], "
            "[bold]cdec serve parse .[/], or [bold]cdec check[/]."
        )
        return

    _banner(path)

    cdec_dir = path / ".cdec"
    if not cdec_dir.is_dir():
        if not _onboard(path):
            return  # user bailed out of onboarding
    else:
        console.print(
            f"[green]✓[/] Found an initialized project at [bold]{path}[/] "
            "([dim].cdec/ present[/])."
        )

    _main_menu(path)


# ---------- presentation ----------

def _banner(path: Path) -> None:
    title = Text("code-constraints", style="bold cyan")
    body = Text.assemble(
        ("Interactive session\n", "dim"),
        ("Working directory: ", "dim"),
        (str(path), "bold"),
    )
    console.print(Panel(body, title=title, border_style="cyan", expand=False))


def _ask_language(path: Path) -> str | None:
    detected = detect_language(path)
    if detected:
        console.print(f"[dim]Detected language:[/] [bold]{detected}[/]")
    choice = questionary.select(
        "Which language is this project?",
        choices=list(SUPPORTED_LANGS),
        default=detected if detected in SUPPORTED_LANGS else None,
    ).ask()
    return choice  # None if the user cancels (Ctrl+C)


# ---------- onboarding ----------

def _onboard(path: Path) -> bool:
    """Walk the user through first-time setup. Returns True to continue to the
    menu, False if the user cancelled out entirely."""
    console.print(
        "\n[bold]This folder isn't a code-constraints project yet.[/] "
        "Let's get it set up.\n"
    )
    if not questionary.confirm("Initialize a code-constraints project here?", default=True).ask():
        console.print("[yellow]Skipped setup.[/] Run [bold]cdec[/] again when ready.")
        return False

    lang = _ask_language(path)
    if lang is None:
        return False

    # 1. Scaffold .cdec/
    try:
        written = init_cdec_config(path / ".cdec", lang, Path("."), force=False)
    except ScaffoldError as exc:
        console.print(f"[red]Could not scaffold .cdec/:[/] {exc}")
        return False
    console.print(f"[green]✓[/] Scaffolded [bold].cdec/[/] ({len(written)} files).")

    # 2. Claude agents
    if questionary.confirm(
        "Copy code-constraints Claude agents into .claude/agents/?", default=True
    ).ask():
        _try_copy_agents(path, force=False)

    # 3. Shims
    if has_shim(lang):
        if questionary.confirm(
            f"Copy the {lang} rule shims into the project?", default=True
        ).ask():
            _try_copy_shims(path, lang, force=False)
    else:
        console.print(f"[dim]No rule shims available for {lang} yet — skipping.[/]")

    console.print("\n[green bold]Setup complete![/]\n")
    return True


# ---------- main menu ----------

_LAUNCH = "🌐  Launch the web app (interactive diagrams)"
_CHECKS = "🔍  Run the architectural checks (cdec check)"
_TESTS = "🧪  Run the project test suite"
_CI = "📦  Generate CI/CD scripts (Windows + Linux)"
_UPDATE = "🔄  Update project assets (agents, shims)"
_EXIT = "❌  Exit"


def _main_menu(path: Path) -> None:
    lang = _resolve_language(path)
    while True:
        action = questionary.select(
            "What would you like to do?",
            choices=[_LAUNCH, _CHECKS, _TESTS, _CI, _UPDATE, _EXIT],
        ).ask()

        if action is None or action == _EXIT:
            console.print("[dim]Bye.[/]")
            return

        try:
            if action == _LAUNCH:
                _launch_web(path, lang)
            elif action == _CHECKS:
                _run_checks(path, lang)
            elif action == _TESTS:
                _run_tests(path, lang)
            elif action == _CI:
                _generate_ci(path, lang)
            elif action == _UPDATE:
                _update_assets(path, lang)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted — back to the menu.[/]")
        except Exception as exc:  # keep the session alive on any action failure
            console.print(f"[red]Action failed:[/] {exc}")

        console.print()  # spacer before the menu repeats


def _resolve_language(path: Path) -> str:
    """Prefer the language recorded in .cdec/rules.yaml, fall back to detection,
    then to 'python'."""
    try:
        from code_constraints.lint.config import load_project_config

        return load_project_config(path / ".cdec").language
    except Exception:
        return detect_language(path) or "python"


# ---------- actions ----------

def _launch_web(path: Path, lang: str) -> None:
    host, port = "127.0.0.1", 8765
    url = f"http://{host}:{port}/?path={quote(str(path.resolve()))}&lang={lang}"
    console.print(
        f"[green]Starting the web app[/] at [bold]{url}[/]\n"
        "[dim]Press Ctrl+C to stop and return to the menu.[/]"
    )
    from code_constraints.cli.__main__ import _run_server

    try:
        _run_server(host, port, open_url=url)
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/]")


def _run_checks(path: Path, lang: str) -> None:
    """One command, every rule. `cdec check` is the whole gate."""
    console.print("[bold]Running the architectural checks…[/]")
    _run(
        [sys.executable, "-m", "code_constraints.cli", "check", "--config", ".cdec", "--source", "."],
        path,
    )
    console.print(
        "\n[dim]To accept a reported issue, quote its key: "
        "[bold]cdec exceptions allow V-XXXXXXXX --reason \"why\"[/]. "
        "For a batch: [bold]cdec check --log-out check.log[/], mark lines [ALLOW], "
        "[bold]cdec exceptions patch --file check.log[/].\n"
        "To grandfather everything on an existing codebase: "
        "[bold]cdec check --automatic-exceptions rules[/].[/]"
    )


def _run_tests(path: Path, lang: str) -> None:
    if lang in ("python",):
        console.print("[bold]Running pytest…[/]")
        _run([sys.executable, "-m", "pytest"], path)
    elif lang == "csharp":
        if which("dotnet") is None:
            console.print("[yellow]`dotnet` not found on PATH — cannot run C# tests.[/]")
            return
        console.print("[bold]Running dotnet test…[/]")
        _run(["dotnet", "test"], path)
    else:
        # typescript / svelte: lean on npm if a package.json is present.
        if (path / "package.json").is_file() and which("npm") is not None:
            console.print("[bold]Running npm test…[/]")
            _run(["npm", "test"], path)
        else:
            console.print(
                f"[yellow]No known test runner for {lang} in this folder "
                "(looked for package.json + npm).[/]"
            )


def _generate_ci(path: Path, lang: str) -> None:
    written = write_ci_scripts(path, lang, Path("."))
    for p in written:
        console.print(f"[green]✓[/] wrote [bold]{p.name}[/]")
    console.print(
        "[dim]Both scripts run `cdec check` and exit non-zero on any violation "
        "— drop them into your CI pipeline.[/]"
    )


def _update_assets(path: Path, lang: str) -> None:
    """Update (or install) Claude agents and shims from the currently-installed
    code-constraints version. Safe to run after upgrading — overwrites only the
    harness-owned files, never your .cdec/ config or source code."""
    console.print(
        "[dim]Updates Claude agents and language shims to the version bundled "
        "with this installation. Run after upgrading code-constraints.[/]\n"
    )

    agents_dest = path / ".claude" / "agents"
    agents_exist = agents_dest.is_dir() and any(agents_dest.iterdir())
    agents_label = "Update" if agents_exist else "Install"
    if questionary.confirm(
        f"{agents_label} code-constraints Claude agents in .claude/agents/?", default=True
    ).ask():
        _try_copy_agents(path, force=True)

    if has_shim(lang):
        shim_exists = (path / "cdec_rules.py").is_file() or (path / "CodeConstraintsRules.cs").is_file()
        shim_label = "Update" if shim_exists else "Install"
        if questionary.confirm(
            f"{shim_label} the {lang} rule shims?", default=True
        ).ask():
            _try_copy_shims(path, lang, force=True)
    else:
        console.print(f"[dim]No rule shims for {lang} — skipping.[/]")


# ---------- copy wrappers (shared by onboarding + recopy) ----------

def _try_copy_agents(path: Path, force: bool) -> None:
    try:
        dests = copy_agents(path, force=force)
        for dest in dests:
            console.print(f"[green]✓[/] Copied agent → [bold]{dest}[/]")
    except ScaffoldError as exc:
        console.print(f"[yellow]Agents not copied:[/] {exc}")


def _try_copy_shims(path: Path, lang: str, force: bool) -> None:
    try:
        dests = copy_shims(path, lang, force=force)
        for dest in dests:
            console.print(f"[green]✓[/] Copied shim → [bold]{dest}[/]")
    except ScaffoldError as exc:
        console.print(f"[yellow]Shim not copied:[/] {exc}")


# ---------- subprocess helper ----------

def _run(cmd: list[str], cwd: Path) -> None:
    """Run a subprocess, streaming its output, without raising on non-zero."""
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        console.print(f"[yellow]Command exited with code {result.returncode}.[/]")
