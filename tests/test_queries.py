"""Execute actual generated Lua against adversarial engine doubles.

Hidden getters raise (and count calls): merely deleting a leaked field after
reading the engine cannot pass these tests.
"""

import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.queries import build_map_query, build_player_query
from civ6_fair_mcp.policy import public_map, public_player


ENGINE = r'''
settings = {me=0, observer=0, human=true, alive=true, turn=12,
    active=true, ready=true, processing=false, multiplayer=false, hotseat=false,
    automation=false, editor=false, resource=7, resource_unlocked=true,
    improvement=-1, pillaged=false, district=-1}
counts = {hidden_reads=0, foreign_reads=0, raw_resources=0, yields=0, layer_reads=0, district_reads=0}
GameConfiguration = {
    IsAnyMultiplayer=function() return settings.multiplayer end,
    IsHotseat=function() return settings.hotseat end,
    IsWorldBuilderEditor=function() return settings.editor end
}
Automation = {IsActive=function() return settings.automation end}
UI = {IsProcessingMessages=function() return settings.processing end}
Game = {
    GetLocalPlayer=function() return settings.me end,
    GetLocalObserver=function() return settings.observer end,
    GetCurrentGameTurn=function() return settings.turn end
}
local function event()
    local callbacks = {}
    return {
        Add=function(callback) callbacks[#callbacks + 1] = callback end,
        Fire=function() for _, callback in ipairs(callbacks) do callback() end end
    }
end
Events = {LoadGameViewStateDone=event(), LocalPlayerChanged=event()}
Locale = {Lookup=function(value) return value end}
YieldTypes = {FOOD=0, PRODUCTION=1, GOLD=2, SCIENCE=3, CULTURE=4, FAITH=5}
local function definitions(values)
    return setmetatable(values, {__call=function(self)
        local key=nil
        return function()
            key=next(self, key)
            if key ~= nil then return self[key] end
        end
    end})
end
GameInfo = {
    Units=definitions({[0]={Hash=100, UnitType='UNIT_WARRIOR'}}),
    Buildings=definitions({[0]={Hash=101, BuildingType='BUILDING_MONUMENT'}}),
    Districts=definitions({}), Projects=definitions({}),
    Technologies={[0]={TechnologyType='TECH_POTTERY'}},
    Civics={[0]={CivicType='CIVIC_CODE_OF_LAWS'}},
    Terrains={[0]={TerrainType='TERRAIN_GRASS'}},
    Features={}, Resources={[7]={Hash=700, ResourceType='RESOURCE_IRON'}},
    Improvements={
        [0]={ImprovementType='IMPROVEMENT_GOODY_HUT'},
        [1]={ImprovementType='IMPROVEMENT_BARBARIAN_CAMP'},
        [2]={ImprovementType='IMPROVEMENT_FARM'}
    }
}
own_units = {}
own_cities = {}
local player = {
    IsAlive=function() return settings.alive end,
    IsHuman=function() return settings.human end,
    IsTurnActive=function() return settings.active end,
    IsTurnActiveComplete=function() return settings.ready end,
    GetResources=function() return {
        IsResourceVisible=function(self,hash)
            assert(hash == 700)
            return settings.resource_unlocked
        end
    } end,
    GetTreasury=function() return {
        GetGoldBalance=function() return 100 end,
        GetGoldYield=function() return 8 end,
        GetTotalMaintenance=function() return 1 end
    } end,
    GetReligion=function() return {
        GetFaithBalance=function() return 20 end,
        GetFaithYield=function() return 2 end
    } end,
    GetTechs=function() return {
        GetScienceYield=function() return 3 end,
        GetResearchingTech=function() return 0 end
    } end,
    GetCulture=function() return {
        GetCultureYield=function() return 4 end,
        GetProgressingCivic=function() return 0 end
    } end,
    GetUnits=function() return {Members=function() return ipairs(own_units) end} end,
    GetCities=function() return {Members=function() return ipairs(own_cities) end} end
}
Players = setmetatable({[0]=player}, {__index=function()
    counts.foreign_reads=counts.foreign_reads+1
    error('SECRET FOREIGN PLAYER')
end})
visibility = {
    IsRevealed=function(self,index) return index > 0 end,
    IsVisible=function(self,index) return index == 2 end,
    GetLayerValue=function(self,layer,index)
        assert(index == 2)
        counts.layer_reads=counts.layer_reads+1
        return settings.resource
    end
}
PlayersVisibility = {[0]=visibility}
VisibilityLayerTypes = {RESOURCES=99}
plots = {}
for index=0,2 do
    local function contents(value)
        if index ~= 2 then
            counts.hidden_reads=counts.hidden_reads+1
            error('SECRET HIDDEN PLOT')
        end
        return value
    end
    plots[index] = {
        GetIndex=function() return index end,
        GetX=function() return index end,
        GetY=function() return 0 end,
        GetTerrainType=function() return contents(0) end,
        GetFeatureType=function() return contents(-1) end,
        IsHills=function() return contents(false) end,
        IsRiver=function() return contents(true) end,
        IsWater=function() return contents(false) end,
        GetOwner=function() return contents(9) end,
        GetDistrictType=function()
            counts.district_reads=counts.district_reads+1
            return contents(settings.district)
        end,
        GetImprovementType=function() return contents(settings.improvement) end,
        IsImprovementPillaged=function() return contents(settings.pillaged) end,
        GetResourceType=function()
            counts.raw_resources=counts.raw_resources+1
            error('SECRET UNRESEARCHED RESOURCE')
        end,
        GetYield=function()
            counts.yields=counts.yields+1
            error('SECRET RESOURCE BONUS')
        end
    }
end
Map = {
    GetPlot=function(x,y) if y==0 then return plots[x] end end,
    GetPlotDistance=function(x,y,tx,ty) return math.abs(x-tx)+math.abs(y-ty) end,
    GetUnitsAt=function() error('SECRET STEALTH UNIT') end
}
'''


