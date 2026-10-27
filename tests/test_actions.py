"""Execute generated Lua against hostile engine fixtures, not string snapshots."""

import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.actions import (
    ALLOWED_ACTIONS,
    LEGACY_ACTIONS,
    build_action_query,
    build_options_query,
    validate_action,
)


BOOTSTRAP = r'''
calls = {}
reads = {units=0, cities=0, unit_fields=0, city_fields=0, can_unit=0}
controls = {active=true, complete=true, busy=false, tactical=true, visible=true,
    revealed=true, owner=0, unit_exists=true, city_exists=true, moves=2,
    can_operation=true, can_produce=true, can_research=true, can_civic=true,
    end_turn=true, blocker=0, distance=1, request_result=true, turn=7, player=0}
function forbid() error("SECRET_HIDDEN_UNIT_AT_3_2") end
GameConfiguration = {IsAnyMultiplayer=function() return false end,
    IsHotseat=function() return false end, IsWorldBuilderEditor=function() return false end}
Game = {GetLocalPlayer=function() return controls.player end,
    GetLocalObserver=function() return controls.player end,
    GetCurrentGameTurn=function() return controls.turn end,
    IsAllowTacticalCommands=function() return controls.tactical end}
Automation = {IsActive=function() return false end}
Events = {LoadGameViewStateDone={Add=function(fn) load_event=fn end},
    LocalPlayerChanged={Add=function(fn) player_event=fn end}}
local function call(kind, entity, operation, params)
    table.insert(calls, {kind=kind, entity=entity, operation=operation, params=params})
    if controls.request_result == "error" then forbid() end
    return controls.request_result
end
UI = {IsProcessingMessages=function() return controls.busy end,
    CanEndTurn=function() return controls.end_turn end,
    RequestPlayerOperation=function(who, op, p) call("player", who, op, p) end,
    RequestAction=function(op) call("action", nil, op) end}
UnitOperationTypes = {MOVE_TO=100, FORTIFY=101, FOUND_CITY=102, BUILD_IMPROVEMENT=103,
    PARAM_X="x", PARAM_Y="y", PARAM_IMPROVEMENT_TYPE="improvement", PARAM_MODIFIERS="modifiers"}
UnitOperationMoveModifiers = {NONE=0, ATTACK=1, MOVE_IGNORE_UNEXPLORED_DESTINATION=16}
MilitaryFormationTypes = {STANDARD_MILITARY_FORMATION=0}
PlayerOperations = {RESEARCH=200, PROGRESS_CIVIC=201,
    PARAM_TECH_TYPE="tech", PARAM_CIVIC_TYPE="civic", PARAM_INSERT_MODE="insert", VALUE_EXCLUSIVE=9}
CityOperationTypes = {BUILD=300, PARAM_UNIT_TYPE="unit", PARAM_BUILDING_TYPE="building",
    PARAM_PROJECT_TYPE="project", PARAM_INSERT_MODE="insert", VALUE_EXCLUSIVE=9}
ActionTypes = {ACTION_ENDTURN=400}
EndTurnBlockingTypes = {NO_ENDTURN_BLOCKING=0}
NotificationManager = {GetFirstEndTurnBlocking=function(who) assert(who==0); return controls.blocker end}
Map = {GetGridSize=function() return 100, 80 end,
    GetPlotDistance=function(ux,uy,x,y) assert(ux==2 and uy==2); return controls.distance end,
    GetPlot=forbid, GetPlotByIndex=forbid, GetUnitsAt=forbid, GetPlotXY=forbid}
UnitManager = {
    RequestOperation=function(u,op,p) return call("unit",u:GetID(),op,p) end,
    CanStartOperation=function(u,op,unused,params,results)
        reads.can_unit=reads.can_unit+1
        assert(op~=100, "move validity must not be probed")
        assert(results==false)
        return controls.can_operation, {secret="SECRET_HIDDEN_UNIT_AT_3_2"}
    end}
CityManager = {RequestOperation=function(c,op,p) return call("city",c:GetID(),op,p) end}
local unit = {
    GetOwner=function() return controls.owner end,
    GetID=function() reads.unit_fields=reads.unit_fields+1; assert(controls.owner==0); return 70001 end,
    GetX=function() reads.unit_fields=reads.unit_fields+1; assert(controls.owner==0); return 2 end,
    GetY=function() reads.unit_fields=reads.unit_fields+1; assert(controls.owner==0); return 2 end,
    GetMovesRemaining=function() reads.unit_fields=reads.unit_fields+1; assert(controls.owner==0); return controls.moves end}
local queue = {CanProduce=function(self,hash,visibility,results)
    assert((visibility==true and results==nil) or (visibility==false and results==false))
    if type(hash)=="table" then
        assert(hash.UnitType==906 and hash.MilitaryFormationType==0)
    else assert(hash~=906, "unit production requires an explicit standard formation") end
    if visibility then return controls.can_show ~= false end
    return controls.can_produce, {secret="SECRET_HIDDEN_UNIT_AT_3_2"}
end}
local city = {
    GetOwner=function() return controls.owner end,
    GetID=function() reads.city_fields=reads.city_fields+1; assert(controls.owner==0); return 70002 end,
    GetBuildQueue=function() reads.city_fields=reads.city_fields+1; assert(controls.owner==0); return queue end}
local function members(entity, exists)
    local yielded=false
    return function()
        if not yielded and exists then yielded=true; return 1, entity end
    end
end
local units = {Members=function() reads.units=reads.units+1; return members(unit,controls.unit_exists) end}
local cities = {Members=function() reads.cities=reads.cities+1; return members(city,controls.city_exists) end}
local techs = {CanResearch=function(self,index) assert(index==4); return controls.can_research end}
local culture = {CanProgress=function(self,index) assert(index==5); return controls.can_civic end}
local player = {IsAlive=function() return true end, IsHuman=function() return true end,
    IsTurnActive=function() return controls.active end,
    IsTurnActiveComplete=function() return controls.complete end,
    GetUnits=function() return units end, GetCities=function() return cities end,
    GetTechs=function() return techs end, GetCulture=function() return culture end}
Players=setmetatable({[0]=player},{__index=forbid})
PlayersVisibility={[0]={IsVisible=function(self,x,y) assert(x==2 and y==2); return controls.visible end,
    IsRevealed=function(self,x,y) assert(x==2 and y==2); return controls.revealed end}}
function definitions(field, rows)
    local result={}
    for _,row in ipairs(rows) do result[row[field]]=row end
    return setmetatable(result,{__call=function()
        local i=0
        return function() i=i+1; return rows[i] end
    end})
end
GameInfo={
    Technologies=definitions("TechnologyType",{{TechnologyType="TECH_MINING",Index=4,Hash=904}}),
    Civics=definitions("CivicType",{{CivicType="CIVIC_CODE_OF_LAWS",Index=5,Hash=905}}),
    Units=definitions("UnitType",{{UnitType="UNIT_SCOUT",Index=6,Hash=906}}),
    Buildings=definitions("BuildingType",{{BuildingType="BUILDING_MONUMENT",Index=7,Hash=907}}),
    Projects=definitions("ProjectType",{{ProjectType="PROJECT_ENHANCE_DISTRICT_CAMPUS",Index=8,Hash=908}}),
    Improvements=definitions("ImprovementType",{{ImprovementType="IMPROVEMENT_FARM",Index=9,Hash=909,Buildable=true}})
}
'''


