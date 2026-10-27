"""Cross-domain permissions, popup token scope and engine-context isolation."""
import asyncio
import json
import re

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.actions import build_action_query, validate_action
from civ6_fair_mcp.extensions import build_inspection_query, registries
from civ6_fair_mcp.extensions.base import lua as literal, validate
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import PolicyError
from civ6_fair_mcp.service import FairGameService
from civ6_fair_mcp.transport import FireTunerTransport, TransportError
from test_actions import engine, action_script
from test_service import FakeTransport, raw
from test_transport import frame, read_frame, markers, output
from civ6_fair_mcp.extensions.popups import build_popup_query


@pytest.mark.parametrize("value,schema", [
    (True, "id"), (-2, "signed_id"), (1.0, "id"), (4096, "coord"),
    (float("nan"), "number"), ([1,1], ["id"]), ([1]*129, ["id"]),
    ({"a":1,"b":2}, {"a":"id"}), ("TECH_X\n", "identifier:TECH_"),
    ("CITY_X", "identifier:TECH_"), ("bad\x00text", "text"), ("", "text"),
])
def test_strict_schema_rejection(value, schema):
    with pytest.raises(ValueError):
        validate(value, schema)


def test_unicode_literal_cannot_execute_lua():
    vm = LuaRuntime()
    value = '宗教"; hacked = true; -- \\ 🙂'
    encoded = literal(validate(value, "text"))
    assert vm.eval(encoded) == value
    assert vm.globals().hacked is None


def inspection(**extra):
    return raw(category="pending_decisions", supported=True, items=[], **extra)


def test_hidden_bad_items_are_discarded_before_validation():
    data = inspection()
    data["items"] = [
        {"scope":"self", "owner_id":1, "id":None, "value":{"secret":1}},
        {"scope":"met", "met":False, "id":None, "owner_id":999},
        {"scope":"visible", "visible":False, "id":None, "x":"secret"},
        {"scope":"visible", "visible":True, "detected":False, "id":None},
    ]
    assert public_inspection(data, "pending_decisions")["items"] == []


def test_new_fields_and_arbitrary_actions_do_not_pass_output_policy():
    data = inspection()
    data["items"] = [{"scope":"self", "owner_id":0,"id":"x", "secret":"hidden"}]
    assert public_inspection(data,"pending_decisions")["items"] == [{"id":"x"}]
    data["items"][0]["action"] = {"type":"run_lua","code":"x()"}
    with pytest.raises(PolicyError): public_inspection(data,"pending_decisions")


async def test_inspection_invalidates_token_and_rejects_unknown_parameters():
    transport = FakeTransport(raw())
    service = FairGameService(transport)
    token = (await service.get_player_state())["observation_token"]
    assert (await service.inspect_game("pending_decisions", {"player_id":1}))["error"] == "invalid_input"
    assert len(transport.calls) == 1
    assert (await service.act(token, {"type":"end_turn"}))["error"] == "fresh_observation_required"


async def test_inactive_popup_token_cannot_send_gameplay_action():
    data = inspection(active_turn=False, decision_mode="ui")
    service = FairGameService(FakeTransport(data))
    observed = await service.inspect_game("pending_decisions")
    assert observed["token_scope"] == "ui"
    assert (await service.act(observed["observation_token"], {"type":"end_turn"}))["error"] == "fresh_observation_required"
    assert len(service.transport.calls) == 1


async def test_other_query_cannot_forge_ui_capability():
    data = raw(active_turn=False, decision_mode="ui", category="unit_actions", supported=True, items=[])
    service = FairGameService(FakeTransport(data))
    result = await service.inspect_game("unit_actions", {"unit_id":1})
    assert "observation_token" not in result


def prepare_popup(vm, run):
    vm.execute('ExposedMembers={}; closed=0; function OnClose() closed=closed+1 end')
    run(action_script({"type":"end_turn"}))  # initialize InGame session
    vm.execute('''
local button={IsVisible=function() return true end, IsDisabled=function() return false end,
    GetText=function() return "继续" end}
Controls={CloseButton=button}
ContextPtr={GetID=function() return "TechCivicCompletedPopup" end,
    IsVisible=function() return true end, GetChildren=function() return {button} end}
''')
    return run(build_popup_query("test_nonce", "research_completed"))["popup"]["buttons"][0]["action"]


def test_popup_ack_uses_shared_session_and_real_close_even_while_busy(engine):
    vm, run = engine
    action = prepare_popup(vm, run)
    vm.execute('_CIV6FAIR_V1=nil; controls.busy=true')  # another Lua context has no private state
    result = run(action_script(action))
    assert result["accepted"] is True
    assert vm.globals().closed == 1
    vm.execute('load_event()')
    assert run(action_script(action, nonce="new"))["accepted"] is False
    assert vm.globals().closed == 1


@pytest.mark.parametrize("setup", [
    'ContextPtr.IsVisible=function() return false end',
    'ContextPtr.GetID=function() return "GameCore_Tuner" end',
    'ExposedMembers.Civ6FairState=nil',
])
def test_popup_ack_rejects_hidden_wrong_context_or_no_session(engine, setup):
    vm, run = engine
    action = prepare_popup(vm, run)
    vm.execute(setup)
    result = run(action_script(action))
    assert result.get("accepted") is not True
    assert vm.globals().closed == 0


async def test_popup_transport_routes_exact_context_and_filters_foreign_output():
    commands=[]
    async def handler(reader, writer):
        try:
            assert await read_frame(reader) == (4,"APP:")
            writer.write(frame("Civilization VI",4)); await writer.drain()
            assert await read_frame(reader) == (4,"LSQ:")
            writer.write(frame("17\x00InGame\x0022\x00TechCivicCompletedPopup",4)); await writer.drain()
            _, command=await read_frame(reader); commands.append(command)
            start, done=markers(command)
            writer.write(output(start,"TechCivicCompletedPopup")
                         + output('CIV6FAIR_JSON:{"hidden":true}',"InGame")
                         + output('CIV6FAIR_JSON:{"ok":true}',"TechCivicCompletedPopup")
                         + output("---END---","TechCivicCompletedPopup")
                         + output(done,"TechCivicCompletedPopup"))
            await writer.drain()
        finally:
            writer.close(); await writer.wait_closed()
    server=await asyncio.start_server(handler,"127.0.0.1",0)
    client=FireTunerTransport(port=server.sockets[0].getsockname()[1])
    try:
        result=await client.execute("authored()",context="TechCivicCompletedPopup")
        assert result == 'CIV6FAIR_JSON:{"ok":true}\n---END---'
        assert commands[0].startswith("CMD:22:")
        with pytest.raises(ValueError): await client.execute("bad()",context="GameCore_Tuner")
    finally:
        await client.close(); server.close(); await server.wait_closed()
