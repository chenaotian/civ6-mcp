"""Own off-map spy lifecycle fields through a real Lua VM and public projection."""
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.spy_overview import ACTIONS, QUERIES
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.lua_common import wrap
from test_spy_menus import SPY_FIXTURE


SETUP = r'''
offmap={{Name='间谍甲',Level=2.0,ReturnTurn=12.0,XLocation=8.0,YLocation=2.0,
    OwningPlayer=0,Secret='SECRET_DATA'},
    setmetatable({ReturnTurn=-1,OwningPlayer=0},{__index=function() error('excluded spy fields read') end})}
offmap_reads=0;destination_reads=0
own_diplomacy={GetNumSpiesOffMap=function(self) assert(self==own_diplomacy);return #offmap end,
    GetNthOffMapSpy=function(self,owner,index)
        assert(self==own_diplomacy and owner==0 and index>=0 and index<#offmap)
        offmap_reads=offmap_reads+1;return offmap[index+1]
    end,
    GetSpyCapacity=function(self) assert(self==own_diplomacy);return 3.0 end}
player.GetDiplomacy=function() return own_diplomacy end
Game.GetPlayers=forbidden
foreign.GetDiplomacy=forbidden
player.GetUnits=nil
player.GetCities=forbidden
PlayersVisibility[0].IsRevealed=forbidden
PlayersVisibility[0].IsVisible=forbidden
Cities.GetPlotPurchaseCity=function(p)
    assert(p:GetX()==8 and p:GetY()==2)
    return {GetName=function() destination_reads=destination_reads+1;return '已派遣目的地' end,
        GetOwner=forbidden,GetID=forbidden,GetDistricts=forbidden,GetPopulation=forbidden}
end
'''


def execute(mutation=""):
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute(SPY_FIXTURE + SETUP + "\n" + mutation)
    output = []
    vm.globals().print = output.append
    body = 'out.category="spy_overview";out.items=array({});out.supported=false\n'
    body += LUA_HELPERS + '\nlocal function collect()\n' + QUERIES['spy_overview'].body({})
    body += '\nend\ncollect()'
    vm.execute(wrap(body, "spy_overview_test"))
    assert len(output) == 2
    result = json.loads(output[0].split(":", 1)[1])
    assert result.get("ok") is True, result
    assert "SECRET" not in json.dumps(result)
    return vm, result


def records(result):
    return {item["id"]: item for item in result["items"]}


def test_own_travelling_spy_survives_absence_from_map_units_and_public_projection():
    vm, raw = execute()
    assert raw["supported"] is True
    result = records(public_inspection(raw, "spy_overview"))
    assert result["travelling:0"]["name"] == "间谍甲"
    assert result["travelling:0"]["value"] == "TRAVELLING"
    assert result["travelling:0:rank"]["value"] == 2
    assert result["travelling:0:rank"]["name"] == "LOC_ESPIONAGE_LEVEL_2_NAME"
    assert type(result["travelling:0:rank"]["value"]) is int
    assert result["travelling:0:turns_remaining"]["value"] == 4
    assert result["travelling:0:destination"]["value"] == "已派遣目的地"
    assert result["travelling_count"]["value"] == 1
    assert result["capacity"]["value"] == 3
    assert not any("action" in item for item in raw["items"])
    assert all(item["scope"] == "self" and item["owner_id"] == 0 for item in raw["items"])
    assert vm.globals().offmap_reads == 2 and vm.globals().destination_reads == 1
    assert vm.globals().reads.hidden == 0
    assert not ACTIONS and not QUERIES["spy_overview"].fields


def test_no_travelling_spies_is_available_empty_list_not_missing_capability():
    vm, result = execute("offmap={}")
    assert result["supported"] is True
    assert records(result)["travelling_count"]["value"] == 0
    assert vm.globals().offmap_reads == 0 and vm.globals().destination_reads == 0


@pytest.mark.parametrize("mutation", [
    "player.GetDiplomacy=nil",
    "player.GetDiplomacy=function() return nil end",
    "player.GetDiplomacy=function() error('unavailable') end",
    "own_diplomacy.GetNumSpiesOffMap=nil",
    "own_diplomacy.GetNumSpiesOffMap=function() return -1 end",
    "own_diplomacy.GetNumSpiesOffMap=function() return 1.5 end",
    "own_diplomacy.GetNumSpiesOffMap=function() return math.huge end",
    "own_diplomacy.GetNumSpiesOffMap=function() return 129 end",
    "own_diplomacy.GetNthOffMapSpy=nil",
    "own_diplomacy.GetNthOffMapSpy=function() error('unavailable') end",
    "offmap[1].ReturnTurn=nil",
    "offmap[1].ReturnTurn=-2",
    "offmap[1].ReturnTurn=0/0",
    "offmap[1].Name=nil",
    "offmap[1].Level=nil",
    "offmap[1].Level=2.5",
    "offmap[2]=42",
])
def test_missing_or_inconsistent_own_snapshot_fails_closed_without_partial_records(mutation):
    _, result = execute(mutation)
    assert result["supported"] is False and result["items"] == []


