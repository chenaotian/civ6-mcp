import json

import pytest

from civ6_fair_mcp.service import FairGameService
from test_service import FakeTransport, raw


async def test_diary_records_only_public_summary_and_submission_not_success():
    transport = FakeTransport(raw(secret="HIDDEN", units=[], tiles=[{"secret": "HIDDEN"}]), raw(accepted=True))
    service = FairGameService(transport)
    first = await service.get_player_state()
    await service.act(first["observation_token"], {"type": "end_turn"})
    result = await service.get_session_history()
    assert len(result["entries"]) == 2 and len(transport.calls) == 2
    assert result["entries"][1] == {"kind": "action_request", "turn": 10,
        "action_type": "end_turn", "accepted": True, "status": "submitted", "completion": "not_asserted"}
    encoded = json.dumps(result)
    assert "HIDDEN" not in encoded and first["observation_token"] not in encoded and "a" * 32 not in encoded
    assert "observation_token" not in result and service._observation is None


async def test_history_read_keeps_current_single_use_capability_and_returns_copy():
    service = FairGameService(FakeTransport(raw()))
    current = await service.get_player_state()
    result = await service.get_session_history()
    result["entries"][0]["economy"]["gold"] = 999
    assert (await service.get_session_history())["entries"][0]["economy"]["gold"] == 25
    assert service._observation.token == current["observation_token"]
    assert len(service.transport.calls) == 1


@pytest.mark.parametrize("extra", [{"session": "b" * 32}, {"player_id": 1}, {"turn": 9}])
async def test_reload_player_change_or_turn_rollback_replaces_diary(extra):
    service = FairGameService(FakeTransport(raw(player={"gold": 10}), raw(player={"gold": 20}, **extra)))
    await service.get_player_state()
    await service.get_player_state()
    entries = (await service.get_session_history())["entries"]
    assert len(entries) == 1 and entries[0]["economy"]["gold"] == 20


async def test_reconnect_clears_history_before_any_new_observation():
    service = FairGameService(FakeTransport(raw()))
    await service.get_player_state()
    service.transport.connection_generation += 1
    assert (await service.get_session_history())["entries"] == []


async def test_failed_read_and_close_clear_diary():
    service = FairGameService(FakeTransport(raw(), ValueError("HIDDEN"), raw()))
    await service.get_player_state()
    await service.get_player_state()
    assert (await service.get_session_history())["entries"] == []
    await service.get_player_state()
    await service.close()
    assert (await service.get_session_history())["entries"] == []


async def test_diary_is_bounded_and_limit_validated_without_game_calls():
    service = FairGameService(FakeTransport(*(raw(turn=i) for i in range(70))))
    for _ in range(70):
        await service.get_player_state()
    result = await service.get_session_history(64)
    assert len(result["entries"]) == 64 and result["entries"][0]["turn"] == 6
    assert len((await service.get_session_history(3))["entries"]) == 3
    for value in (0, 65, True, "2"):
        assert (await service.get_session_history(value))["error"] == "invalid_input"
    assert len(service.transport.calls) == 70


async def test_identical_observation_polls_do_not_evict_useful_history():
    service = FairGameService(FakeTransport(raw(), raw(accepted=True), *(raw() for _ in range(70))))
    first = await service.get_player_state()
    await service.act(first["observation_token"], {"type": "end_turn"})
    for _ in range(70):
        await service.get_player_state()
    assert len((await service.get_session_history(64))["entries"]) == 3
