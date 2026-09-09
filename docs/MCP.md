# code-constraints as an MCP server

`cdec-mcp` exposes the three enforcement engines, the model pipeline, and the
waiver review loop over the [Model Context Protocol](https://modelcontextprotocol.io)
as a **stdio server**, so any MCP-capable coding harness can run code-constraints
as tools instead of shelling out to the CLI and parsing human output.

The tools call the library in-process, so results come back as structured JSON
and issue keys (`V-`/`F-`/`L-`) are derived by the same code path the CLI uses —
a key an agent reads from `cdec_check` is the same key `cdec baseline allow`
accepts on the command line.

## Install

```bash
pip install "code-constraints[mcp]"
```

The `[mcp]` extra pulls in the `mcp` Python SDK (>= 2.0). Installing the package
puts a `cdec-mcp` console script next to `cdec`.

Verify it starts:

```bash
cdec-mcp --help
```

## Configuration

Copy the project-root [`.mcp.json`](../.mcp.json) into whatever repo you want
constrained:

```json
{
  "mcpServers": {
    "code-constraints": {
      "type": "stdio",
      "command": "cdec-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

This shape — a `mcpServers` object keyed by server name, with
`command`/`args`/`env` — is what Claude Code, Cursor, Windsurf, Zed, Cline and
most other harnesses read. Only the *filename* differs; see the table below.

| Harness | Config file | Notes |
| --- | --- | --- |
| Claude Code | `.mcp.json` at the repo root | Committed and shared with the team. Or run `claude mcp add code-constraints -- cdec-mcp`. |
| Claude Desktop | `claude_desktop_config.json` | Same `mcpServers` shape. `cdec-mcp` must be on the GUI app's PATH — prefer the absolute-path variant below. |
| Cursor | `.cursor/mcp.json` (or `~/.cursor/mcp.json`) | Same `mcpServers` shape. |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | Same `mcpServers` shape. |
| Cline / Roo | `cline_mcp_settings.json` | Same `mcpServers` shape. |
| Zed | `settings.json` → `context_servers` | Key is `context_servers`, entry shape is the same. |
| VS Code (Copilot) | `.vscode/mcp.json` | Top-level key is `servers`, not `mcpServers`. |

VS Code's variant:

```json
{
  "servers": {
    "code-constraints": {
      "type": "stdio",
      "command": "cdec-mcp"
    }
  }
}
```

### If `cdec-mcp` isn't on PATH

A harness spawns the server as a bare subprocess, so it does **not** inherit an
activated virtualenv. When code-constraints lives in a project venv, point at
that interpreter explicitly — this is also the most reliable option for GUI apps
launched from a desktop shortcut:

```json
{
  "mcpServers": {
    "code-constraints": {
      "type": "stdio",
      "command": "C:/path/to/.venv/Scripts/python.exe",
      "args": ["-m", "code_constraints.mcp"]
    }
  }
}
```

On macOS/Linux the interpreter is `.venv/bin/python`. To keep it off PATH
entirely, `uvx --from "code-constraints[mcp]" cdec-mcp` works as the `command`
+ `args` pair too.

### Project root

Relative paths in tool arguments resolve against, in order:

1. `--project-root DIR`
2. `$CDEC_PROJECT_ROOT`
3. the process working directory — which is what most harnesses set to the open
   workspace, so usually nothing needs configuring.

Set it explicitly when one server should always target a fixed repo:

```json
{
  "mcpServers": {
    "code-constraints": {
      "type": "stdio",
      "command": "cdec-mcp",
      "args": ["--project-root", "/srv/checkouts/my-service"]
    }
  }
}
```

`--log-level DEBUG` turns on verbose logging; logs always go to stderr, never
stdout (stdout is the protocol stream).

## Tools

### Orientation

| Tool | What it does |
| --- | --- |
| `cdec_status` | How code-constraints is configured here: language, source, reference, rule count, waiver/lock ledgers. Start here. |
| `cdec_rules` | The catalogue of architectural rule tags (`@no_instantiation`, `[Sealed]`, …), their legal targets and parameters. |

### The three engines

| Tool | Engine | Question it answers |
| --- | --- | --- |
| `cdec_check` | A — drift | Did the architecture drift from the reference model? Model only; never reads bodies. `enforce=True` also runs B; `locks=True` (default) also runs C. |
| `cdec_enforce` | B — conformance | Does the code obey its rule tags right now? Re-parses source and inspects method bodies. |
| `cdec_lock_check` | C — freeze | Did a frozen (`@locked`) implementation change at all? |
| `cdec_lock_list` | C | What is lockable, what is tagged, what is baselined, what is stale. |
| `cdec_lock_set` | C | Record current implementations as the approved baseline. |

### The review loop

| Tool | What it does |
| --- | --- |
| `cdec_issues` | Every issue all three engines report, as one keyed list. The triage view. |
| `cdec_allow` | Accept issues by key into `.cdec/baseline.yaml`, with a reason. |
| `cdec_waivers_list` | What is currently accepted, and why. Needs no source parse. |
| `cdec_waiver_remove` | Withdraw waivers by key so those issues block again. |
| `cdec_waivers_prune` | Drop waivers for issues that no longer occur. |

### The model pipeline

| Tool | What it does |
| --- | --- |
| `cdec_parse` | Parse a source tree into a model file (`.xmi` or `.json`). |
| `cdec_convert` | Convert a model between XMI 2.1 and editor JSON. |
| `cdec_propose` | Push a proposed architecture to the web viewer, diffed against the code. Starts the viewer if needed. |
| `cdec_reference_test` | Every structural deviation of the code from the reference model. |
| `cdec_reference_set` | Promote an authored model to be the target architecture. |
| `cdec_reference_update` | Re-snapshot the *current* code as the reference. |

## Operations that need the user's say-so

Four tools change what the project is gated on, or accept something a rule
rejected. An agent should confirm with the user before calling them:

- **`cdec_allow`** — switches off a rule for a specific element. Always pass a
  `reason`; that is what makes the ledger reviewable.
- **`cdec_lock_set(force=True)`** — accepts a change to a *frozen*
  implementation. Without `force` the tool only adds new locks and can never
  erase evidence that locked code changed.
- **`cdec_reference_set`** — replaces the target architecture.
- **`cdec_reference_update`** — re-snapshots the current code as the reference,
  erasing the drift the reference existed to detect.

Lock violations are deliberately **not waivable** through `cdec_allow`; the tool
refuses them and points at `cdec_lock_set(force=True)`, which leaves a reviewable
diff on `.cdec/locks.yaml` that CODEOWNERS can gate.

Most tools that write accept `dry_run=True` to preview the change first.

## Typical flows

**Gate a change.** One call runs all three engines:

```json
{"tool": "cdec_check", "arguments": {"enforce": true}}
```

`ok` is the verdict; `text` is the human report with keys inline.

**Triage and accept.**

```json
{"tool": "cdec_issues", "arguments": {}}
{"tool": "cdec_allow", "arguments": {"keys": ["V-DD3EA5B2"], "reason": "agreed in ARCH-42"}}
```

**Agree a design.** Write a model `.json`, then iterate — re-proposing the same
model refreshes the already-open browser tab in place:

```json
{"tool": "cdec_propose", "arguments": {"model": "target.json", "focus": ["orders.Billing"]}}
{"tool": "cdec_reference_set", "arguments": {"model": "target.json"}}
```

`cdec_propose` returns a `url`; hand it to the user so they can look at the
diagram. It starts `cdec serve` in the background when nothing is listening on
the port (pass `start_viewer=false` to require an already-running viewer).

## Troubleshooting

**"the MCP server needs the optional `mcp` dependency"** — the package is
installed without the extra. Run `pip install "code-constraints[mcp]"` into the
same environment the `command` points at.

**Server shows as failed with no output** — almost always `command` not being
resolvable from the harness's environment. Use the absolute-interpreter variant
above.

**Tools report "missing .cdec/config.yaml"** — the project isn't scaffolded, or
the server's project root isn't the repo. Check `cdec_status`'s `project_root`,
and run `cdec init` in the target project.

**`cdec_propose` can't reach the viewer** — port 8765 is the default. Note port
8000 is reserved by Windows `http.sys` on some machines; pass `port` explicitly
if 8765 is taken.
