"""MCP stdio handshake smoke test: spawns the real server subprocess over
stdio, initializes a client session, and checks the tool list. Needs no
Mort compiler - tools only look for one when called.
"""

import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

EXPECTED_TOOLS = {
    "mort_version",
    "mort_check",
    "mort_run",
    "mort_emit_c",
    "mort_format",
    "mort_std",
    "mort_docs",
    "mort_examples",
}


@pytest.mark.anyio
async def test_stdio_handshake_lists_expected_tools():
    params = StdioServerParameters(command=sys.executable, args=["-m", "mort_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init_result = await session.initialize()
        assert init_result.server_info.name == "mort"

        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert names == EXPECTED_TOOLS, (
            f"missing: {EXPECTED_TOOLS - names}, unexpected: {names - EXPECTED_TOOLS}"
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_instructive_errors_reach_the_agent(tmp_path):
    """MCPServer hides any exception that isn't a ToolError behind a generic
    "Error executing tool X"; setup instructions must survive the trip."""
    import os

    env = {k: v for k, v in os.environ.items() if k != "MORT_HOME"}
    env["MORT_HOME"] = str(tmp_path)  # a directory with no mortc.py
    params = StdioServerParameters(command=sys.executable, args=["-m", "mort_mcp"], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("mort_check", {"source": "fn main() -> int { return 0; }"})
        assert result.is_error
        assert "has no mortc.py - point it at a Mort checkout" in result.content[0].text
