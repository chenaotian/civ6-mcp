"""Execute the actual map adapter with fog and optional hazard API traps."""

import pytest

from civ6_fair_mcp.policy import PolicyError, public_map
from civ6_fair_mcp.queries import build_map_query
from test_queries import engine  # noqa: F401


HAZARDS = r'''
settings.storm = 1
settings.drought = 2
settings.drought_turns = 4
counts.storm_reads = 0
counts.drought_reads = 0
counts.drought_turn_reads = 0
counts.hidden_hazard_reads = 0
counts.global_hazard_reads = 0
local function visible_only(plot)
    if plot ~= plots[2] then
        counts.hidden_hazard_reads = counts.hidden_hazard_reads + 1
        error('HIDDEN_HAZARD')
    end
end
GameClimate = setmetatable({
    GetActiveStormTypeAtPlot=function(plot)
        visible_only(plot)
        counts.storm_reads = counts.storm_reads + 1
        return settings.storm
    end,
    GetActiveDroughtTypeAtPlot=function(plot)
        visible_only(plot)
        counts.drought_reads = counts.drought_reads + 1
        return settings.drought
    end,
    GetDroughtTurnsAtPlot=function(plot)
        visible_only(plot)
        counts.drought_turn_reads = counts.drought_turn_reads + 1
        return settings.drought_turns
    end
}, {__index=function()
    counts.global_hazard_reads = counts.global_hazard_reads + 1
    error('GLOBAL_HAZARD_STATE')
end})
GameInfo.RandomEvents = {
    [1]={RandomEventType='RANDOM_EVENT_HURRICANE_CAT_4', Name='LOC_STORM_NAME'},
    [2]={RandomEventType='RANDOM_EVENT_DROUGHT_MAJOR', Name='LOC_DROUGHT_NAME'}
}
Locale.Lookup = function(key)
    if key == 'LOC_STORM_NAME' then return '四级飓风' end
    if key == 'LOC_DROUGHT_NAME' then return '严重干旱' end
    return key
end
'''


@pytest.fixture
def hazards(engine):
    lua, run = engine
    lua.execute(HAZARDS)
    return lua, run


def visible_tile(run):
    raw = run(build_map_query("hazard_visible_test", 2, 0, 0))
    assert raw["ok"] is True
    return public_map(raw)["tiles"][0]


def test_only_current_visible_plot_receives_exact_stock_hazards(hazards):
    lua, run = hazards
    raw = run(build_map_query("hazard_visibility", 1, 0, 2))
    tiles = public_map(raw)["tiles"]
    assert tiles[0] == {"x": 0, "y": 0, "revealed": False, "visible": False}
    assert tiles[1] == {"x": 1, "y": 0, "revealed": True, "visible": False}
    assert {k: v for k, v in tiles[2].items() if k.startswith(("storm_", "drought_"))} == {
        "storm_type": "RANDOM_EVENT_HURRICANE_CAT_4", "storm_name": "四级飓风",
        "drought_type": "RANDOM_EVENT_DROUGHT_MAJOR", "drought_name": "严重干旱",
        "drought_turns": 4,
    }
    assert lua.globals().counts.storm_reads == 1
    assert lua.globals().counts.drought_reads == 1
    assert lua.globals().counts.drought_turn_reads == 1
    assert lua.globals().counts.hidden_hazard_reads == 0
    assert lua.globals().counts.global_hazard_reads == 0


def test_fog_transition_neither_reads_nor_reuses_previous_hazards(hazards):
    lua, run = hazards
    assert visible_tile(run)["storm_name"] == "四级飓风"
    lua.execute("visibility.IsVisible=function() return false end")
    raw = run(build_map_query("hazard_fog", 1, 0, 2))
    assert all(set(tile) == {"x", "y", "revealed", "visible"} for tile in public_map(raw)["tiles"])
    assert lua.globals().counts.storm_reads == 1
    assert lua.globals().counts.drought_reads == 1
    assert lua.globals().counts.drought_turn_reads == 1


def test_minus_one_alone_means_none_and_needs_no_definition_or_turns(hazards):
    lua, run = hazards
    lua.execute("settings.storm=-1; settings.drought=-1; GameInfo.RandomEvents=nil")
    tile = visible_tile(run)
    assert tile["storm_type"] == tile["drought_type"] == "NONE"
    assert "storm_name" not in tile and "drought_name" not in tile and "drought_turns" not in tile
    assert lua.globals().counts.drought_turn_reads == 0


@pytest.mark.parametrize("setup", [
    "GameClimate=nil",
    "GameClimate={}",
    "GameClimate=setmetatable({}, {__index=function() error('GETTER_LOOKUP') end})",
    "GameClimate.GetActiveStormTypeAtPlot=function() error('STORM_FAILURE') end; "
    "GameClimate.GetActiveDroughtTypeAtPlot=function() error('DROUGHT_FAILURE') end",
    "settings.storm=nil; settings.drought=nil",
    "settings.storm=false; settings.drought=true",
    "settings.storm='1'; settings.drought='2'",
    "settings.storm=1.5; settings.drought=2.5",
    "settings.storm=0/0; settings.drought=math.huge",
    "settings.storm=-2147483649; settings.drought=4294967296",
    "settings.storm=-2; settings.drought=999",
    "GameInfo.RandomEvents=nil",
    "GameInfo.RandomEvents={}",
    "GameInfo.RandomEvents=setmetatable({}, {__index=function() error('ROW_LOOKUP') end})",
    "GameInfo.RandomEvents[1]={RandomEventType='TECH_SECRET'}; "
    "GameInfo.RandomEvents[2]={RandomEventType='RANDOM_EVENT_'}",
    "GameInfo.RandomEvents[1]={RandomEventType='RANDOM_EVENT_X;attack()'}; "
    "GameInfo.RandomEvents[2]={RandomEventType='RANDOM_EVENT_'..string.rep('X', 120)}",
])
def test_unknown_hazards_are_omitted_without_losing_regular_map(hazards, setup):
    lua, run = hazards
    lua.execute(setup)
    tile = visible_tile(run)
    assert tile["terrain"] == "TERRAIN_GRASS"
    assert not any(k.startswith(("storm_", "drought_")) for k in tile)
    assert lua.globals().counts.drought_turn_reads == 0