def test_contradictory_owner_is_rejected_before_identity_or_location_reads():
    vm, result = execute("offmap={setmetatable({OwningPlayer=1},{__index=forbidden})}")
    assert result["supported"] is False and result["items"] == []
    assert vm.globals().reads.hidden == 0 and vm.globals().destination_reads == 0


@pytest.mark.parametrize("mutation", [
    "Map.GetPlot=nil",
    "Cities.GetPlotPurchaseCity=nil",
    "Cities.GetPlotPurchaseCity=function() return nil end",
    "Cities.GetPlotPurchaseCity=function() return {GetName=function() error('unavailable') end} end",
    "offmap[1].XLocation=-1",
    "offmap[1].YLocation=2.5",
])
def test_unknown_destination_is_omitted_without_guessing_or_losing_trip(mutation):
    _, result = execute(mutation)
    assert result["supported"] is True
    values = records(result)
    assert "travelling:0" in values and "travelling:0:destination" not in values


@pytest.mark.parametrize("mutation", [
    "own_diplomacy.GetSpyCapacity=nil",
    "own_diplomacy.GetSpyCapacity=function() return nil end",
    "own_diplomacy.GetSpyCapacity=function() return -1 end",
])
def test_missing_capacity_is_unknown_not_zero(mutation):
    _, result = execute(mutation)
    assert result["supported"] is True and "capacity" not in records(result)


@pytest.mark.parametrize("level,expected", [(0, 1), (1, 1), (3, 3), (4, 4), (5, 1)])
def test_rank_follows_original_ui_fixed_mapping(level, expected):
    _, result = execute(f"offmap[1].Level={level}")
    assert records(result)["travelling:0:rank"]["value"] == expected


def test_arrival_transition_remaining_turns_does_not_become_negative():
    _, result = execute("offmap[1].ReturnTurn=7")
    assert records(result)["travelling:0:turns_remaining"]["value"] == 0


def test_nil_entry_matches_original_ui_skip_and_other_spies_still_available():
    _, result = execute("local prior=own_diplomacy.GetNthOffMapSpy;own_diplomacy.GetNthOffMapSpy=function(self,owner,index) if index==1 then return nil end;return prior(self,owner,index) end")
    assert result["supported"] is True
    assert records(result)["travelling_count"]["value"] == 1


STATIONED = r'''
offmap={}
settings.unit_x=9;settings.unit_y=2
local rows={}
for _,row in pairs(GameInfo.UnitOperations) do rows[row.Index]=row end
for index,row in pairs(rows) do GameInfo.UnitOperations[index]=row end
active_operation=GameInfo.UnitOperations.UNITOPERATION_SPY_SIPHON_FUNDS.Index
unit.GetName=function() return '在岗间谍' end
unit.GetExperience=function() return {GetLevel=function() return 3.0 end} end
unit.GetSpyOperation=function() return active_operation end
unit.GetSpyOperationEndTurn=function() return 13.0 end
unit.GetMovesRemaining=forbidden;unit.IsReadyToMove=forbidden
foreign_unit=setmetatable({GetOwner=function() return 1 end},{__index=forbidden})
player.GetUnits=function() return {Members=function() return members({foreign_unit,unit}) end} end
spy_city={GetName=function() return '目标城' end,GetX=function() return 8 end,GetY=function() return 2 end,
    GetOwner=forbidden,GetID=forbidden,GetDistricts=forbidden,GetPopulation=forbidden}
Cities.GetPlotPurchaseCity=function(p)
    assert(p:GetX()==9 and p:GetY()==2,'current city must come from own spy plot')
    return spy_city
end
district_reads=0;details_reads=0;total_reads=0
Map.GetPlot=function(x,y)
    assert((x==8 or x==9) and y==2,'unexpected target plot')
    local p=plot(x,y)
    p.GetDistrictType=function()
        assert(x==9,'current district must come from own spy plot')
        district_reads=district_reads+1;return 2
    end
    return p
end
UnitManager.CanStartOperation=forbidden
UnitManager.GetResultProbability=forbidden
UnitManager.GetTimeToComplete=function(index,u)
    assert(index==active_operation and u==unit)
    total_reads=total_reads+1;return 8.0
end
UnitManager.GetOperationDetailText=function(index,u,p)
    assert(index==active_operation and u==unit and p:GetX()==8 and p:GetY()==2,
        'effect details use the city center, not the current district')
    details_reads=details_reads+1;return '120'
end
'''


