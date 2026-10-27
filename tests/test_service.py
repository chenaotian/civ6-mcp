import asyncio
import json

import pytest

from civ6_fair_mcp.service import FairGameService


def raw(**extra):
    return {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 10,
            "active_turn": True, "player": {"gold": 25}, "units": [], "cities": [], **extra}


class FakeTransport:
    connection_generation = 1

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    async def execute(self, script, context="InGame", *, expected_generation=None):
        if expected_generation is not None and expected_generation != self.connection_generation:
            raise RuntimeError("stale")
        self.calls.append(script)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return "CIV6FAIR_JSON:" + json.dumps(value) + "\n---END---"

    async def close(self):
        self.closed = True
        self.connection_generation += 1


async def test_token_consumed_and_action_not_replayed():
    transport = FakeTransport(raw(), raw(accepted=True))
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    assert (await service.act(token, {"type": "end_turn"}))["status"] == "submitted"
    assert (await service.act(token, {"type": "end_turn"}))["error"] == "fresh_observation_required"
    assert len(transport.calls) == 2


async def test_timeout_redacted_and_not_retried():
    transport = FakeTransport(raw(), TimeoutError("enemy uranium at 12,13"))
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    result = await service.act(token, {"type": "end_turn"})
    assert result == {"ok": False, "error": "action_outcome_unknown"}
    assert len(transport.calls) == 2 and transport.closed
    assert (await service.act(token, {"type": "end_turn"}))["error"] == "fresh_observation_required"


async def test_concurrent_actions_only_one_submits():
    transport = FakeTransport(raw(), raw(accepted=True))
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    results = await asyncio.gather(*(service.act(token, {"type": "end_turn"}) for _ in range(5)))
    assert sum(r.get("accepted", False) for r in results) == 1
    assert len(transport.calls) == 2


async def test_reconnect_invalidates_token_before_dispatch():
    transport = FakeTransport(raw())
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    transport.connection_generation += 1
    assert (await service.act(token, {"type": "end_turn"}))["error"] == "fresh_observation_required"
    assert len(transport.calls) == 1


async def test_inactive_turn_issues_no_capability():
    service = FairGameService(FakeTransport(raw(active_turn=False)))
    assert "observation_token" not in await service.get_player_state()


async def test_read_errors_never_expose_engine_details():
    service = FairGameService(FakeTransport(ValueError("hidden world state")))
    assert await service.get_player_state() == {"ok": False, "error": "game_unavailable"}


async def test_invalid_action_consumes_capability_without_dispatch():
    transport = FakeTransport(raw())
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    assert (await service.act(token, {"type": "run_lua", "code": "print(Players[1])"}))["error"] == "invalid_action"
    assert len(transport.calls) == 1
    assert (await service.act(token, {"type": "end_turn"}))["error"] == "fresh_observation_required"


async def test_new_observation_invalidates_previous_token():
    service = FairGameService(FakeTransport(raw(), raw()))
    old = (await service.get_player_state())["observation_token"]
    new = (await service.get_player_state())["observation_token"]
    assert old != new
    assert (await service.act(old, {"type": "end_turn"}))["error"] == "fresh_observation_required"


async def test_expired_capability():
    service = FairGameService(FakeTransport(raw()), token_ttl=-1)
    token = (await service.get_player_state())["observation_token"]
    assert (await service.act(token, {"type": "end_turn"}))["error"] == "fresh_observation_required"


async def test_bounds_reject_before_contacting_game():
    transport = FakeTransport()
    service = FairGameService(transport)
    for coords in [(True, 0, 1), (0, 0, 999), (-1, 0, 1)]:
        assert await service.observe_area(*coords) == {"ok": False, "error": "invalid_input"}
    assert not transport.calls


async def test_diplomacy_projection_and_fresh_token():
    transport = FakeTransport(raw(), raw(civilization_count=6, civilizations=[
        {"id": 1, "met": True, "alive": True, "civilization": "CIVILIZATION_ROME", "gold": 25},
        {"id": 2, "met": False, "civilization": "CIVILIZATION_GERMANY", "gold": 9999}]))
    service = FairGameService(transport)
    previous = (await service.get_player_state())["observation_token"]
    result = await service.get_diplomacy()
    assert result["civilization_count"] == 6
    assert len(result["civilizations"]) == 1 and result["civilizations"][0]["id"] == 1
    assert result["observation_token"] != previous
    assert "GERMANY" not in json.dumps(result)
    assert (await service.act(previous, {"type": "end_turn"}))["error"] == "fresh_observation_required"


async def test_diplomacy_errors_are_opaque_and_invalidate_observation():
    service = FairGameService(FakeTransport(raw(), RuntimeError("unmet leader secret")))
    token = (await service.get_player_state())["observation_token"]
    assert await service.get_diplomacy() == {"ok": False, "error": "game_unavailable"}
    assert (await service.act(token, {"type": "end_turn"}))["error"] == "fresh_observation_required"
