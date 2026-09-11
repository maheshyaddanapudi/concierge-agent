"""Stub MCP server for manager tests (spec §11).

FastMCP stdio server with a mutable toolset:
- v1 exposes `echo` and `add`
- calling `mutate_toolset` drops `add`, adds `extra_tool`, and emits a
  tools/list_changed notification
- calling `die` hard-exits the process (health-loop tests)
"""

import asyncio
import os
import sys

from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP("stub")


def echo(text: str) -> str:
    """Echo the given text back."""
    return f"echo:{text}"


def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def extra_tool() -> str:
    """A tool that only exists in toolset v2."""
    return "extra"


async def mutate_toolset(ctx: Context) -> str:  # type: ignore[type-arg]
    """Switch the server to toolset v2 and notify listChanged."""
    mcp._tool_manager.remove_tool("add")
    mcp.add_tool(extra_tool)
    await ctx.session.send_tool_list_changed()
    return "mutated"


def die() -> str:
    """Hard-exit the server process."""
    os._exit(1)


def echo_v2(message: str) -> str:
    """Echo the given text back."""
    return f"echo:{message}"


_ECHO_V2 = False


async def mutate_schema(ctx: Context) -> str:  # type: ignore[type-arg]
    """Rename `echo`'s parameter (text ⇄ message) — the same tool name with
    a different input schema — and notify listChanged (spec §3.2 drift).
    Each call flips between the two shapes, so a drill can change it back."""
    global _ECHO_V2
    _ECHO_V2 = not _ECHO_V2
    mcp._tool_manager.remove_tool("echo")
    mcp.add_tool(echo_v2 if _ECHO_V2 else echo, name="echo")
    await ctx.session.send_tool_list_changed()
    return f"schema mutated: echo now takes {'message' if _ECHO_V2 else 'text'}"


mcp.add_tool(echo)
mcp.add_tool(add)
mcp.add_tool(mutate_toolset)
mcp.add_tool(mutate_schema)
mcp.add_tool(die)


if __name__ == "__main__":
    if "--fail" in sys.argv:
        print("boot failure", file=sys.stderr)
        sys.exit(3)
    asyncio.run(mcp.run_stdio_async())
