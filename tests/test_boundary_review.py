"""Independent regressions for the service / transport / JSON trust boundaries."""

import asyncio
import json

import pytest

from civ6_fair_mcp.policy import parse_response, public_player
from civ6_fair_mcp.service import FairGameService


def state(**extra):
    return {
        "ok": True, "session": "s" * 32, "player_id": 0, "turn": 10,
        "active_turn": True, "player": {}, "units": [], "cities": [], **extra,
    }


class BoundaryTransport:
    def __init__(self):
        self.connection_generation = 1
        self.executions = 0
        self.submitted_actions = 0
        self.closed = False
        self.change_generation_at_dispatch = False
        self.block_next = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, script, context="InGame", *, expected_generation=None):
        self.executions += 1
        if expected_generation is not None:
            if self.change_generation_at_dispatch:
                self.connection_generation += 1
            if expected_generation != self.connection_generation:
                raise ConnectionError("internal hidden engine message")
            self.submitted_actions += 1
        if self.block_next:
            self.entered.set()
            await self.release.wait()
        return "CIV6FAIR_JSON:" + json.dumps(state(accepted=True)) + "\n---END---"

    async def close(self):
        self.closed = True
        self.connection_generation += 1


@pytest.mark.parametrize("invalid_token", ["令牌", "é", "a\u2028b", "\ud800"])
async def test_non_ascii_capability_is_generic_rejection_and_is_consumed(invalid_token):
    transport = BoundaryTransport()
    service = FairGameService(transport)
    valid_token = (await service.get_player_state())["observation_token"]
    assert await service.act(invalid_token, {"type": "end_turn"}) == {
        "ok": False, "error": "fresh_observation_required",
    }
    assert await service.act(valid_token, {"type": "end_turn"}) == {
        "ok": False, "error": "fresh_observation_required",
    }
    assert transport.submitted_actions == 0


@pytest.mark.parametrize("x,y", [(4096, 0), (0, 4096), (65535, 65535)])
async def test_map_coordinate_validation_matches_template_before_transport(x, y):
    transport = BoundaryTransport()
    service = FairGameService(transport)
    assert await service.observe_area(x, y) == {"ok": False, "error": "invalid_input"}
    assert transport.executions == 0
    assert not transport.closed


async def test_reconnect_between_service_check_and_dispatch_cannot_submit():
    transport = BoundaryTransport()
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    transport.change_generation_at_dispatch = True
    assert await service.act(token, {"type": "end_turn"}) == {
        "ok": False, "error": "action_outcome_unknown",
    }
    assert transport.submitted_actions == 0
    assert transport.closed
    assert "observation_token" not in await service.act(token, {"type": "end_turn"})


@pytest.mark.parametrize("operation", ["action", "observation"])
async def test_cancellation_cannot_restore_previous_capability(operation):
    transport = BoundaryTransport()
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    transport.block_next = True
    pending = asyncio.create_task(
        service.act(token, {"type": "end_turn"})
        if operation == "action" else service.get_player_state()
    )
    await asyncio.wait_for(transport.entered.wait(), timeout=1)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    calls_after_cancel = transport.executions
    assert await service.act(token, {"type": "end_turn"}) == {
        "ok": False, "error": "fresh_observation_required",
    }
    assert transport.executions == calls_after_cancel


@pytest.mark.parametrize("separator", ["\u0085", "\u2028", "\u2029"])
def test_unicode_line_separators_inside_json_strings_are_not_protocol_delimiters(separator):
    name = "City" + separator + "Name"
    raw = state(cities=[{"owner_id": 0, "id": 1, "x": 2, "y": 3, "name": name}])
    wire = "CIV6FAIR_JSON:" + json.dumps(raw, ensure_ascii=False) + "\n---END---"
    assert public_player(parse_response(wire))["cities"][0]["name"] == name
