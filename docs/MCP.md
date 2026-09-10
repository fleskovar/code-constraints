# code-constraints as an MCP server

`cdec-mcp` exposes the gate, the model pipeline, and the exception review loop
over the [Model Context Protocol](https://modelcontextprotocol.io) as a **stdio
server**, so any MCP-capable coding harness can run code-constraints as tools
instead of shelling out to the CLI and parsing human output.

The tools call the library in-process, so results come back as structured JSON
and issue keys (`V-`/`F-`/`L-`/`R-`) are derived by the same code path the CLI
uses — a key an agent reads from `cdec_check` is the same key
`cdec exceptions allow` accepts on the command line.

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
| `cdec_status` | How code-constraints is configured here: language, source, reference, which rules are active, how many exceptions and locks are recorded. Start here. |
| `cdec_rules` | The catalogue of constraint *tags* (`@no_instantiation`, `[Sealed]`, …), their legal targets and parameters. Read it before writing a tag. |
| `cdec_rule_types` | The `type:` values that can appear in `.cdec/rules.yaml`. Read it before writing a rule. |

### The gate

| Tool | What it does |
| --- | --- |
| `cdec_check` | Runs **every** rule in `.cdec/rules.yaml` and returns one verdict. Model rules, `tag-conformance`, `implementation-locks` and `reference-architecture` alike. There is no second gate to call. |
| `cdec_accept` | Records the current state as approved instead of failing on it: `what=["rules"]` grandfathers today's violations, `["locks"]` records new lock digests, `["reference"]` re-snapshots the reference model. |
| `cdec_locks` | Read-only: what is lockable, what is tagged, what is baselined, what is stale. |

Each violation carries a key whose prefix names the engine that produced it — `V-` a model
rule, `F-` `tag-conformance`, `L-` `implementation-locks`, `R-` `reference-architecture`.

### The review loop

| Tool | What it does |
| --- | --- |
| `cdec_issues` | Every issue `cdec_check` reports, as one keyed list. The triage view; filter by `engine` or `rule_id`. |
| `cdec_allow` | Accept issues by key into the `exceptions:` section of `.cdec/rules.yaml`, with a reason. |
| `cdec_exceptions_list` | What is currently accepted, and why. Needs no source parse. |
| `cdec_exception_remove` | Withdraw exceptions by key so those issues block again. |
| `cdec_exceptions_prune` | Drop exceptions for issues that no longer occur. |

### The model pipeline

| Tool | What it does |
| --- | --- |
| `cdec_parse` | Parse a source tree into a model file (`.xmi` or `.json`). |
| `cdec_convert` | Convert a model between XMI 2.1 and editor JSON. |
| `cdec_propose` | Push a proposed architecture to the web viewer, diffed against the code. Starts the viewer if needed. |
| `cdec_reference_set` | Promote an authored model to be the target architecture — what the code *should become*. |

## Operations that need the user's say-so

Three tools change what the project is gated on, or accept something a rule
rejected. An agent should confirm with the user before calling them:

- **`cdec_allow`** — switches off a rule for a specific element. Always pass a
  `reason`; that is what makes the entry reviewable.
- **`cdec_accept`** — accepts the current state wholesale. Each value is a different
  size of decision:
  - `what=["rules"]` grandfathers every current violation. The adoption move on an
    existing codebase, and a blunt one anywhere else.
  - `what=["locks"]` records digests for newly tagged code. Safe on its own — without
    `force` it only *adds* and can never erase evidence that locked code changed.
    `force=True` accepts a change to a *frozen* implementation: only with explicit
    approval.
  - `what=["reference"]` re-snapshots the current code, erasing the drift the reference
    existed to detect.
- **`cdec_reference_set`** — replaces the target architecture.

Lock violations are deliberately **not acceptable** through `cdec_allow`; the tool refuses
them and points at `cdec_accept(what=["locks"], force=True)`, which leaves a reviewable diff
on the `locks:` section of `.cdec/rules.yaml` that CODEOWNERS can gate.
`cdec_accept(what=["rules"])` refuses them too, and reports which ones it would not
grandfather.

Most tools that write accept `dry_run=True` to preview the change first.

## Typical flows

**Gate a change.** One call runs every rule the project configured:

```json
{"tool": "cdec_check", "arguments": {}}
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

**Tools report "missing .cdec/rules.yaml"** — the project isn't scaffolded, or
the server's project root isn't the repo. Check `cdec_status`'s `project_root`,
and run `cdec init` in the target project.

**`cdec_propose` can't reach the viewer** — port 8765 is the default. Note port
8000 is reserved by Windows `http.sys` on some machines; pass `port` explicitly
if 8765 is taken.