@pytest.fixture
def engine():
    lua = LuaRuntime(unpack_returned_tuples=True)
    output = []
    lua.globals().print = output.append
    lua.execute(BOOTSTRAP)

    def run(script):
        output.clear()
        lua.execute(script)
        assert len(output) == 2
        assert output[1] == "---END---"
        assert output[0].startswith("CIV6FAIR_JSON:")
        assert "SECRET_" not in output[0]
        return json.loads(output[0].removeprefix("CIV6FAIR_JSON:"))

    return lua, run


def action_script(action, **overrides):
    metadata = dict(nonce="test_nonce", expected_session="test_nonce", expected_player=0, expected_turn=7)
    metadata.update(overrides)
    return build_action_query(action=action, **metadata)


MOVE = {"type": "move", "unit_id": 70001, "x": 3, "y": 2}
SAMPLES = [
    MOVE,
    {"type": "fortify", "unit_id": 70001},
    {"type": "found_city", "unit_id": 70001},
    {"type": "build_improvement", "unit_id": 70001, "improvement": "IMPROVEMENT_FARM"},
    {"type": "set_research", "technology": "TECH_MINING"},
    {"type": "set_civic", "civic": "CIVIC_CODE_OF_LAWS"},
    {"type": "set_production", "city_id": 70002, "item": "UNIT_SCOUT"},
    {"type": "end_turn"},
]


@pytest.mark.parametrize("action", SAMPLES)
def test_each_supported_action_is_a_single_normal_request(engine, action):
    lua, run = engine
    result = run(action_script(action))
    assert result["accepted"] is True
    assert len(lua.globals().calls) == 1
    assert set(result) == {"ok", "session", "player_id", "turn", "active_turn", "accepted"}


def test_action_catalog_and_copy():
    assert LEGACY_ACTIONS == {item["type"] for item in SAMPLES}
    assert LEGACY_ACTIONS < ALLOWED_ACTIONS
    assert validate_action(MOVE) == MOVE
    assert validate_action(MOVE) is not MOVE