@pytest.fixture
def engine():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(ENGINE)
    output = []
    lua.globals().print = output.append

    def run(script):
        output.clear()
        lua.execute(script)
        assert len(output) == 2
        assert output[-1] == "---END---"
        assert output[0].startswith("CIV6FAIR_JSON:")
        return json.loads(output[0][len("CIV6FAIR_JSON:") :])

    return lua, run


def test_hidden_contents_never_read_and_resource_layer_only(engine):
    lua, run = engine
    result = run(build_map_query("nonce", 1, 0, 2))
    assert result["ok"] is True
    tiles = {item["x"]: item for item in result["tiles"]}
    assert tiles[0] == {"x": 0, "y": 0, "revealed": False, "visible": False}
    assert tiles[1] == {"x": 1, "y": 0, "revealed": True, "visible": False}
    assert tiles[2]["resource"] == "RESOURCE_IRON"
    assert tiles[2]["resource_visible"] is True
    assert tiles[2]["owner_id"] == 9
    assert lua.globals().counts.hidden_reads == 0
    assert lua.globals().counts.foreign_reads == 0
    assert lua.globals().counts.raw_resources == 0
    assert lua.globals().counts.yields == 0
    assert lua.globals().counts.layer_reads == 1


@pytest.mark.parametrize("district,expected", [(-1, "NONE"), (3, "DISTRICT_CAMPUS"), (4, "DISTRICT_CITY_CENTER")])
def test_visible_tile_reports_exact_district_without_city_district_collection(engine, district, expected):
    lua, run = engine
    lua.execute('''
        GameInfo.Districts[3]={DistrictType="DISTRICT_CAMPUS"}
        GameInfo.Districts[4]={DistrictType="DISTRICT_CITY_CENTER"}
        plots[2].GetDistrictID=function() error("SECRET_DISTRICT_ID") end
    ''')
    lua.globals().settings.district = district
    result = run(build_map_query("district_visible", 1, 0, 2))
    tiles = {item["x"]: item for item in result["tiles"]}
    assert tiles[2]["district"] == expected
    assert "district" not in tiles[0] and "district" not in tiles[1]
    assert tiles[2]["improvement"] == "NONE"
    assert lua.globals().counts.district_reads == 1
    assert lua.globals().counts.hidden_reads == 0
    assert lua.globals().counts.foreign_reads == 0


@pytest.mark.parametrize("setup", [
    "plots[2].GetDistrictType=nil",
    'plots[2].GetDistrictType=function() error("SECRET_ERROR") end',
    "settings.district=-2", "settings.district=0.5", "settings.district='3'", "settings.district=0/0",
    "settings.district=3; GameInfo.Districts=nil",
    "settings.district=999",
    'settings.district=3; GameInfo.Districts[3]={DistrictType="TECH_WRITING"}',
    'settings.district=3; GameInfo.Districts[3]={DistrictType="DISTRICT_"}',
    'settings.district=3; GameInfo.Districts[3]={DistrictType="DISTRICT_CAMPUS;SECRET()"}',
])
def test_missing_or_invalid_optional_district_data_is_omitted(engine, setup):
    lua, run = engine
    lua.execute(setup)
    result = run(build_map_query("district_optional", 2, 0, 0))
    assert result["ok"] is True
    assert "district" not in result["tiles"][0]
    assert result["tiles"][0]["terrain"] == "TERRAIN_GRASS"


