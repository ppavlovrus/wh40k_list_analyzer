"""MCP server smoke test: in-memory stdio session, real tool calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from wh40k_analyzer.mcp_server import mcp

FIXTURE = Path(__file__).parent / "fixtures" / "salamanders_take_and_hold.json"


async def _call(session, name: str, args: dict) -> object:
    result = await session.call_tool(name, args)
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured.get("result", structured)
    if result.content:
        return result.content[0].text
    return None


def test_mcp_tools_end_to_end():
    async def scenario() -> None:
        async with create_connected_server_and_client_session(mcp) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {
                "load_roster_tool",
                "army_summary",
                "list_scenarios",
                "damage_matrix_tool",
                "duel",
            } <= names

            loaded = await _call(
                session,
                "load_roster_tool",
                {
                    "path": str(FIXTURE),
                    "roster_id": "sal",
                },
            )
            loaded = json.loads(loaded) if isinstance(loaded, str) else loaded
            assert loaded["points"] == 1960
            assert any(u["name"] == "Infernus Squad" for u in loaded["combat_units"])

            scenarios = await _call(session, "list_scenarios", {})
            assert "full_buffs_shooting" in scenarios

            summary = await _call(session, "army_summary", {"roster_id": "sal"})
            assert "Infernus Squad" in str(summary)

    asyncio.run(scenario())
