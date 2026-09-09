"""Entry point for the code-constraints MCP server.

    python -m code_constraints.mcp
    cdec-mcp --project-root /path/to/repo

stdio is the default transport because that is what coding harnesses launch:
the harness spawns this process and speaks JSON-RPC over its stdin/stdout.
Which is also why the first thing `main` does is pin logging to stderr — a
stray byte on stdout corrupts the protocol stream.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cdec-mcp",
        description="Run code-constraints as an MCP server.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Directory that relative tool paths resolve against "
            "(default: $CDEC_PROJECT_ROOT, else the current directory)."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio, which is what coding harnesses use).",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Log verbosity. Logs always go to stderr.",
    )
    args = parser.parse_args(argv)

    # stdout belongs to the MCP transport; everything diagnostic goes to stderr.
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        from code_constraints.mcp.server import build_server
    except ModuleNotFoundError as exc:
        if exc.name != "mcp":
            raise
        print(
            "the MCP server needs the optional `mcp` dependency:\n"
            '    pip install "code-constraints[mcp]"',
            file=sys.stderr,
        )
        return 2

    build_server(args.project_root).run(transport=args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