def test_district_not_read_or_cached_once_tile_returns_to_fog(engine):
    lua, run = engine
    lua.execute('settings.district=3; GameInfo.Districts[3]={DistrictType="DISTRICT_CAMPUS"}')
    assert run(build_map_query("district_fog", 2, 0, 0))["tiles"][0]["district"] == "DISTRICT_CAMPUS"
    lua.execute('''visibility.IsVisible=function() return false end
        plots[2].GetDistrictType=function() error("SECRET_FOG_DISTRICT") end''')
    assert run(build_map_query("district_fog", 2, 0, 0))["tiles"] == [
        {"x": 2, "y": 0, "revealed": True, "visible": False}
    ]
    assert lua.globals().counts.district_reads == 1


CLIFF_SETUP = r'''
cliff_reads={IsNWOfCliff=0,IsWOfCliff=0,IsNEOfCliff=0}
cliff_values={IsNWOfCliff=true,IsWOfCliff=false,IsNEOfCliff=true}
for index=0,2 do
    for _,method in ipairs({'IsNWOfCliff','IsWOfCliff','IsNEOfCliff'}) do
        plots[index][method]=function(self)
            assert(self==plots[index])
            if index~=2 then counts.hidden_reads=counts.hidden_reads+1;error('SECRET_FOG_CLIFF') end
            cliff_reads[method]=cliff_reads[method]+1
            return cliff_values[method]
        end
    end
end
'''


@pytest.mark.parametrize("nw,w,ne", [(bool(bits & 4), bool(bits & 2), bool(bits & 1)) for bits in range(8)])
def test_cliff_flags_keep_exact_independent_api_mapping_and_pass_public_projection(engine, nw, w, ne):
    vm, run = engine
    vm.execute(CLIFF_SETUP)
    for method, value in (("IsNWOfCliff", nw), ("IsWOfCliff", w), ("IsNEOfCliff", ne)):
        vm.globals().cliff_values[method] = value
    result = run(build_map_query("cliff_visible_test", 1, 0, 2))
    values = {item["x"]: item for item in public_map(result)["tiles"]}
    assert values[2]["is_nw_of_cliff"] is nw
    assert values[2]["is_w_of_cliff"] is w
    assert values[2]["is_ne_of_cliff"] is ne
    assert values[0] == {"x": 0, "y": 0, "revealed": False, "visible": False}
    assert values[1] == {"x": 1, "y": 0, "revealed": True, "visible": False}
    assert list(vm.globals().cliff_reads.values()) == [1, 1, 1]
    assert vm.globals().counts.hidden_reads == 0


@pytest.mark.parametrize("method,field", [
    ("IsNWOfCliff", "is_nw_of_cliff"),
    ("IsWOfCliff", "is_w_of_cliff"),
    ("IsNEOfCliff", "is_ne_of_cliff"),
])
@pytest.mark.parametrize("replacement", ["nil", "42", "function() return nil end",
    "function() return 1 end", "function() return 'true' end", "function() error('SECRET_ERROR') end"])
def test_unknown_optional_cliff_edge_is_omitted_without_discarding_other_edges(engine, method, field, replacement):
    vm, run = engine
    vm.execute(CLIFF_SETUP + f"\nplots[2].{method}={replacement}")
    result = run(build_map_query("cliff_optional_test", 2, 0, 0))
    assert result["ok"] is True
    tile = result["tiles"][0]
    assert field not in tile
    assert len([key for key in tile if key.endswith("_of_cliff")]) == 2
    assert tile["terrain"] == "TERRAIN_GRASS"
    assert "SECRET" not in json.dumps(result)


