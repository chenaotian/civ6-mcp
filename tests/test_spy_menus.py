"""Execute the stock-menu spy boundary in a real Lua VM, with permissive core.

The fixture deliberately says that excluded destinations/forged actions can
start. Menu membership, rather than this permissive answer, must stop them.
"""
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS, lua, own_unit
from civ6_fair_mcp.extensions.spy_menus import (
    spy_body, spy_destinations, spy_options, spy_travel_body,
)
from civ6_fair_mcp.extensions.units import HELPERS, SPY_MISSIONS
from civ6_fair_mcp.lua_common import wrap


SPY_FIXTURE = r'''
settings={rules="RULESET_EXPANSION_2",revealed=true,visible=false,entry=true,
    moves=2,can=true,travel_can=true,unit_x=2,unit_y=2,foreign_state=1,
    foreign_team=-1,own_team=0,free=false,major=true,unit_owner=0,awake=true}
reads={hidden=0,plots=0,mission_checks=0,names=0}
calls={}; checks={}
function forbidden() reads.hidden=reads.hidden+1; error("SECRET_HIDDEN_DATA") end
function members(values)
    local i=0; return function() i=i+1; if values[i] then return i,values[i] end end
end
GameConfiguration={IsAnyMultiplayer=function() return false end,IsHotseat=function() return false end,
    IsWorldBuilderEditor=function() return false end,GetValue=function(key) assert(key=="RULESET"); return settings.rules end}
Automation={IsActive=function() return false end}
Events={LoadGameViewStateDone={Add=function() end},LocalPlayerChanged={Add=function() end}}
Locale={Lookup=function(text,...)
    local args={...}
    return #args>0 and (text.."["..table.concat(args,",").."]") or text
end,ToUpper=string.upper}
UI={IsProcessingMessages=function() return false end}
UnitOperationTypes={PARAM_X="x",PARAM_Y="y"}
UnitOperationResults={PLOTS="plots",FAILURE_REASONS="failure"}
OperationResultsTypes={NO_TARGETS=77}
ActivityTypes={ACTIVITY_AWAKE=1}
GameInfo={UnitOperations={},Units={[1]={Spy=true}},DiplomaticStates={
    [1]={StateType="DIPLO_STATE_NEUTRAL"},[2]={StateType="DIPLO_STATE_ALLIED"}},
    Districts={[1]={DistrictType="DISTRICT_CITY_CENTER",Name="City Center"},
        [2]={DistrictType="DISTRICT_CAMPUS",Name="Campus"},
        [3]={DistrictType="DISTRICT_WONDER",Name="Hidden Wonder"}}}
function plot(x,y)
    return {GetX=function() return x end,GetY=function() return y end,GetIndex=function() return y*100+x end}
end
function district(x,y,kind,complete)
    return {GetX=function() return x end,GetY=function() return y end,
        GetType=function() return kind end,IsComplete=function() return complete end}
end
function make_city(owner,id,x,y,name,hidden)
    local list={district(x,y,1,true),district(x+1,y,2,true),district(x+2,y,3,true),district(x+3,y,2,false)}
    local function allowed()
        if hidden or (owner==1 and not settings.revealed) then forbidden() end
    end
    return {GetX=function() return x end,GetY=function() return y end,
        GetOwner=function() allowed(); return owner end,GetID=function() allowed(); return id end,
        GetName=function() allowed(); reads.names=reads.names+1; return name end,
        GetDistricts=function() allowed(); return {Members=function() return members(list) end} end,
        _districts=list}
end
own_city=make_city(0,20,2,2,"Home")
foreign_city=make_city(1,21,8,2,"Fogged City")
hidden_city=make_city(1,22,12,2,"SECRET_CITY",true)
own_cities={own_city}; foreign_cities={foreign_city,hidden_city}
unit={GetOwner=function() return settings.unit_owner end,
    GetID=function() if settings.unit_owner~=0 then forbidden() end; return 10 end,
    GetUnitType=function() if settings.unit_owner~=0 then forbidden() end; return 1 end,
    GetX=function() return settings.unit_x end,GetY=function() return settings.unit_y end,
    GetMovesRemaining=function() return settings.moves end,
    IsReadyToMove=function() return settings.awake and settings.moves>0 end}
player={GetID=function() return 0 end,GetTeam=function() return settings.own_team end,
    IsAlive=function() return true end,IsHuman=function() return true end,
    IsTurnActive=function() return true end,IsTurnActiveComplete=function() return true end,
    IsMajor=function() return true end,IsFreeCities=function() return false end,
    GetDiplomaticAI=function() return {GetDiplomaticStateIndex=function() return 1 end} end,
    GetUnits=function() return {Members=function() return members({unit}) end} end,
    GetCities=function() return {Members=function() return members(own_cities) end} end,
    GetDiplomacy=function() return {HasMet=forbidden} end}
foreign={GetID=function() return 1 end,GetTeam=function() return settings.foreign_team end,
    IsMajor=function() return settings.major end,IsFreeCities=function() return settings.free end,
    GetDiplomaticAI=function() return {GetDiplomaticStateIndex=function() return settings.foreign_state end} end,
    GetCities=function() return {Members=function() return members(foreign_cities) end} end}
Players={[0]=player,[1]=foreign}
Game={GetLocalPlayer=function() return 0 end,GetLocalObserver=function() return 0 end,
    GetCurrentGameTurn=function() return 8 end,IsAllowTacticalCommands=function() return true end,
    GetPlayers=function() return {player,foreign} end}
PlayersVisibility={[0]={IsRevealed=function(self,x,y)
        if x==12 and y==2 then return false end
        if x==8 and y==2 then return settings.revealed end
        return true
    end,IsVisible=function() return settings.visible end}}
Map={GetGridSize=function() return 100,80 end,
    GetPlot=function(x,y)
        assert(not (x==12 and y==2),"unrevealed city plot read")
        reads.plots=reads.plots+1; return plot(x,y)
    end,
    GetPlotByIndex=function(index)
        reads.plots=reads.plots+1
        if settings.invalid_plot then return nil end
        return plot(index%100,math.floor(index/100))
    end}
Cities={GetPlotPurchaseCity=function(p)
    local x,y=p:GetX(),p:GetY()
    if y==2 and x>=2 and x<=5 then return own_city end
    if y==2 and x>=8 and x<=11 then return foreign_city end
end}
CityManager={GetCityAt=forbidden}
UnitManager={GetActivityType=function() return settings.awake and 1 or 2 end,
    CanStartOperation=function(u,hash,p,params,results)
        checks[#checks+1]={hash=hash,plot=p,params=params,results=results}
        if p==nil then return settings.entry end
        local row=GameInfo.UnitOperations[hash]
        if row.OperationType=="UNITOPERATION_SPY_TRAVEL_NEW_CITY" then
            assert(type(params)=="table" and results==nil)
            return settings.travel_can
        end
        assert(params==false and results==true,"wrong mission chooser signature")
        reads.mission_checks=reads.mission_checks+1
        if not settings.can then return false,{failure={"Menu reason"},secret=forbidden} end
        local x,y=p:GetX(),p:GetY()
        if settings.target_indices then return true,{plots=settings.target_indices,secret=forbidden} end
        if settings.empty_plots then return true,{plots={},secret=forbidden} end
        if row.OperationType=="UNITOPERATION_SPY_COUNTERSPY" then
            return true,{plots={y*100+x,y*100+x+1},secret=forbidden}
        end
        if row.OperationType=="UNITOPERATION_SPY_GAIN_SOURCES" or row.OperationType=="UNITOPERATION_SPY_LISTENING_POST" then
            return true,{secret=forbidden}
        end
        return true,{plots={y*100+x+1},secret=forbidden}
    end,
    RequestOperation=function(u,hash,params) calls[#calls+1]={hash=hash,params=params} end,
    GetTravelTime=function() return 3 end,GetEstablishInCityTime=function() return 2 end,
    GetTimeToComplete=function(index,u) assert(index<100); return 8 end,
    GetOperationDetailText=function(index,u,p) assert(index<100); return "Menu mission details" end,
    GetResultProbability=function(index,u,p) assert(index<100); return {
        ESPIONAGE_SUCCESS_UNDETECTED=.4,ESPIONAGE_SUCCESS_MUST_ESCAPE=.2,SECRET=forbidden} end}
'''
SPY_FIXTURE += "\nlocal mission_names=" + lua(list(SPY_MISSIONS) + ["SPY_TRAVEL_NEW_CITY"]) + r'''
for index,name in ipairs(mission_names) do
    local row={Hash=1000+index,Index=index,VisibleInUI=true,OperationType="UNITOPERATION_"..name,
        Description=name,CategoryInUI=(name=="SPY_COUNTERSPY" or name=="SPY_TRAVEL_NEW_CITY") and "MOVE" or "OFFENSIVESPY"}
    GameInfo.UnitOperations["UNITOPERATION_"..name]=row; GameInfo.UnitOperations[row.Hash]=row
end
'''


