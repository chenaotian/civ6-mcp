"""Fallback lifecycle, unknown outcomes and independence from normal tokens."""

import asyncio
import json

import pytest

from civ6_fair_mcp.service import FairGameService
from civ6_fair_mcp.server import create_server
from test_service import FakeTransport, raw


CODE = 'print("visible UI diagnostic"); return true'
REASON = "get_pending_decisions reports an unsupported visible modal with no usable button."
ATTEMPTS = ["get_pending_decisions", "inspect_game"]


def response(phase="completed", **extra):
    return 'CIV6FAIR_JSON:' + json.dumps({"phase": phase, "lines": ["visible UI diagnostic"],
        "truncated": False, **extra}) + '\n---END---'


class FallbackTransport(FakeTransport):
    def __init__(self, *preflights, fallback=None):
        super().__init__(*preflights)
        self.fallback = response() if fallback is None else fallback
        self.fallback_calls = []

    async def execute_fallback(self, script, context="InGame", *, expected_generation):
        self.fallback_calls.append((script, context, expected_generation))
        if expected_generation != self.connection_generation:
            raise ConnectionError("SECRET transport detail")
        if isinstance(self.fallback, BaseException):
            raise self.fallback
        return self.fallback


async def test_missing_normal_token_and_inactive_turn_are_valid_for_verified_local_fallback():
    transport = FallbackTransport(raw(active_turn=False, fallback_eligible=True))
    service = FairGameService(transport)
    result = await service.run_lua(CODE, REASON, ATTEMPTS)
    assert result["ok"] and result["script_executed"] is True
    assert result["operation_completion"] == "not_asserted"
    assert result["automatic_fairness_filter"] is False
    assert result["receipt"]["reason"] == REASON
    assert result["receipt"]["attempted_tools"] == ATTEMPTS
    assert result["receipt"]["attempts_verified"] is False
    assert result["receipt"]["retention"] == "response_only"
    assert CODE not in json.dumps(result)
    assert len(transport.calls) == len(transport.fallback_calls) == 1
    assert transport.fallback_calls[0][1:] == ("InGame", 1)
    assert service._observation is None and service._last_read is None


@pytest.mark.parametrize("phase,executed", [("completed", True), ("runtime_error", True),
    ("compile_error", False), ("compiler_unavailable", False), ("identity_rejected", False),
    ("outcome_unknown", None)])
async def test_all_results_invalidate_observation_wait_history_and_preview(phase, executed):
    transport = FallbackTransport(raw(), raw(fallback_eligible=True), fallback=response(phase))
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    service._preview_generation = transport.connection_generation
    assert service._last_read is not None and (await service.get_session_history())["entries"]
    result = await service.run_lua(CODE, REASON, ATTEMPTS)
    assert result["status"] == phase and result["script_executed"] is executed
    assert service._observation is None and service._last_read is None and service._preview_generation is None
    assert (await service.get_session_history())["entries"] == []
    assert (await service.wait_for_change(1))["error"] == "observation_required"
    assert (await service.act(token, {"type": "end_turn"}))["error"] == "fresh_observation_required"
    assert len(transport.fallback_calls) == 1
    await service.close()
    assert len(transport.calls) == 2  # no old preview cleanup after fallback


@pytest.mark.parametrize("preflight", [raw(), raw(fallback_eligible=1),
    {"ok": False, "error": "SECRET"}, raw(fallback_eligible=True, session="bad"),
    TimeoutError("SECRET native error")])
async def test_failed_or_malformed_preflight_never_executes_arbitrary_code(preflight):
    transport = FallbackTransport(preflight)
    service = FairGameService(transport)
    result = await service.run_lua(CODE, REASON, ATTEMPTS)
    assert result["error"] == "fallback_preflight_unavailable" and result["script_executed"] is False
    assert not transport.fallback_calls and transport.closed
    assert "SECRET" not in json.dumps(result)


