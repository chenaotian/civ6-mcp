"""Visible tooltip fields, never resource/yield or neighboring-plot probes."""
import pytest

from civ6_fair_mcp.policy import PolicyError, public_map
from civ6_fair_mcp.queries import build_map_query
from test_queries import engine  # noqa: F401

FIELDS = {"impassable", "lake", "movement_cost", "defense_modifier", "appeal",
          "route", "route_movement_cost", "route_pillaged"}
FIXTURE = r'''
settings.impassable=false;settings.lake=false;settings.movement_cost=2
settings.defense=-2;settings.appeal=3;settings.appeal_capability=true
settings.route_present=true;settings.route_index=0;settings.route_pillaged=true
counts.planning_hidden=0;counts.appeal_reads=0;counts.cost_reads=0;counts.route_reads=0
local function visible_only(index,value)
 if index~=2 then counts.planning_hidden=counts.planning_hidden+1;error('HIDDEN_PLANNING') end
 return value
end
for index=0,2 do
 plots[index].IsImpassable=function() return visible_only(index,settings.impassable) end
 plots[index].IsLake=function() return visible_only(index,settings.lake) end
 plots[index].GetMovementCost=function() counts.cost_reads=counts.cost_reads+1;return visible_only(index,settings.movement_cost) end
 plots[index].GetDefenseModifier=function() return visible_only(index,settings.defense) end
 plots[index].GetAppeal=function() counts.appeal_reads=counts.appeal_reads+1;return visible_only(index,settings.appeal) end
 plots[index].IsRoute=function() return visible_only(index,settings.route_present) end
 plots[index].GetRouteType=function() counts.route_reads=counts.route_reads+1;return visible_only(index,settings.route_index) end
 plots[index].IsRoutePillaged=function() return visible_only(index,settings.route_pillaged) end
end
GameCapabilities={HasCapability=function(cap)
 assert(cap=='CAPABILITY_LENS_APPEAL');return settings.appeal_capability end}
GameInfo.AppealHousingChanges=function()
 local done=false;return function() if not done then done=true;return {MinimumValue=-100,Description='LOC_APPEAL'} end end end
GameInfo.Routes={[0]={RouteType='ROUTE_RAILROAD',Name='LOC_RAILROAD',MovementCost=0.25}}
'''


@pytest.fixture
def planning(engine):
    vm, run = engine
    vm.execute(FIXTURE)
    return vm, run


def tile(run):
    raw = run(build_map_query("planning_visible", 2, 0, 0))
    assert raw["ok"] is True
    return public_map(raw)["tiles"][0]


def test_visible_planning_fields_use_stock_tooltip_rules_only(planning):
    vm, run = planning
    raw = run(build_map_query("planning_region_test", 1, 0, 2))
    assert raw["ok"] is True, raw
    result = public_map(raw)["tiles"]
    assert all(not (FIELDS & set(t)) for t in result[:2])
    assert {k: v for k, v in result[2].items() if k in FIELDS} == {
        "impassable": False, "lake": False, "movement_cost": 2, "defense_modifier": -2,
        "appeal": 3, "route": "ROUTE_RAILROAD", "route_movement_cost": 0.25,
        "route_pillaged": True}
    assert vm.globals().counts.planning_hidden == 0
    assert vm.globals().counts.raw_resources == vm.globals().counts.yields == 0
    assert vm.globals().counts.appeal_reads == vm.globals().counts.cost_reads == 1


def test_becoming_fogged_does_not_cache_or_read_planning_fields(planning):
    vm, run = planning
    assert tile(run)["appeal"] == 3
    vm.execute("visibility.IsVisible=function() return false end")
    assert not FIELDS & set(tile(run))
    assert vm.globals().counts.appeal_reads == vm.globals().counts.cost_reads == 1


@pytest.mark.parametrize("change", ["settings.appeal_capability=false", "settings.appeal_capability=nil",
    "settings.appeal_capability=1", "GameCapabilities=nil", "GameCapabilities.HasCapability=nil",
    "GameCapabilities.HasCapability=function() error('PRIVATE') end",
    "plots[2].IsWater=function() return true end"])
def test_appeal_hidden_by_normal_ui_rules_is_not_even_read(planning, change):
    vm, run = planning
    vm.execute(change)
    assert "appeal" not in tile(run)
    assert vm.globals().counts.appeal_reads == 0


def test_water_natural_wonder_can_show_appeal_under_stock_exception(planning):
    vm, run = planning
    vm.execute("plots[2].IsWater=function() return true end;plots[2].GetFeatureType=function() return 0 end;"
               "GameInfo.Features[0]={FeatureType='FEATURE_WONDER',NaturalWonder=true};"
               "GameInfo.Features.FEATURE_WONDER=GameInfo.Features[0]")
    assert tile(run)["appeal"] == 3


