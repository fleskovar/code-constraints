"""code-constraints as an MCP server.

Exposes the three enforcement engines, the model pipeline, and the waiver review
loop over the Model Context Protocol, so any MCP-capable coding harness can run
`cdec` operations as tools instead of shelling out and parsing human output.

The tools call the library in-process (`code_constraints.lint`,
`code_constraints.enforce`, `code_constraints.lock`, `code_constraints.waivers`)
rather than invoking the `cdec` CLI, so results arrive as structured JSON and
issue keys line up exactly with what `cdec check` would print.

    python -m code_constraints.mcp          # stdio transport
    cdec-mcp                                # same, via the console script

Requires the optional `mcp` dependency: `pip install "code-constraints[mcp]"`.
"""

from code_constraints.mcp.server import build_server

__all__ = ["build_server"]