@pytest.fixture
def spy_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute(SPY_FIXTURE)
    output = []
    vm.globals().print = output.append

    def run(kind, **values):
        functions = {"mission": spy_body, "travel": spy_travel_body,
                     "options": spy_options, "destinations": spy_destinations}
        params = {"unit_id": 10, "x": 8, "y": 2, "offset": 0,
                  "mission": "SPY_GAIN_SOURCES", **values}
        body = 'out.items=array({}); out.supported=true; out.accepted=false\n'
        body += 'local function attempt(fn,...) fn(...); out.accepted=true end\n'
        body += LUA_HELPERS + '\nlocal function execute()\n' + HELPERS + own_unit(10)
        body += functions[kind](params) + '\nend\nexecute()'
        output.clear()
        vm.execute(wrap(body, "spy_menu_test"))
        assert len(output) == 2 and "SECRET" not in output[0]
        result = json.loads(output[0].split(":", 1)[1])
        assert result.get("ok") is True, result
        return result

    return vm, run


def missions(result):
    return [item for item in result["items"] if item["id"].startswith("SPY_")]


def test_revealed_fogged_destinations_have_exact_menu_proof(spy_engine):
    vm, run = spy_engine
    result = run("destinations")
    foreign = next(item for item in result["items"] if item["id"] == "spy:8:2")
    assert foreign["name"] == "Fogged City"
    assert foreign["action"]["type"] == "spy_travel"
    assert "Campus" in foreign["description"] and "Hidden Wonder" not in foreign["description"]
    assert foreign["description"].count("Campus") == 1  # Incomplete campus omitted.
    assert vm.globals().reads.hidden == 0
    for item in result["items"]:
        assert {k: item[k] for k in ("scope", "menu_owner_id", "menu_source", "menu_offered", "menu_unit_id")} == {
            "scope": "menu", "menu_owner_id": 0, "menu_source": "spy", "menu_offered": True, "menu_unit_id": 10}


