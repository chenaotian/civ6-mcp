"""UI activity is an advisory fixed enum, not action completion or permission."""
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.engine_activity import ACTIVITY_LUA, combine_engine_activity
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.service import FairGameService
from test_queries import engine
from test_service import raw
from test_ui_monitoring import UITransport, popup
from test_waiting import RepeatingTransport


@pytest.mark.parametrize("core,processing,expected", [
    ("false", "false", "idle"), ("true", "false", "busy"),
    ("false", "true", "busy"), ("true", "true", "busy"),
    ("nil", "false", "unknown"), ("false", "nil", "unknown"),
    ("1", "false", "unknown"), ("false", "0", "unknown"),
    ('"false"', "false", "unknown"), ("{}", "false", "unknown"),
    ("nil", "true", "busy"), ("true", "nil", "busy"),
])
def test_lua_accepts_only_strict_boolean_signals(core, processing, expected):
    vm = LuaRuntime()
    vm.execute(f"out={{}}; UI={{IsGameCoreBusy=function() return {core} end,"
               f"IsProcessingMessages=function() return {processing} end}}")
    vm.execute(ACTIVITY_LUA)
    assert vm.globals().out.engine_activity == expected


@pytest.mark.parametrize("setup,expected", [
    ("UI=nil", "unknown"),
    ("UI={}", "unknown"),
    ("UI={IsProcessingMessages=function() return false end}", "unknown"),
    ("UI={IsGameCoreBusy=function() error('SECRET') end,"
     "IsProcessingMessages=function() return false end}", "unknown"),
    ("UI={IsGameCoreBusy=function() return true end,"
     "IsProcessingMessages=function() error('SECRET') end}", "busy"),
    ("UI=setmetatable({}, {__index=function() error('SECRET') end})", "unknown"),
])
def test_missing_or_throwing_api_never_exports_error_or_claims_idle(setup, expected):
    vm = LuaRuntime()
    vm.execute("out={}; " + setup)
    vm.execute(ACTIVITY_LUA)
    assert dict(vm.globals().out) == {"engine_activity": expected}


@pytest.mark.parametrize("accepted", ["true", "false"])
def test_action_wrapper_never_samples_or_returns_post_request_activity(engine, accepted):
    vm, run = engine
    vm.execute("calls=0; UI.IsGameCoreBusy=function() calls=calls+1; return true end")
    result = run(wrap(f"out.accepted={accepted}", "a" * 32, observation_activity=False))
    assert vm.globals().calls == 0
    assert "engine_activity" not in result
    assert result["accepted"] is (accepted == "true")


@pytest.mark.parametrize("busy", [True, False])
def test_wrapped_read_samples_activity_without_altering_existing_active_turn(engine, busy):
    vm, run = engine
    vm.execute(f"UI.IsGameCoreBusy=function() return {str(busy).lower()} end")
    result = run(wrap("", "a" * 32))
    assert result["active_turn"] is True
    assert result["engine_activity"] == ("busy" if busy else "idle")


@pytest.mark.parametrize("values,expected", [
    ((), "unknown"), (("idle",), "idle"), (("idle", "idle"), "idle"),
    (("idle", "busy"), "busy"), (("busy", "unknown"), "busy"),
    (("idle", "unknown"), "unknown"), (("idle", None), "unknown"),
    ((True,), "unknown"), (({},), "unknown"), ((["busy"],), "unknown"),
    (("SECRET_ENGINE_ERROR",), "unknown"),
])
def test_projection_keeps_only_enum_and_combines_observation_samples(values, expected):
    assert combine_engine_activity(*values) == expected


def observed_activity(activity="idle", **extra):
    return raw(popup_keys=[], ui_monitor_available=True, turn_blockers=[],
               engine_activity=activity, **extra)


@pytest.mark.parametrize("activity", ["busy", "idle", "unknown", None, {"secret": True}])
@pytest.mark.parametrize("ui_kind", ["ready", "waiting", "decision", "popup"])
async def test_activity_does_not_change_status_or_action_capability(activity, ui_kind):
    initial = observed_activity(activity, active_turn=ui_kind != "waiting")
    responses = [initial]
    if ui_kind == "decision":
        initial["turn_blockers"] = ["ENDTURN_BLOCKING_RESEARCH"]
    if ui_kind == "popup":
        initial["popup_keys"] = ["boost"]
        responses.append(popup(engine_activity="idle"))
    service = FairGameService(UITransport(*responses))
    result = await service.get_player_state()
    assert result["ui"]["status"] == ui_kind
    assert result["ui"]["engine_activity"] == combine_engine_activity(activity)
    assert ("observation_token" in result) is (ui_kind != "waiting")
    assert "secret" not in json.dumps(result)


async def test_later_popup_context_busy_is_not_overwritten_by_initial_idle():
    initial = observed_activity()
    initial["popup_keys"] = ["boost"]
    service = FairGameService(UITransport(initial, popup(engine_activity="busy")))
    result = await service.get_player_state()
    assert result["ui"]["engine_activity"] == "busy"
    assert result["ui"]["status"] == "popup"
    assert result["ui"]["popups"][0]["buttons"][0]["action"]["type"] == "popup_action"


async def test_fixed_district_preview_context_activity_is_also_combined():
    service = FairGameService(UITransport(observed_activity("idle"),
        raw(category="district_preview", supported=True, items=[], engine_activity="busy")))
    result = await service.inspect_game("district_preview",
                                       {"city_id": 7, "item": "DISTRICT_CAMPUS"})
    assert result["ui"]["engine_activity"] == "busy"
    assert result["ui"]["status"] == "ready"
    assert result["supported"] is True
    assert "observation_token" in result


async def test_wait_reports_activity_change_without_replaying_action():
    transport = UITransport(observed_activity("busy"), observed_activity("idle"))
    service = FairGameService(transport)
    first = await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["wait"]["reason"] == "ui_changed"
    assert result["ui"]["engine_activity"] == "idle"
    assert result["observation_token"] != first["observation_token"]
    assert len(transport.calls) == 2
    assert not any("out.accepted" in script for script in transport.calls)


async def test_idle_does_not_itself_claim_observation_or_action_completion():
    class RepeatingUITransport(RepeatingTransport):
        supports_ui_contexts = True

    service = FairGameService(RepeatingUITransport(observed_activity("idle")))
    await service.get_player_state()
    result = await service.wait_for_change(20)
    assert result["wait"]["reason"] == "timeout"
    assert result["wait"]["changed"] is False
    assert "action_completed" not in result
    assert "accepted" not in result