def test_cliff_getter_lookup_failure_is_optional_and_fog_never_reuses_previous_flags(engine):
    vm, run = engine
    vm.execute(CLIFF_SETUP + r'''
plots[2].IsWOfCliff=nil
setmetatable(plots[2],{__index=function(self,key)
    if key=='IsWOfCliff' then error('SECRET_API_ERROR') end
end})
''')
    tile = run(build_map_query("cliff_fog_test", 2, 0, 0))["tiles"][0]
    assert tile["is_nw_of_cliff"] is True and "is_w_of_cliff" not in tile
    vm.execute("visibility.IsVisible=function() return false end")
    raw = run(build_map_query("cliff_fog_test", 2, 0, 0))
    assert raw["tiles"] == [{"x": 2, "y": 0, "revealed": True, "visible": False}]
    assert vm.globals().cliff_reads.IsNWOfCliff == 1
    assert vm.globals().cliff_reads.IsNEOfCliff == 1
    assert vm.globals().counts.hidden_reads == 0


@pytest.mark.parametrize("setup", [
    "settings.resource = -1", "visibility.GetLayerValue = nil",
    "VisibilityLayerTypes = nil", "settings.resource = '7'",
    "settings.resource_unlocked = false", "Players[0].GetResources = nil",
])
def test_resources_omitted_without_explicit_layer_proof(engine, setup):
    lua, run = engine
    lua.execute(setup)
    tile = run(build_map_query("nonce", 2, 0, 0))["tiles"][0]
    assert "resource" not in tile
    assert "resource_visible" not in tile
    assert lua.globals().counts.raw_resources == 0


@pytest.mark.parametrize("setup", [
    "settings.me = -1", "settings.observer = -1", "settings.human = false",
    "settings.alive = false", "settings.multiplayer = true",
    "settings.hotseat = true", "settings.automation = true",
    "settings.editor = true", "GameConfiguration.IsWorldBuilderEditor = nil",
    "GameConfiguration.IsAnyMultiplayer = nil", "Automation = nil",
    "Game.GetLocalObserver = nil", "PlayersVisibility[0] = nil",
    "visibility.IsVisible = nil", "settings.active = 1",
    "Events.LoadGameViewStateDone = nil", "Events.LocalPlayerChanged = nil",
])
def test_unknown_or_privileged_control_modes_fail_closed(engine, setup):
    lua, run = engine
    lua.execute(setup)
    assert run(build_map_query("nonce", 2, 0, 0)) == {"ok": False, "error": "unavailable"}


@pytest.mark.parametrize("setting", ["active", "ready"])
def test_not_ready_turn_has_no_action_authority(engine, setting):
    lua, run = engine
    lua.globals().settings[setting] = False
    assert run(build_map_query("nonce", 2, 0, 0))["active_turn"] is False


def test_busy_turn_has_no_action_authority(engine):
    lua, run = engine
    lua.globals().settings.processing = True
    assert run(build_map_query("nonce", 2, 0, 0))["active_turn"] is False


def test_session_stable_until_load_player_change_or_rollback(engine):
    lua, run = engine
    assert run(build_map_query("first", 2, 0, 0))["session"] == "first"
    assert run(build_map_query("second", 2, 0, 0))["session"] == "first"
    lua.execute("Events.LoadGameViewStateDone.Fire()")
    assert run(build_map_query("third", 2, 0, 0))["session"] == "third"
    lua.execute("Events.LocalPlayerChanged.Fire()")
    assert run(build_map_query("fourth", 2, 0, 0))["session"] == "fourth"
    lua.execute("settings.turn = 11")
    assert run(build_map_query("fifth", 2, 0, 0))["session"] == "fifth"


def test_no_live_or_cached_details_after_visibility_lost(engine):
    lua, run = engine
    assert "terrain" in run(build_map_query("a", 2, 0, 0))["tiles"][0]
    lua.execute("visibility.IsVisible = function() return false end")
    assert run(build_map_query("b", 2, 0, 0))["tiles"] == [
        {"x": 2, "y": 0, "revealed": True, "visible": False}
    ]
    assert lua.globals().counts.layer_reads == 1


def test_own_observation_empty_lists_encode_as_arrays(engine):
    _, run = engine
    result = run(build_player_query("nonce"))
    assert result["units"] == [] and result["cities"] == []
    assert result["player"]["gold_per_turn"] == 7
    assert result["player"]["research"] == "TECH_POTTERY"
    assert result["player"]["civic"] == "CIVIC_CODE_OF_LAWS"


def test_foreign_entities_guarded_before_any_details(engine):
    lua, run = engine
    lua.execute("""
        local foreign = setmetatable({GetOwner=function() return 1 end},
            {__index=function() counts.foreign_reads=counts.foreign_reads+1;
                error('SECRET FOREIGN DETAILS') end})
        own_units[1] = foreign
        own_cities[1] = foreign
    """)
    result = run(build_player_query("nonce"))
    assert result["units"] == [] and result["cities"] == []
    assert lua.globals().counts.foreign_reads == 0