def test_one_hazard_api_failure_does_not_erase_other_hazard(hazards):
    lua, run = hazards
    lua.execute("GameClimate.GetActiveStormTypeAtPlot=function() error('STORM_FAILURE') end")
    tile = visible_tile(run)
    assert "storm_type" not in tile
    assert tile["drought_type"] == "RANDOM_EVENT_DROUGHT_MAJOR"
    assert tile["drought_turns"] == 4


@pytest.mark.parametrize("setup", [
    "Locale=nil", "Locale={}",
    "Locale.Lookup=function() error('TRANSLATION_FAILURE') end",
    "Locale.Lookup=function() return nil end",
    "Locale.Lookup=function() return false end",
    "Locale.Lookup=function() return '' end",
    "Locale.Lookup=function() return 'BAD'..string.char(10)..'TITLE' end",
    "Locale.Lookup=function() return string.rep('X',257) end",
    "GameInfo.RandomEvents[1].Name=nil; GameInfo.RandomEvents[2].Name=nil",
])
def test_optional_title_failure_preserves_known_type_and_turns(hazards, setup):
    lua, run = hazards
    lua.execute(setup)
    tile = visible_tile(run)
    assert tile["storm_type"] == "RANDOM_EVENT_HURRICANE_CAT_4"
    assert tile["drought_type"] == "RANDOM_EVENT_DROUGHT_MAJOR"
    assert tile["drought_turns"] == 4
    assert "storm_name" not in tile and "drought_name" not in tile


@pytest.mark.parametrize("setup", [
    "GameClimate.GetDroughtTurnsAtPlot=nil",
    "GameClimate.GetDroughtTurnsAtPlot=function() error('TURN_FAILURE') end",
    "settings.drought_turns=nil", "settings.drought_turns=false",
    "settings.drought_turns=-1", "settings.drought_turns=0.5",
    "settings.drought_turns='4'", "settings.drought_turns=1000001",
    "settings.drought_turns=0/0", "settings.drought_turns=math.huge",
])
def test_unknown_or_invalid_turns_are_omitted(hazards, setup):
    lua, run = hazards
    lua.execute(setup)
    tile = visible_tile(run)
    assert tile["drought_type"] == "RANDOM_EVENT_DROUGHT_MAJOR"
    assert tile["drought_name"] == "严重干旱"
    assert "drought_turns" not in tile


@pytest.mark.parametrize("turns", [0, 1_000_000])
def test_turn_count_boundaries(hazards, turns):
    lua, run = hazards
    lua.globals().settings.drought_turns = turns
    assert visible_tile(run)["drought_turns"] == turns


def raw_tile(**fields):
    return {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 15,
            "active_turn": True, "tiles": [
                {"x": 1, "y": 2, "revealed": True, "visible": True, **fields}]}


@pytest.mark.parametrize("field,value", [
    ("storm_type", "TECH_WRITING"), ("drought_type", "RANDOM_EVENT_"),
    ("storm_type", "RANDOM_EVENT_X;read()"), ("storm_type", "RANDOM_EVENT_" + "X" * 120),
    ("storm_type", 1), ("storm_type", None), ("storm_type", False),
    ("storm_name", "X" * 257), ("drought_name", "x\ny"), ("storm_name", 1),
    ("drought_turns", True), ("drought_turns", -1), ("drought_turns", 1_000_001),
    ("drought_turns", 1.5), ("drought_turns", "4"),
])
def test_python_boundary_rejects_invalid_visible_fields(field, value):
    with pytest.raises(PolicyError):
        public_map(raw_tile(**{field: value}))


@pytest.mark.parametrize("revealed", [False, True])
def test_python_boundary_discards_fogged_hazards_before_validation(revealed):
    raw = raw_tile(revealed=revealed, visible=False, storm_type={"secret": 1},
                   storm_name=["SECRET"], drought_type=False, drought_name=9, drought_turns=-999)
    assert public_map(raw)["tiles"] == [
        {"x": 1, "y": 2, "revealed": revealed, "visible": False}]


@pytest.mark.parametrize("types", [{}, {"storm_type": "NONE", "drought_type": "NONE"}])
def test_python_boundary_omits_orphan_title_and_turn_fields(types):
    tile = public_map(raw_tile(**types, storm_name="orphan", drought_name="orphan", drought_turns=4))["tiles"][0]
    assert "storm_name" not in tile and "drought_name" not in tile and "drought_turns" not in tile


def test_python_boundary_never_exposes_unapproved_global_disaster_metadata():
    tile = public_map(raw_tile(storm_type="RANDOM_EVENT_HURRICANE_CAT_4", storm_name="飓风",
                              storm_center={"x": 99, "y": 99}, storm_path=[1, 2],
                              affected_cities=["SECRET"], disaster_id=91))["tiles"][0]
    assert set(tile) == {"x", "y", "revealed", "visible", "storm_type", "storm_name"}
