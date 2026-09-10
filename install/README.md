# Standalone install

These scripts install **code-constraints** as a self-contained tool. They use your existing
`git` to clone the project from GitHub, create and manage their own Python virtualenv
(installing/updating all dependencies), build the web frontend, and put the `cdec` CLI on
your PATH so it works from anywhere.

**Re-running the installer is the update path** — it pulls the latest `main`, re-syncs
dependencies whenever requirements change, and rebuilds the frontend. It is idempotent and
needs no admin/root. Once installed, `cdec update` does the same thing from the CLI without
needing the installer script.

## Prerequisites

- **git**
- **Python 3.11+**
- **Node.js 20+** and **npm** (required — the web UI is built from source)

## Install / update

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.sh | bash
```

Or from a checkout: `./install/install.sh`

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/fleskovar/code_constraints/main/install/install.ps1 | iex
```

Or from a checkout: `.\install\install.ps1`

After installing, open a **new terminal** so the PATH change takes effect, then:

```bash
cdec --help
cdec serve        # web viewer at http://127.0.0.1:8765
```

## Configuration

All optional, set as environment variables before running:

| Variable             | Default                                              | Purpose            |
| -------------------- | ---------------------------------------------------- | ------------------ |
| `CDEC_HOME`   | `~/.code-constraints` / `%LOCALAPPDATA%\code-constraints`      | install location   |
| `CDEC_REPO`   | `https://github.com/fleskovar/code_constraints.git`       | git clone URL      |
| `CDEC_BRANCH` | `main`                                               | branch to track    |

Example (Linux):

```bash
CDEC_HOME=/opt/code-constraints ./install/install.sh
```

## What gets installed where

```
$CDEC_HOME/
  repo/                 # the git checkout (updated in place on re-run)
    .venv/              # dedicated Python virtualenv
    frontend/dist/      # built web UI that `cdec serve` mounts
```

The `cdec` command points back into `repo/.venv`:
- **Windows:** `repo\.venv\Scripts` is added to your User PATH.
- **Linux/macOS:** `~/.local/bin/cdec` is symlinked to `repo/.venv/bin/cdec` (and
  `~/.local/bin` is added to PATH in your shell rc if it wasn't already).

## Uninstall

- Remove the install directory (`$CDEC_HOME`).
- **Windows:** remove the `...\repo\.venv\Scripts` entry from your User PATH
  (System Settings → Environment Variables).
- **Linux/macOS:** delete `~/.local/bin/cdec` and the
  `# added by code-constraints installer` line from your shell rc files.

> For developing **on** code-constraints itself (working in an existing clone), use the
> in-repo `scripts/bootstrap.{ps1,sh}` instead — they set up the venv and frontend without
> touching your PATH.
