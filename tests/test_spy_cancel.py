"""Own spy cancellation follows UnitPanel's two checks without a fog-map read."""
import pytest

from test_extension_units import engine


def configure(vm):
    vm.execute('''
settings.visible=false;settings.revealed=true
settings.cancel_visible=true;settings.cancel_now=true;cancel_checks={}
Locale.Lookup=function(key)
    if key=='LOC_UNITPANEL_ESPIONAGE_CANCEL_MISSION' then return '取消间谍任务' end
    return key
end
Map.GetPlot=forbidden;CityManager.GetCityAt=forbidden;Cities.GetPlotPurchaseCity=forbidden
UnitManager.CanStartOperation=forbidden
UnitManager.CanStartCommand=function(actor,hash,exclusion,results)
    assert(actor==unit and actor:GetOwner()==0 and hash==UnitCommandTypes.CANCEL)
    cancel_checks[#cancel_checks+1]={exclusion=exclusion,results=results}
    if exclusion==true then assert(results==nil);return settings.cancel_visible end
    assert(exclusion==false and results==true)
    return settings.cancel_now,setmetatable({},{__index=forbidden})
end
''')


def test_fogged_owned_spy_offers_cancel_only_without_hidden_map_or_city_reads(engine):
    vm, run = engine
    configure(vm)
    out = run("unit_actions", {"unit_id": 10}, True)
    assert out["supported"] is True
    assert len(out["items"]) == 1
    assert out["items"][0]["id"] == "cancel"
    assert out["items"][0]["action"] == {"type": "unit_command", "unit_id": 10, "command": "cancel"}
    assert out["items"][0]["description"] == "取消间谍任务"
    assert len(vm.globals().cancel_checks) == 2
    assert vm.globals().reads.hidden == 0 and vm.globals().reads.plot == 0
    assert len(vm.globals().calls) == 0


def test_spy_cancel_submission_uses_no_position_or_city_getter(engine):
    vm, run = engine
    configure(vm)
    vm.execute("unit.GetX=forbidden;unit.GetY=forbidden")
    out = run("unit_command", {"unit_id": 10, "command": "cancel"})
    assert out["accepted"] is True
    call = vm.globals().calls[1]
    assert call["kind"] == "command" and call["op"] == vm.globals().UnitCommandTypes.CANCEL
    assert call["params"] is None
    assert len(vm.globals().cancel_checks) == 2 and vm.globals().reads.hidden == 0


@pytest.mark.parametrize("mutation", [
    "settings.cancel_visible=false", "settings.cancel_visible=nil", "settings.cancel_visible=1",
    "settings.cancel_now=false", "settings.cancel_now=nil", "settings.cancel_now=1",
    "settings.tactical=false", "settings.tactical=nil",
    "GameInfo.UnitCommands.UNITCOMMAND_CANCEL={VisibleInUI=false,Hash=UnitCommandTypes.CANCEL}",
])
def test_query_and_action_reject_when_normal_cancel_eligibility_is_missing(engine, mutation):
    vm, run = engine
    configure(vm)
    vm.execute(mutation)
    assert run("unit_actions", {"unit_id": 10}, True)["items"] == []
    assert run("unit_command", {"unit_id": 10, "command": "cancel"})["accepted"] is False
    assert len(vm.globals().calls) == 0 and vm.globals().reads.hidden == 0


def test_action_rechecks_current_command_state_after_a_valid_offer(engine):
    vm, run = engine
    configure(vm)
    offered = run("unit_actions", {"unit_id": 10}, True)["items"][0]["action"]
    vm.execute("settings.cancel_now=false")
    assert run("unit_command", {k: v for k, v in offered.items() if k != "type"})["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_non_spy_keeps_original_fog_visibility_requirement(engine):
    vm, run = engine
    configure(vm)
    vm.execute("GameInfo.Units[1].Spy=false;UnitManager.CanStartCommand=forbidden")
    assert run("unit_actions", {"unit_id": 10}, True)["items"] == []
    assert run("unit_command", {"unit_id": 10, "command": "cancel"})["accepted"] is False
    assert len(vm.globals().calls) == 0 and vm.globals().reads.hidden == 0


def test_foreign_spy_is_rejected_before_unit_type_or_location_access(engine):
    vm, run = engine
    configure(vm)
    vm.execute("settings.owner=1;unit.GetUnitType=forbidden;unit.GetX=forbidden;unit.GetY=forbidden")
    assert run("unit_actions", {"unit_id": 10}, True)["items"] == []
    assert run("unit_command", {"unit_id": 10, "command": "cancel"})["accepted"] is False
    assert len(vm.globals().cancel_checks) == 0 and vm.globals().reads.hidden == 0


@pytest.mark.parametrize("command", ["wake", "delete", "stop_automation", "upgrade"])
def test_fog_exception_does_not_authorize_other_spy_commands(engine, command):
    vm, run = engine
    configure(vm)
    assert run("unit_command", {"unit_id": 10, "command": command})["accepted"] is False
    assert len(vm.globals().calls) == 0 and vm.globals().reads.hidden == 0


def test_visible_spy_cancel_is_not_offered_again_by_generic_command_loop(engine):
    vm, run = engine
    vm.execute('''
settings.cancel_checks=0
UnitManager.CanStartCommand=function(actor,hash,exclusion,results)
    if hash~=UnitCommandTypes.CANCEL then return false end
    settings.cancel_checks=settings.cancel_checks+1
    if exclusion==true then assert(results==nil);return true end
    assert(exclusion==false and results==true);return true
end
UnitManager.CanStartOperation=function() return false end
GameInfo.Improvements=setmetatable({},{__call=function() return function() return nil end end})
''')
    out = run("unit_actions", {"unit_id": 10}, True)
    assert [row["id"] for row in out["items"]] == ["cancel"]
    assert vm.globals().settings.cancel_checks == 2