@pytest.mark.parametrize("action", [
    None, [], {}, {"type": []}, {"type": "run_lua", "code": "print(Game)"},
    {**MOVE, "player_id": 1}, {**MOVE, "force": True}, {**MOVE, "script": "os.execute('x')"},
    {**MOVE, "x": True}, {**MOVE, "x": -1}, {**MOVE, "x": 65536},
    {**MOVE, "unit_id": 2**32}, {**MOVE, "unit_id": "70001"}, {**MOVE, "unit_id": 70001.0},
    {"type": "set_research", "technology": 'TECH_MINING"]; print("SECRET"); --'},
    {"type": "set_research", "technology": "TECH_MINING\n"},
    {"type": "set_research", "technology": "ＴＥＣＨ_MINING"},
    {"type": "set_research", "technology": "TECH_" + "A" * 128},
    {"type": "set_civic", "civic": "TECH_MINING"},
    {"type": "set_production", "city_id": 2, "item": "DISTRICT_CAMPUS"},
    {"type": "found_city", "unit_id": 70001, "x": 5, "y": 5},
    {"type": "end_turn", "force": True},
])
def test_untrusted_payloads_cannot_become_lua(action):
    with pytest.raises(ValueError):
        validate_action(action)


@pytest.mark.parametrize("overrides", [
    {"expected_session": 's"; error("injected"); --'},
    {"expected_player": True}, {"expected_turn": -1}, {"expected_turn": "7"},
    {"nonce": "x\nprint('injected')"},
])
def test_context_values_cannot_become_lua(overrides):
    with pytest.raises(ValueError):
        action_script(MOVE, **overrides)


@pytest.mark.parametrize("control,value", [
    ("active", False), ("complete", False), ("busy", True), ("turn", 8),
])
def test_turn_guard_rejects_before_entity_reads(engine, control, value):
    lua, run = engine
    lua.globals().controls[control] = value
    assert run(action_script(MOVE))["accepted"] is False
    assert len(lua.globals().calls) == 0
    assert lua.globals().reads.units == 0


@pytest.mark.parametrize("overrides", [{"expected_session": "old_session"}, {"expected_player": 1}])
def test_wrong_session_or_player_never_dispatches(engine, overrides):
    lua, run = engine
    assert run(action_script(MOVE, **overrides))["accepted"] is False
    assert len(lua.globals().calls) == 0
    assert lua.globals().reads.units == 0


def test_load_event_invalidates_same_turn_action(engine):
    lua, run = engine
    run(build_options_query("test_nonce", "research"))
    lua.execute("load_event()")
    assert run(action_script(MOVE, nonce="new_nonce"))["accepted"] is False
    assert len(lua.globals().calls) == 0


@pytest.mark.parametrize("action", [MOVE, {"type": "set_production", "city_id": 70002, "item": "UNIT_SCOUT"}])
def test_owner_checked_before_any_entity_field(engine, action):
    lua, run = engine
    lua.globals().controls.owner = 1
    assert run(action_script(action))["accepted"] is False
    assert len(lua.globals().calls) == 0
    assert lua.globals().reads.unit_fields == 0
    assert lua.globals().reads.city_fields == 0


def test_packed_ids_are_not_truncated_to_other_entity(engine):
    lua, run = engine
    assert run(action_script({"type": "set_production", "city_id": 70002 % 65536, "item": "UNIT_SCOUT"}))["accepted"] is False
    assert len(lua.globals().calls) == 0


@pytest.mark.parametrize("request_result", [True, False, "error"])
def test_unknown_adjacent_move_has_no_hidden_target_or_result_oracle(engine, request_result):
    lua, run = engine
    lua.globals().controls.visible = False
    lua.globals().controls.revealed = False
    lua.globals().controls.request_result = request_result
    result = run(action_script(MOVE))
    assert result == {"ok": True, "session": "test_nonce", "player_id": 0,
                      "turn": 7, "active_turn": True, "accepted": True}
    assert lua.globals().reads.can_unit == 0
    assert len(lua.globals().calls) == 1
    request = lua.globals().calls[1]
    assert request.operation == 100
    assert dict(request.params) == {"x": 3, "y": 2, "modifiers": 16}


@pytest.mark.parametrize("control,value", [("distance", 2), ("moves", 0), ("tactical", False), ("unit_exists", False)])
def test_move_public_restrictions_prevent_dispatch(engine, control, value):
    lua, run = engine
    lua.globals().controls[control] = value
    assert run(action_script(MOVE))["accepted"] is False
    assert len(lua.globals().calls) == 0


@pytest.mark.parametrize("axis,value", [("x", 100), ("y", 80)])
def test_map_bounds_prevent_wrapped_out_of_range_targets(engine, axis, value):
    lua, run = engine
    assert run(action_script({**MOVE, axis: value}))["accepted"] is False
    assert len(lua.globals().calls) == 0