@pytest.mark.parametrize("change", [
    "settings.revealed=false", "settings.foreign_state=-1", "settings.foreign_state=2",
    "settings.foreign_team=0", "settings.free=true",
])
def test_exact_city_exclusions_override_permissive_engine(spy_engine, change):
    vm, run = spy_engine
    vm.execute(change)
    assert not any(i["id"] == "spy:8:2" for i in run("destinations")["items"])
    assert run("travel")["accepted"] is False
    assert run("options")["items"] == []
    assert vm.globals().reads.hidden == 0 and len(vm.globals().calls) == 0


@pytest.mark.parametrize("rules,major,expected", [
    ("RULESET_STANDARD", False, False), ("RULESET_STANDARD", True, True),
    ("RULESET_EXPANSION_1", False, True), ("RULESET_EXPANSION_2", False, True),
])
def test_ruleset_controls_city_state_destination_membership(spy_engine, rules, major, expected):
    vm, run = spy_engine
    vm.globals().settings.rules, vm.globals().settings.major = rules, major
    assert run("travel")["accepted"] is expected


@pytest.mark.parametrize("change", [
    'settings.rules="RULESET_CUSTOM"', "GameConfiguration.GetValue=nil",
    "Game.GetPlayers=nil", "foreign.GetDiplomaticAI=nil", "foreign.IsFreeCities=nil",
    "UnitOperationResults.PLOTS=nil", "UnitManager.CanStartOperation=nil",
    "foreign_city.GetDistricts=nil", "Map.GetPlotByIndex=nil", "UnitOperationTypes.PARAM_X=nil",
    "GameInfo.Districts=nil",
])
def test_missing_menu_capability_is_not_reported_as_supported(spy_engine, change):
    vm, run = spy_engine
    vm.execute(change)
    assert run("destinations")["supported"] is False
    assert len(vm.globals().calls) == 0


