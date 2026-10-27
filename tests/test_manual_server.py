"""The manual tool must not invalidate a player's pending action capability."""

from civ6_fair_mcp.server import create_server
from civ6_fair_mcp.service import FairGameService
from test_service import FakeTransport, raw


async def test_manual_tool_does_not_touch_game_token_or_history(tmp_path):
    transport = FakeTransport(raw(), raw(accepted=True))
    service = FairGameService(transport)
    current = await service.get_player_state()
    observation = service._observation
    baseline = service._last_read
    history = await service.get_session_history()
    server = create_server(service, tmp_path)
    await server.call_tool("query_manual", {})
    await server.call_tool("query_manual", {"query": "总督"})
    await server.call_tool("query_manual", {"entry_id": "LOC_PEDIA_CONCEPTS_PAGE_POWER_CHAPTER_CONTENT"})
    await server.call_tool("query_manual", {"query": "总督", "source": "all"})
    await server.call_tool("query_manual", {"source": "gathering_storm", "page": 6})
    await server.call_tool("query_manual", {"source": "../../Saves"})
    assert service._observation is observation
    assert service._last_read is baseline
    assert await service.get_session_history() == history
    assert len(transport.calls) == 1
    result = await service.act(current["observation_token"], {"type": "end_turn"})
    assert result["status"] == "submitted"
    assert len(transport.calls) == 2
