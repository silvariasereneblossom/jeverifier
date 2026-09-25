"""MCP server: gives Claude Code (or any MCP client) the harness's reading lists as a tool.
Needs a Jev key (TYPESAFE_API_KEY or OPENJEV_API_KEY, see jev.py).

Register:  claude mcp add jeverifier -- <venv python> -m jeverifier.mcp_server
           (<venv>/bin/python on Linux and macOS, <venv>\\Scripts\\python.exe on Windows)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import ctx

mcp = MCPServer(name="jeverifier", instructions="Use context_find at the start of a task instead of reading every "
                                                "doc: it returns the doc sections the task needs, within a token budget.")


@mcp.tool()
async def context_find(repo: str, task: str, budget_tokens: int = 25_000) -> str:
    """Reading list for `task`: the doc sections (file:line ranges) Jev judges relevant, within a
    token budget. Use at the start of a session instead of reading every doc; CLAUDE.md and
    docs/HANDOVER.md are assumed already read."""
    picked, total = await asyncio.to_thread(ctx.find, Path(repo), task, budget_tokens,
                                            0.5, ("CLAUDE.md", "docs/HANDOVER.md"))
    return ctx.render_reading_list(task, picked, total)


def main() -> None:
    import logging

    from . import keys

    keys.load_into_env()
    for name in ("httpx", "httpx2", "typesafe_sdk"):
        logging.getLogger(name).setLevel(logging.WARNING)
    mcp.run("stdio")


if __name__ == "__main__":
    main()