def test_own_units_and_cities_use_ui_fields_and_public_production_definitions(engine):
    lua, run = engine
    lua.execute("""
        own_units[1] = {
            GetOwner=function() return 0 end, GetID=function() return 11 end,
            GetX=function() return 2 end, GetY=function() return 0 end,
            GetUnitType=function() return 0 end, GetName=function() return '战士' end,
            GetMovesRemaining=function() return 1 end, GetMaxMoves=function() return 2 end,
            GetDamage=function() return 10 end, GetMaxDamage=function() return 100 end,
            GetBuildCharges=function() return 0 end
        }
        own_cities[1] = {
            GetOwner=function() return 0 end, GetID=function() return 12 end,
            GetX=function() return 2 end, GetY=function() return 0 end,
            GetName=function() return '北京' end, GetPopulation=function() return 3 end,
            GetYield=function(self,kind) return kind + 1 end,
            GetBuildQueue=function() return {
                GetSize=function() return 1 end,
                GetCurrentProductionTypeHash=function() return 101 end,
                GetTurnsLeft=function() return 4 end
            } end
        }
    """)
    result = run(build_player_query("nonce"))
    assert result["units"] == [{
        "owner_id": 0, "id": 11, "x": 2, "y": 0, "type": "UNIT_WARRIOR",
        "name": "战士", "moves": 1, "max_moves": 2, "damage": 10,
        "max_damage": 100, "build_charges": 0,
    }]
    assert result["cities"] == [{
        "owner_id": 0, "id": 12, "x": 2, "y": 0, "name": "北京", "population": 3,
        "food": 1, "production_per_turn": 2, "gold_per_turn": 3,
        "science_per_turn": 4, "culture_per_turn": 5, "faith_per_turn": 6,
        "production": "BUILDING_MONUMENT", "production_turns": 4,
    }]
    assert lua.globals().counts.foreign_reads == 0


@pytest.fixture
def production_state_engine(engine):
    lua, run = engine
    lua.execute('''
        production_state={size=1,turns=4}
        current_queue={GetSize=function() return production_state.size end,
            GetCurrentProductionTypeHash=function() assert(production_state.size>0); return 101 end,
            GetTurnsLeft=function() assert(production_state.size>0); return production_state.turns end}
        own_cities[1]={GetOwner=function() return 0 end,GetID=function() return 12 end,
            GetX=function() return 2 end,GetY=function() return 0 end,
            GetName=function() return '姆班赞刚果' end,GetPopulation=function() return 5 end,
            GetYield=function(self,kind) return kind+1 end,
            GetBuildQueue=function() return current_queue end}
    ''')
    return lua, run


@pytest.mark.parametrize("turns,expected", [
    (-1, {"production_indefinite": True}),
    (0, {"production_turns": 0}),
    (3.0, {"production_turns": 3}),
])
def test_normal_production_estimate_states_preserve_whole_player_snapshot(production_state_engine, turns, expected):
    lua, run = production_state_engine
    lua.globals().production_state.turns = turns
    raw = run(build_player_query("production_state_test"))
    public = public_player(raw)
    city = public["cities"][0]
    assert city["production"] == "BUILDING_MONUMENT"
    assert {k: city[k] for k in ("production_turns", "production_indefinite") if k in city} == expected
    assert public["player"]["gold"] == 100
    assert public["units"] == []  # a consumed builder does not invalidate cities
    if "production_turns" in city:
        assert type(city["production_turns"]) is int


@pytest.mark.parametrize("setup", [
    "current_queue.GetTurnsLeft=nil",
    "current_queue.GetTurnsLeft=function() error('SECRET_ENGINE_ERROR') end",
    "production_state.turns=nil", "production_state.turns=-2", "production_state.turns=2.5",
    "production_state.turns='3'", "production_state.turns=math.huge", "production_state.turns=0/0",
])
def test_optional_unknown_production_estimate_omits_only_estimate(production_state_engine, setup):
    lua, run = production_state_engine
    lua.execute(setup)
    public = public_player(run(build_player_query("production_optional")))
    city = public["cities"][0]
    assert city["production"] == "BUILDING_MONUMENT"
    assert "production_turns" not in city and "production_indefinite" not in city
    assert public["player"]["gold"] == 100