@pytest.mark.parametrize("action", SAMPLES[1:4])
@pytest.mark.parametrize("flag", ["visible", "revealed"])
def test_stationary_unit_actions_require_own_current_visible_tile(engine, action, flag):
    lua, run = engine
    lua.globals().controls[flag] = False
    assert run(action_script(action))["accepted"] is False
    assert lua.globals().reads.can_unit == 0
    assert len(lua.globals().calls) == 0


@pytest.mark.parametrize("action,control", [
    (SAMPLES[1], "can_operation"), (SAMPLES[3], "can_operation"),
    (SAMPLES[4], "can_research"), (SAMPLES[5], "can_civic"),
    (SAMPLES[6], "can_produce"), (SAMPLES[7], "end_turn"),
])
def test_normal_ui_unavailable_choices_are_not_requested(engine, action, control):
    lua, run = engine
    lua.globals().controls[control] = False
    assert run(action_script(action))["accepted"] is False
    assert len(lua.globals().calls) == 0


def test_end_turn_does_not_force_through_blocking_decisions(engine):
    lua, run = engine
    lua.globals().controls.blocker = 99
    assert run(action_script({"type": "end_turn"}))["accepted"] is False
    assert len(lua.globals().calls) == 0


def test_production_checks_ui_visibility_gate_before_startability(engine):
    lua, run = engine
    lua.globals().controls.can_show = False
    lua.globals().controls.can_produce = True
    assert run(action_script(SAMPLES[6]))["accepted"] is False
    assert run(build_options_query("locked_items", "production", 70002))["options"] == []
    assert len(lua.globals().calls) == 0


@pytest.mark.parametrize("action,expected", [
    (SAMPLES[3], {"x": 2, "y": 2, "improvement": 909}),
    (SAMPLES[4], {"tech": 904, "insert": 9}),
    (SAMPLES[5], {"civic": 905, "insert": 9}),
    (SAMPLES[6], {"unit": 906, "insert": 9}),
    ({"type": "set_production", "city_id": 70002, "item": "BUILDING_MONUMENT"}, {"building": 907, "insert": 9}),
    ({"type": "set_production", "city_id": 70002, "item": "PROJECT_ENHANCE_DISTRICT_CAMPUS"}, {"project": 908, "insert": 9}),
])
def test_requests_use_definition_hash_not_index(engine, action, expected):
    lua, run = engine
    assert run(action_script(action))["accepted"] is True
    assert dict(lua.globals().calls[1].params) == expected


@pytest.mark.parametrize("flag", ["RequiresPlacement", "IsWonder", "InternalOnly", "MustPurchase"])
def test_unsupported_production_item_is_neither_offered_nor_requested(engine, flag):
    lua, run = engine
    lua.globals().GameInfo.Buildings.BUILDING_MONUMENT[flag] = True
    action = {"type": "set_production", "city_id": 70002, "item": "BUILDING_MONUMENT"}
    assert run(action_script(action))["accepted"] is False
    options = run(build_options_query("next_nonce", "production", 70002))["options"]
    assert all(option["id"] != "BUILDING_MONUMENT" for option in options)
    assert len(lua.globals().calls) == 0


@pytest.mark.parametrize("kind,entity_id,expected", [
    ("research", None, [{"id": "TECH_MINING", "kind": "research"}]),
    ("civic", None, [{"id": "CIVIC_CODE_OF_LAWS", "kind": "civic"}]),
    ("production", 70002, [{"id": "UNIT_SCOUT", "kind": "unit"},
                          {"id": "BUILDING_MONUMENT", "kind": "building"},
                          {"id": "PROJECT_ENHANCE_DISTRICT_CAMPUS", "kind": "project"}]),
])
def test_options_only_contain_safe_own_player_legal_identifiers(engine, kind, entity_id, expected):
    lua, run = engine
    result = run(build_options_query("test_nonce", kind, entity_id))
    assert result["options"] == expected
    assert len(lua.globals().calls) == 0


def test_options_cannot_use_foreign_city(engine):
    lua, run = engine
    lua.globals().controls.owner = 1
    assert run(build_options_query("test_nonce", "production", 70002))["options"] == []
    assert lua.globals().reads.city_fields == 0


@pytest.mark.parametrize("kind,entity_id", [("cheats", None), ("research", 0), ("production", None), ("production", True), ("production", -1)])
def test_invalid_options_input_rejected(kind, entity_id):
    with pytest.raises(ValueError):
        build_options_query("test_nonce", kind, entity_id)


def test_option_count_is_bounded_and_no_partial_secret_result(engine):
    lua, run = engine
    lua.execute('''
        local many={}
        for i=1,513 do table.insert(many,{TechnologyType="TECH_X"..i,Index=4,Hash=i}) end
        GameInfo.Technologies=definitions("TechnologyType",many)
    ''')
    assert run(build_options_query("test_nonce", "research")) == {"ok": False, "error": "unavailable"}