@pytest.mark.parametrize("failure", [TimeoutError("SECRET"), ConnectionError("SECRET"),
    "CIV6FAIR_JSON:{bad json}\n---END---", response(lines=["x" * 4097]),
    response(phase=["SECRET"]), response(return_type=[], return_value=42)])
async def test_after_dispatch_failures_are_unknown_never_replayed(failure):
    transport = FallbackTransport(raw(fallback_eligible=True), fallback=failure)
    service = FairGameService(transport)
    result = await service.run_lua(CODE, REASON, ATTEMPTS)
    assert result["error"] == "fallback_outcome_unknown" and result["script_executed"] is None
    assert len(transport.calls) == len(transport.fallback_calls) == 1
    assert transport.closed and "SECRET" not in json.dumps(result)


@pytest.mark.parametrize("context,expected", [("ingame", "InGame"), ("gamecore", "GameCore_Tuner"),
                                          ("NewNativePopup", "NewNativePopup")])
async def test_context_aliases_are_explicit_and_bound_to_preflight_generation(context, expected):
    transport = FallbackTransport(raw(fallback_eligible=True))
    service = FairGameService(transport)
    result = await service.run_lua(CODE, REASON, ATTEMPTS, context)
    assert result["receipt"]["context"] == expected
    assert transport.fallback_calls[0][1:] == (expected, 1)


async def test_invalid_input_drops_old_capability_but_never_contacts_game():
    transport = FallbackTransport(raw())
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.run_lua(CODE, "", [])
    assert result["error"] == "invalid_input" and result["script_executed"] is False
    assert len(transport.calls) == 1 and not transport.fallback_calls
    assert service._observation is None and service._last_read is None


async def test_unsupported_transport_fails_without_preflight():
    transport = FakeTransport()
    result = await FairGameService(transport).run_lua(CODE, REASON, ATTEMPTS)
    assert result["error"] == "fallback_transport_unavailable" and not transport.calls


@pytest.mark.parametrize("cancel_phase", ["preflight", "dispatch"])
async def test_cancellation_propagates_closes_connection_and_clears_state(cancel_phase):
    preflight = asyncio.CancelledError() if cancel_phase == "preflight" else raw(fallback_eligible=True)
    transport = FallbackTransport(raw(), preflight, fallback=asyncio.CancelledError())
    if cancel_phase == "preflight":
        original = transport.execute
        async def execute(*args, **kwargs):
            if len(transport.calls) == 1:
                raise asyncio.CancelledError()
            return await original(*args, **kwargs)
        transport.execute = execute
    service = FairGameService(transport)
    await service.get_player_state()
    service._preview_generation = 1
    with pytest.raises(asyncio.CancelledError):
        await service.run_lua(CODE, REASON, ATTEMPTS)
    assert transport.closed
    assert service._observation is None and service._last_read is None and service._preview_generation is None
    assert (await service.get_session_history())["entries"] == []
    assert len(transport.fallback_calls) == (1 if cancel_phase == "dispatch" else 0)


async def test_actual_mcp_registration_executes_the_guarded_service_path():
    transport = FallbackTransport(raw(fallback_eligible=True))
    server = create_server(FairGameService(transport))
    tools = await server.list_tools()
    tool = next(item for item in tools if item.name == "run_lua")
    assert set(tool.inputSchema["required"]) == {"code", "reason", "attempted_tools"}
    assert tool.annotations.destructiveHint and not tool.annotations.idempotentHint
    await server.call_tool("run_lua", {"code": CODE, "reason": REASON, "attempted_tools": ATTEMPTS})
    assert len(transport.calls) == len(transport.fallback_calls) == 1


async def test_close_error_does_not_replace_cancellation_or_keep_old_state():
    transport = FallbackTransport(raw(fallback_eligible=True), fallback=asyncio.CancelledError())
    async def broken_close():
        raise OSError("SECRET close failure")
    transport.close = broken_close
    service = FairGameService(transport)
    service._preview_generation = 1
    with pytest.raises(asyncio.CancelledError):
        await service.run_lua(CODE, REASON, ATTEMPTS)
    assert service._observation is None and service._last_read is None and service._preview_generation is None