def test_completed_empty_queue_does_not_probe_current_production_or_estimate(production_state_engine):
    lua, run = production_state_engine
    lua.execute("production_state.size=0")
    city = public_player(run(build_player_query("production_empty_test")))["cities"][0]
    assert all(key not in city for key in ("production", "production_turns", "production_indefinite"))


@pytest.fixture
def ready_unit_engine(engine):
    lua,run=engine
    lua.execute('''
ready_unit={
    GetOwner=function() return 0 end,GetID=function() return 11 end,
    GetX=function() return 2 end,GetY=function() return 0 end,
    GetUnitType=function() return 0 end,GetName=function() return '战士' end,
    GetMovesRemaining=function() return 1 end,GetMaxMoves=function() return 2 end,
    GetDamage=function() return 0 end,GetMaxDamage=function() return 100 end,
    GetBuildCharges=function() return 0 end
}
own_units={ready_unit}
unit_collection={Members=function() return ipairs(own_units) end,
    GetFirstReadyUnit=function() return ready_unit end}
Players[0].GetUnits=function() return unit_collection end
''')
    return lua,run


def test_first_ready_unit_id_is_bound_to_projected_own_unit_list(ready_unit_engine):
    _,run=ready_unit_engine
    public=public_player(run(build_player_query('a'*32)))
    assert public['first_ready_unit_id']==11
    assert public['first_ready_unit_id'] in {unit['id'] for unit in public['units']}
    assert 'first_ready_unit_checked' not in public


@pytest.mark.parametrize('state', ['missing','nil','error'])
def test_first_ready_unit_distinguishes_no_ready_unit_from_unavailable_api(ready_unit_engine,state):
    lua,run=ready_unit_engine
    lua.execute({'missing':'unit_collection.GetFirstReadyUnit=nil',
        'nil':'unit_collection.GetFirstReadyUnit=function() return nil end',
        'error':"unit_collection.GetFirstReadyUnit=function() error('private engine failure') end"}[state])
    public=public_player(run(build_player_query('a'*32)))
    if state=='nil':
        assert 'first_ready_unit_id' in public and public['first_ready_unit_id'] is None
    else:
        assert 'first_ready_unit_id' not in public


def test_foreign_first_ready_unit_owner_is_checked_before_id_getter(ready_unit_engine):
    lua,run=ready_unit_engine
    lua.execute('''
unit_collection.GetFirstReadyUnit=function()
    return setmetatable({GetOwner=function() return 1 end},{__index=function()
        counts.foreign_reads=counts.foreign_reads+1;error('SECRET FOREIGN READY UNIT') end})
end
''')
    public=public_player(run(build_player_query('a'*32)))
    assert 'first_ready_unit_id' not in public
    assert lua.globals().counts.foreign_reads==0


def test_first_ready_unit_outside_this_snapshot_is_not_returned(ready_unit_engine):
    lua,run=ready_unit_engine
    lua.execute('''
unit_collection.GetFirstReadyUnit=function()
    return {GetOwner=function() return 0 end,GetID=function() return 99 end}
end
''')
    public=public_player(run(build_player_query('a'*32)))
    assert [unit['id'] for unit in public['units']]==[11]
    assert 'first_ready_unit_id' not in public


def test_json_escapes_controls_quotes_backslashes_and_unicode(engine):
    lua, run = engine
    expected = '秦始皇 "city" \\ ' + "".join(chr(i) for i in range(32))
    lua.globals().test_text = expected
    result = run(wrap("out.text = test_text", "nonce"))
    assert result["text"] == expected


@pytest.mark.parametrize("body", [
    "error('SECRET RESOURCE IRON at 45,60')",
    "out.secret = math.huge", "out.secret = 0/0",
    "out.secret = out", "out.secret = function() end",
])
def test_errors_and_unserializable_values_never_emit_raw_details(engine, body):
    _, run = engine
    assert run(wrap(body, "nonce")) == {"ok": False, "error": "unavailable"}


@pytest.mark.parametrize("args", [(True, 0, 1), (0, 0, 9), (-1, 0, 1), (0, "0", 1), (4096, 0, 0)])
def test_map_input_cannot_inject_lua(args):
    with pytest.raises(ValueError):
        build_map_query("nonce", *args)


@pytest.mark.parametrize("nonce", ["x';error('oops')--", "", "x\n", "n" * 129])
def test_nonce_cannot_inject_lua(nonce):
    with pytest.raises(ValueError):
        wrap("", nonce)