def test_remote_city_tasks_are_previews_without_actions(spy_engine):
    vm, run = spy_engine
    entries = missions(run("options"))
    assert len(entries) == len(SPY_MISSIONS) - 1
    assert all("action" not in item and item["value"] is False for item in entries)
    assert all("Menu mission details" in item["description"] for item in entries)
    assert all("Success: 60%" in item["description"] for item in entries)
    assert run("mission")["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("mission", [m for m in SPY_MISSIONS if m != "SPY_COUNTERSPY"])
def test_offensive_current_city_actions_use_menu_target_and_no_parameter_request(spy_engine, mission):
    vm, run = spy_engine
    vm.globals().settings.unit_x = 8
    item = next(i for i in missions(run("options")) if i["id"].startswith(mission + ":"))
    action = dict(item["action"])
    action.pop("type")
    assert run("mission", **action)["accepted"] is True
    assert len(vm.globals().calls) == 1
    call = vm.globals().calls[1]
    assert call["hash"] == vm.globals().GameInfo.UnitOperations["UNITOPERATION_" + mission]["Hash"]
    assert call["params"] is None


def test_city_center_query_discovers_fogged_district_actions(spy_engine):
    vm, run = spy_engine
    vm.globals().settings.unit_x = 8
    item = next(i for i in missions(run("options")) if i["id"] == "SPY_SIPHON_FUNDS:9:2")
    assert item["action"]["x"] == 9 and "Campus" in item["description"]
    # A caller does not get to change the displayed target to the city center.
    assert run("mission", mission="SPY_SIPHON_FUNDS", x=8)["accepted"] is False
    assert run("mission", mission="SPY_SIPHON_FUNDS", x=9)["accepted"] is True


def test_specific_target_query_matches_menu_rows_only(spy_engine):
    vm, run = spy_engine
    vm.globals().settings.unit_x = 8
    assert all(i["action"]["x"] == 9 for i in missions(run("options", x=9)))
    assert run("options", x=98, y=77)["items"] == []
    assert run("mission", x=98, y=77)["accepted"] is False


def test_counterspy_only_accepts_own_city_matching_districts(spy_engine):
    vm, run = spy_engine
    entries = missions(run("options", x=2))
    assert {i["id"] for i in entries} == {"SPY_COUNTERSPY:2:2", "SPY_COUNTERSPY:3:2"}
    assert run("mission", mission="SPY_COUNTERSPY", x=3)["accepted"] is True
    assert dict(vm.globals().calls[1]["params"]) == {"x": 3, "y": 2}
    vm.execute("settings.target_indices={209}")  # Engine returns a foreign district.
    assert missions(run("options", x=2)) == []
    assert run("mission", mission="SPY_COUNTERSPY", x=9)["accepted"] is False


def test_no_counterspy_for_foreign_city_and_no_offense_for_own_city(spy_engine):
    vm, run = spy_engine
    assert run("mission", x=2)["accepted"] is False
    vm.globals().settings.unit_x = 8
    assert run("mission", mission="SPY_COUNTERSPY", x=9)["accepted"] is False


def test_failed_offensive_mission_has_public_reason_without_action(spy_engine):
    vm, run = spy_engine
    vm.execute("settings.unit_x=8; settings.can=false")
    entries = missions(run("options"))
    assert entries and all("Menu reason" in i["description"] and "action" not in i for i in entries)
    assert all("Turns: 8" in i["description"] and "Success: 60%" in i["description"] for i in entries)
    assert all("Menu mission details" not in i["description"] for i in entries)
    assert run("mission")["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_counterspy_never_queries_hidden_offensive_stats_or_details(spy_engine):
    vm, run = spy_engine
    vm.execute("UnitManager.GetTimeToComplete=forbidden; UnitManager.GetOperationDetailText=forbidden; UnitManager.GetResultProbability=forbidden")
    entries = missions(run("options", x=2))
    assert len(entries) == 2 and all("action" in item for item in entries)
    assert all("Turns:" not in item["description"] and "Success:" not in item["description"] for item in entries)
    assert vm.globals().reads.hidden == 0


def test_siphon_details_format_amount_with_public_city_name(spy_engine):
    vm, run = spy_engine
    vm.execute('UnitManager.GetOperationDetailText=function(index,u,p) return "120" end')
    entry = next(i for i in missions(run("options")) if i["id"].startswith("SPY_SIPHON_FUNDS:"))
    assert "LOC_SPYMISSIONDETAILS_UNITOPERATION_SPY_SIPHON_FUNDS[FOGGED CITY,120]" in entry["description"]
    assert not entry["description"].endswith("; 120")


@pytest.mark.parametrize("mission", ["SPY_LISTENING_POST", "SPY_GAIN_SOURCES"])
def test_empty_operation_detail_uses_stock_localized_effect(mission, spy_engine):
    vm, run = spy_engine
    vm.execute('UnitManager.GetOperationDetailText=function(index,u,p) return "" end')
    entry = next(i for i in missions(run("options")) if i["id"].startswith(mission + ":"))
    assert "LOC_SPYMISSIONDETAILS_UNITOPERATION_" + mission in entry["description"]


@pytest.mark.parametrize("setting", ["empty_plots", "invalid_plot"])
def test_offensive_no_valid_plot_falls_back_to_city_center(spy_engine, setting):
    vm, run = spy_engine
    vm.globals().settings.unit_x = 8
    vm.globals().settings[setting] = True
    assert run("mission", mission="SPY_SIPHON_FUNDS", x=8)["accepted"] is True
    assert run("mission", mission="SPY_SIPHON_FUNDS", x=9)["accepted"] is False


def test_missing_counterspy_targets_do_not_invent_center_fallback(spy_engine):
    vm, run = spy_engine
    vm.globals().settings.empty_plots = True
    assert missions(run("options", x=2)) == []
    assert run("mission", mission="SPY_COUNTERSPY", x=2)["accepted"] is False


@pytest.mark.parametrize("change", ["settings.moves=0", "settings.awake=false; settings.entry=false"])
def test_inaccessible_menus_do_not_offer_or_execute_operations(spy_engine, change):
    vm, run = spy_engine
    vm.execute("settings.unit_x=8; " + change)
    assert run("options")["items"] == []
    assert run("mission")["accepted"] is False
    assert run("travel")["accepted"] is False


def test_manual_unit_panel_path_can_open_sleeping_spy_menu(spy_engine):
    vm, run = spy_engine
    vm.execute("settings.unit_x=8; settings.awake=false; settings.entry=true")
    assert run("mission")["accepted"] is True


def test_destination_can_be_listed_without_travel_action(spy_engine):
    vm, run = spy_engine
    vm.globals().settings.travel_can = False
    entry = next(i for i in run("destinations")["items"] if i["id"] == "spy:8:2")
    assert "action" not in entry
    assert run("travel")["accepted"] is False


def test_current_own_city_confirmation_is_not_a_travel_request(spy_engine):
    vm, run = spy_engine
    assert run("travel", x=2)["accepted"] is False
    assert "action" not in next(i for i in run("destinations")["items"] if i["id"] == "spy:2:2")


def test_candidate_pagination_counts_only_public_menu_cities(spy_engine):
    vm, run = spy_engine
    vm.execute('for i=1,70 do foreign_cities[#foreign_cities+1]=make_city(1,100+i,i,4,"Public "..i) end')
    first = run("destinations")
    assert len(first["items"]) == 65
    assert first["items"][-1]["value"] == 64
    second = run("destinations", offset=64)
    assert len(second["items"]) == 9  # 72 public cities, hidden city excluded.
    assert second["items"][-1]["value"] == -1
    first_ids = {i["id"] for i in first["items"][:-1]}
    assert first_ids.isdisjoint(i["id"] for i in second["items"][:-1])


def test_action_rechecks_diplomacy_and_targets_after_observation(spy_engine):
    vm, run = spy_engine
    assert next(i for i in run("destinations")["items"] if i["id"] == "spy:8:2")["action"]
    vm.globals().settings.foreign_state = 2
    assert run("travel")["accepted"] is False
    vm.execute("settings.foreign_state=1; settings.unit_x=8")
    assert next(i for i in missions(run("options")) if i["id"] == "SPY_SIPHON_FUNDS:9:2")["action"]
    vm.globals().settings.empty_plots = True
    assert run("mission", mission="SPY_SIPHON_FUNDS", x=9)["accepted"] is False


def test_foreign_actor_rejected_before_identity_and_spy_fields(spy_engine):
    vm, run = spy_engine
    vm.globals().settings.unit_owner = 1
    assert run("destinations")["items"] == []
    assert run("mission")["accepted"] is False
    assert vm.globals().reads.hidden == 0


def test_native_float_ids_and_coordinates_emit_strict_integer_actions(spy_engine):
    vm, run = spy_engine
    vm.execute('''
        unit.GetID=function() return 10.0 end
        foreign_city.GetX=function() return 8.0 end
        foreign_city.GetY=function() return 2.0 end
        foreign_city.GetID=function() return 21.0 end
        settings.target_indices={209.0}
    ''')
    destination = next(i for i in run("destinations")["items"] if i["id"] == "spy:8:2")
    for field in ("unit_id", "x", "y"):
        assert type(destination["action"][field]) is int
    assert type(destination["menu_unit_id"]) is int
    vm.globals().settings.unit_x = 8.0
    action = next(i for i in missions(run("options")) if i["id"] == "SPY_SIPHON_FUNDS:9:2")
    for field in ("unit_id", "x", "y"):
        assert type(action["action"][field]) is int
    assert type(action["menu_unit_id"]) is int


@pytest.mark.parametrize("value", ["8.5", "-1", "4096", "0/0"])
def test_invalid_city_coordinate_is_never_returned_as_menu_candidate(spy_engine, value):
    vm, run = spy_engine
    vm.execute("foreign_city.GetX=function() return " + value + " end")
    assert not any(i["name"] == "Fogged City" for i in run("destinations")["items"] if "name" in i)
    assert run("travel")["accepted"] is False


SOURCES = r'''
source_reads=0;source_turns=7.0
player.GetDiplomacy=function() return {GetSourceTurnsRemaining=function(self,city)
    assert(city==foreign_city,'sources must bind to the current mission city')
    source_reads=source_reads+1;return source_turns
end} end
'''


@pytest.mark.parametrize("turns", [0, 7])
def test_sources_remaining_is_current_mission_menu_information_only(spy_engine, turns):
    from civ6_fair_mcp.inspection_policy import public_inspection
    vm, run = spy_engine
    vm.execute(SOURCES + f"\nsettings.unit_x=8;source_turns={turns}.0")
    raw = run("options")
    entry = next(row for row in raw["items"] if row["id"] == "sources_turns_remaining")
    assert entry["value"] == turns and type(entry["value"]) is int
    assert entry["scope"] == "menu" and entry["menu_unit_id"] == 10
    assert "action" not in entry and vm.globals().source_reads == 1
    raw["category"] = "spy_missions"
    raw["session"] = "spy_sources_projection_test"
    projected = public_inspection(raw, "spy_missions")
    assert next(row for row in projected["items"] if row["id"] == "sources_turns_remaining")["value"] == turns


@pytest.mark.parametrize("kind,mutation", [
    ("destinations", ""),
    ("options", ""),  # A foreign destination preview while still at home.
    ("options", "settings.unit_x=8;settings.moves=0"),
    ("options", "settings.unit_x=8;settings.awake=false;settings.entry=false"),
])
def test_remote_or_inaccessible_mission_menu_never_reads_source_status(spy_engine, kind, mutation):
    vm, run = spy_engine
    vm.execute(SOURCES + "\n" + mutation)
    result = run(kind)
    assert not any(row["id"] == "sources_turns_remaining" for row in result["items"])
    assert vm.globals().source_reads == 0


@pytest.mark.parametrize("mutation", [
    "source_turns=nil",
    "source_turns=-1",
    "source_turns=1.5",
    "source_turns=math.huge",
    "player.GetDiplomacy=nil",
    "player.GetDiplomacy=function() return 42 end",
    "player.GetDiplomacy=function() return {} end",
    "player.GetDiplomacy=function() return {GetSourceTurnsRemaining=function() error('unavailable') end} end",
])
def test_optional_source_status_failure_does_not_remove_mission_options(spy_engine, mutation):
    vm, run = spy_engine
    vm.execute(SOURCES + "\nsettings.unit_x=8\n" + mutation)
    result = run("options")
    assert result["supported"] is True and missions(result)
    assert not any(row["id"] == "sources_turns_remaining" for row in result["items"])


def test_optional_effect_text_failure_does_not_remove_menu_action(spy_engine):
    vm, run = spy_engine
    vm.execute("settings.unit_x=8;UnitManager.GetOperationDetailText=function() error('unavailable') end")
    entries = missions(run("options"))
    assert entries and all("action" in entry for entry in entries)


def test_current_own_city_counterspy_menu_can_report_no_active_sources(spy_engine):
    vm, run = spy_engine
    vm.execute("""
        source_reads=0
        player.GetDiplomacy=function() return {GetSourceTurnsRemaining=function(self,city)
            assert(city==own_city);source_reads=source_reads+1;return 0
        end} end
    """)
    result = run("options", x=2)
    assert next(row for row in result["items"] if row["id"] == "sources_turns_remaining")["value"] == 0
    assert vm.globals().source_reads == 1
