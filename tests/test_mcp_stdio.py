"""Exercise a real SDK client/server subprocess, without a running game."""

from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_stdio_handshake_tool_surface_and_input_rejection():
    parameters = StdioServerParameters(command=sys.executable,
        args=["-m", "civ6_fair_mcp"], cwd=str(Path(__file__).resolve().parents[1]))
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as client:
            initialized = await client.initialize()
            assert initialized.serverInfo.name == "civ6-fair"
            tools = (await client.list_tools()).tools
            assert {tool.name for tool in tools} == {
                "get_rules", "query_manual", "get_game_status", "get_player_state", "get_diplomacy", "observe_area", "list_options", "inspect_game", "get_pending_decisions", "wait_for_change", "get_session_history", "act", "run_lua"}
            rules = await client.call_tool("get_rules", {})
            assert not rules.isError
            from civ6_fair_mcp import __version__
            assert rules.structuredContent["version"] == __version__
            assert "congress_ballot" in rules.structuredContent["actions"]
            assert "pending_decisions" in rules.structuredContent["inspection_categories"]
            manual = next(tool for tool in tools if tool.name == "query_manual")
            assert manual.annotations.readOnlyHint is True
            assert manual.annotations.openWorldHint is False
            assert manual.inputSchema["properties"]["source"]["default"] == "civilopedia"
            catalog = await client.call_tool("query_manual", {})
            assert not catalog.isError
            assert {item["id"] for item in catalog.structuredContent["sources"]} == {
                "civilopedia", "base", "rise_and_fall", "gathering_storm"}
            invalid_manual = await client.call_tool("query_manual", {"source": "../../save"})
            assert invalid_manual.structuredContent["error"] == "invalid_input"
            waiting = next(tool for tool in tools if tool.name == "wait_for_change")
            assert waiting.annotations.readOnlyHint is True
            invalid_wait = await client.call_tool("wait_for_change", {"timeout_ms": 10001})
            assert invalid_wait.structuredContent == {"ok": False, "error": "invalid_input"}
            no_baseline = await client.call_tool("wait_for_change", {"timeout_ms": 10})
            assert no_baseline.structuredContent["error"] == "observation_required"
            history = await client.call_tool("get_session_history", {"limit": 10})
            assert not history.isError and history.structuredContent["entries"] == []
            invalid_history = await client.call_tool("get_session_history", {"limit": 65})
            assert invalid_history.structuredContent == {"ok": False, "error": "invalid_input"}
            invalid = await client.call_tool("observe_area", {"x": 1, "y": 1, "radius": 999})
            assert invalid.structuredContent == {"ok": False, "error": "invalid_input"}
            replay = await client.call_tool("act", {"observation_token": "fake", "action": {"type": "end_turn"}})
            assert replay.structuredContent["error"] == "fresh_observation_required"
            fallback = next(tool for tool in tools if tool.name == "run_lua")
            assert fallback.annotations.readOnlyHint is False
            assert fallback.annotations.idempotentHint is False
            assert "备用接口" in fallback.description and "LAST RESORT" in fallback.description
            missing = await client.call_tool("run_lua", {"code": "return 1"})
            assert missing.isError
            invalid = await client.call_tool("run_lua", {"code": "return 1", "reason": "", "attempted_tools": []})
            assert invalid.structuredContent["error"] == "invalid_input"