@pytest.mark.parametrize("change", ["GameInfo.AppealHousingChanges=nil",
    "GameInfo.AppealHousingChanges=function() return function() return nil end end",
    "GameInfo.AppealHousingChanges=function() error('PRIVATE') end",
    "GameInfo.AppealHousingChanges=function() return function() return {MinimumValue=999,Description='LOC_HIGH'} end end"])
def test_no_matching_public_appeal_descriptor_omits_value(planning, change):
    vm, run = planning
    vm.execute(change)
    assert "appeal" not in tile(run)


@pytest.mark.parametrize("impassable", ["true", "nil", "1"])
def test_movement_cost_requires_confirmed_passable_terrain(planning, impassable):
    vm, run = planning
    vm.execute("settings.impassable=" + impassable)
    assert "movement_cost" not in tile(run)
    assert vm.globals().counts.cost_reads == 0


def test_no_route_is_explicit_only_from_actual_false_flag(planning):
    vm, run = planning
    vm.execute("settings.route_present=false;plots[2].GetRouteType=function() error('MUST_NOT_READ') end")
    result = tile(run)
    assert result["route"] == "NONE"
    assert "route_pillaged" not in result and "route_movement_cost" not in result


@pytest.mark.parametrize("change", ["settings.route_present=nil", "settings.route_present=1",
    "settings.route_index=-1", "settings.route_index=0.5", "settings.route_index='0'",
    "GameInfo.Routes=nil", "GameInfo.Routes[0]=nil",
    "GameInfo.Routes[0].RouteType='RESOURCE_URANIUM'", "GameInfo.Routes[0].Name=nil",
    "GameInfo.Routes[0].MovementCost=0/0", "GameInfo.Routes[0].MovementCost=-1"])
def test_unknown_route_definition_omits_all_route_fields(planning, change):
    vm, run = planning
    vm.execute(change)
    assert not {"route", "route_pillaged", "route_movement_cost"} & set(tile(run))


@pytest.mark.parametrize("field,method", [("movement_cost", "GetMovementCost"),
    ("defense_modifier", "GetDefenseModifier"), ("appeal", "GetAppeal"),
    ("lake", "IsLake"), ("impassable", "IsImpassable"), ("route_pillaged", "IsRoutePillaged")])
@pytest.mark.parametrize("replacement", ["nil", "function() error('PRIVATE') end", "function() return 'invalid' end"])
def test_optional_getter_missing_invalid_or_throwing_does_not_break_map(planning, field, method, replacement):
    vm, run = planning
    vm.execute(f"plots[2].{method}={replacement}")
    result = tile(run)
    assert result["terrain"] == "TERRAIN_GRASS" and field not in result


@pytest.mark.parametrize("value", ["0/0", "math.huge", "-math.huge", "1000001", "-1000001"])
def test_invalid_numeric_planning_values_are_omitted(planning, value):
    vm, run = planning
    vm.execute(f"settings.appeal={value};settings.defense={value};settings.movement_cost={value}")
    assert not {"appeal", "defense_modifier", "movement_cost"} & set(tile(run))


def test_locked_resource_does_not_remove_independent_visible_tooltip_fields(planning):
    vm, run = planning
    vm.execute("settings.resource_unlocked=false")
    result = tile(run)
    assert "resource" not in result and result["appeal"] == 3
    assert vm.globals().counts.raw_resources == vm.globals().counts.yields == 0


@pytest.mark.parametrize("field,value", [("route", "RESOURCE_NITER"), ("appeal", 1_000_001),
    ("movement_cost", -1), ("defense_modifier", float("inf")), ("lake", 1)])
def test_python_rejects_bad_visible_field_types_and_bounds(planning, field, value):
    _, run = planning
    raw = run(build_map_query("planning_bad_public", 2, 0, 0))
    raw["tiles"][0][field] = value
    with pytest.raises(PolicyError):
        public_map(raw)


def test_python_omits_orphan_route_details_and_all_fog_contents(planning):
    _, run = planning
    raw = run(build_map_query("planning_public_guard", 2, 0, 0))
    raw["tiles"][0]["route"] = "NONE"
    result = public_map(raw)["tiles"][0]
    assert "route_pillaged" not in result and "route_movement_cost" not in result
    raw["tiles"][0].update(visible=False, appeal="PRIVATE_BAD_TYPE")
    result = public_map(raw)["tiles"][0]
    assert not FIELDS & set(result)