def test_active_spy_details_are_readable_with_no_moves_and_match_overview_plot_bindings():
    vm, raw = execute(STATIONED)
    assert raw["supported"] is True
    values = records(public_inspection(raw, "spy_overview"))
    assert values["stationed:10"]["value"] == 10
    assert values["stationed:10"]["name"] == "在岗间谍"
    assert values["stationed:10:city"]["value"] == "目标城"
    assert values["stationed:10:rank"]["name"] == "LOC_ESPIONAGE_LEVEL_3_NAME"
    assert values["stationed:10:mission"]["value"] == "UNITOPERATION_SPY_SIPHON_FUNDS"
    assert values["stationed:10:turns_remaining"]["value"] == 5
    assert values["stationed:10:total_turns"]["value"] == 8
    assert values["stationed:10:target_district"]["value"] == "DISTRICT_CAMPUS"
    assert values["stationed:10:effect"]["description"] == "LOC_SPYMISSIONDETAILS_UNITOPERATION_SPY_SIPHON_FUNDS[目标城,120]"
    assert values["stationed_count"]["value"] == 1
    assert vm.globals().district_reads == vm.globals().details_reads == vm.globals().total_reads == 1
    assert vm.globals().reads.hidden == 0
    assert not any("action" in item for item in raw["items"])


def test_counterspy_effect_uses_current_district_caption_without_offensive_detail_or_probability():
    vm, raw = execute(STATIONED + "\nactive_operation=GameInfo.UnitOperations.UNITOPERATION_SPY_COUNTERSPY.Index;UnitManager.GetOperationDetailText=forbidden")
    values = records(raw)
    assert values["stationed:10:effect"]["description"] == "LOC_ESPIONAGECHOOSER_COUNTERSPY[Campus]"
    assert vm.globals().reads.hidden == 0 and vm.globals().details_reads == 0


def test_idle_spy_only_has_city_and_no_current_mission_target_or_effect():
    vm, raw = execute(STATIONED + "\nactive_operation=-1;UnitManager.GetTimeToComplete=forbidden;UnitManager.GetOperationDetailText=forbidden")
    values = records(raw)
    assert values["stationed:10:mission"]["value"] == "NONE"
    assert values["stationed:10:city"]["value"] == "目标城"
    assert "stationed:10:target_district" not in values and "stationed:10:effect" not in values
    assert vm.globals().district_reads == 0 and vm.globals().reads.hidden == 0


@pytest.mark.parametrize("mutation,missing", [
    ("unit.GetSpyOperation=nil", ["mission", "effect", "target_district"]),
    ("unit.GetSpyOperationEndTurn=nil", ["turns_remaining"]),
    ("UnitManager.GetTimeToComplete=nil", ["total_turns"]),
    ("UnitManager.GetOperationDetailText=nil", ["effect"]),
    ("UnitManager.GetOperationDetailText=function() error('unavailable') end", ["effect"]),
    ("spy_city.GetX=nil", ["effect"]),
    ("Cities.GetPlotPurchaseCity=function() return nil end", ["city", "effect"]),
    ("unit.GetExperience=nil", ["rank"]),
])
def test_optional_stationed_fields_are_omitted_without_losing_identity(mutation, missing):
    _, raw = execute(STATIONED + "\n" + mutation)
    values = records(raw)
    assert "stationed:10" in values
    assert all("stationed:10:" + suffix not in values for suffix in missing)


def test_unknown_current_operation_cannot_expand_into_an_arbitrary_details_query():
    vm, raw = execute(STATIONED + "\nGameInfo.UnitOperations[active_operation]={Index=active_operation,OperationType='UNITOPERATION_EXECUTE_SCRIPT'};UnitManager.GetOperationDetailText=forbidden")
    values = records(raw)
    assert "stationed:10:mission" not in values and "stationed:10:effect" not in values
    assert vm.globals().reads.hidden == 0 and vm.globals().district_reads == 0


def test_off_map_coordinates_are_not_queried_by_stationed_path():
    vm, raw = execute(STATIONED + "\nsettings.unit_x=-1;Map.GetPlot=forbidden")
    values = records(raw)
    assert "stationed:10" not in values and values["stationed_count"]["value"] == 0
    assert vm.globals().reads.hidden == 0


def test_broken_optional_map_iterator_preserves_valid_travelling_snapshot():
    _, raw = execute("player.GetUnits=function() return {Members=function() error('unavailable') end} end")
    values = records(raw)
    assert raw["supported"] is True and "travelling:0" in values
    assert "stationed_count" not in values


@pytest.mark.parametrize("mutation", [
    "unit.GetOwner=nil",
    "unit.GetUnitType=nil",
    "unit.GetUnitType=function() return 999 end",
    "unit.GetX=nil",
    "unit.GetY=function() return 0/0 end",
])
def test_incomplete_map_ownership_or_position_does_not_claim_zero_stationed_spies(mutation):
    _, raw = execute(STATIONED + "\n" + mutation)
    values = records(raw)
    assert raw["supported"] is True and "travelling_count" in values
    assert not any(key.startswith("stationed") for key in values)


@pytest.mark.parametrize("mission", ["SPY_GAIN_SOURCES", "SPY_LISTENING_POST"])
def test_stationed_empty_effect_gets_original_static_fallback(mission):
    _, raw = execute(STATIONED + f"\nactive_operation=GameInfo.UnitOperations.UNITOPERATION_{mission}.Index;UnitManager.GetOperationDetailText=function() return '' end")
    assert records(raw)["stationed:10:effect"]["description"] == "LOC_SPYMISSIONDETAILS_UNITOPERATION_" + mission
