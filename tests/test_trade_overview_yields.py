"""Active trade benefits use stock totals without inspecting route geography."""
from copy import deepcopy

import pytest

from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import PolicyError
from test_trade_overview import overview_engine  # noqa: F401


@pytest.fixture
def yields_engine(overview_engine):
    vm, run = overview_engine
    vm.execute('''
yield_reads={route=0,origin_multiplier=0,destination_multiplier=0}
yield_data={
    Origin={FromPotentialRoute={2,0,-4,1,0,2},FromPath={1,0,1,2,0,0},FromModifiers={3,0,1,3,0,0}},
    Destination={FromPotentialRoute={1,2,3,4,5,6},FromPath={0,0,0,0,0,0},FromModifiers={0,0,0,0,0,0}}
}
GameInfo.Yields={}
for i,name in ipairs({"YIELD_FOOD","YIELD_PRODUCTION","YIELD_GOLD","YIELD_SCIENCE","YIELD_CULTURE","YIELD_FAITH"}) do
    GameInfo.Yields[name]={Index=i-1}
end
yield_manager=setmetatable({}, {__index=function(_,key)
    if key:find("^Calculate") then return nil end
    return forbidden()
end})
Game.GetTradeManager=function() return yield_manager end
own_trade.GetInternationalYieldModifier=function(_,index)
    assert(index>=0 and index<=5)
    yield_reads.origin_multiplier=yield_reads.origin_multiplier+1
    return 1.5
end
foreign_trade={GetInternationalYieldModifier=function(_,index)
    assert(settings.met and index>=0 and index<=5)
    yield_reads.destination_multiplier=yield_reads.destination_multiplier+1
    return 2
end}
foreign_player.GetTrade=function() assert(settings.met);return foreign_trade end
for _,side in ipairs({"Origin","Destination"}) do
    for _,suffix in ipairs({"FromPotentialRoute","FromPath","FromModifiers"}) do
        yield_manager["Calculate"..side.."Yields"..suffix]=function(_,origin_owner,origin_id,owner,id)
            assert(origin_owner==0)
            assert((origin_id==20 and owner==1 and id==31 and settings.met and reads.foreign_lookup>0)
                or (origin_id==21 and owner==0 and id==20))
            yield_reads.route=yield_reads.route+1
            return yield_data[side][suffix]
        end
    end
end
-- Poison unapproved route fields, even when the native inventory contains them.
routes_a[1].OriginYields=nil
setmetatable(routes_a[1],{__index=forbidden})
''')
    return vm, run


def test_current_international_and_domestic_totals_match_both_stock_benefit_views(yields_engine):
    vm, run = yields_engine
    raw, values = run()
    assert raw["supported"] is True and values["active_count"] == 2
    assert values["route:10:origin_yield:YIELD_FOOD"] == 9
    assert values["route:10:origin_yield:YIELD_SCIENCE"] == 9
    assert values["route:10:origin_yield:YIELD_GOLD"] == -2  # Nonpositive totals are not multiplied.
    assert values["route:10:origin_yield:YIELD_PRODUCTION"] == 0
    assert values["route:10:destination_yield:YIELD_FAITH"] == 12
    assert values["route:11:origin_yield:YIELD_FOOD"] == 6  # Domestic routes ignore international modifiers.
    assert values["route:11:destination_yield:YIELD_FAITH"] == 6
    assert sum("_yield:" in key for key in values) == 24
    assert vm.globals().yield_reads.route == 12
    assert vm.globals().yield_reads.origin_multiplier == vm.globals().yield_reads.destination_multiplier == 6
    assert not any("path" in key or "religion" in key or "turns" in key for key in values)


@pytest.mark.parametrize("change", [
    'settings.met=false',
    'foreign_collection.FindID=function() return nil end',
    'foreign_city.GetOwner=function() return 2 end',
    'foreign_city.GetID=function() return 32 end',
])
def test_endpoint_must_be_known_and_exact_before_any_optional_yield_lookup(yields_engine, change):
    vm, run = yields_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is True and values["active_count"] == 2
    assert not any(key.startswith("route:10:") and "_yield:" in key for key in values)
    assert vm.globals().yield_reads.route == 6  # Only the domestic route.
    assert vm.globals().yield_reads.origin_multiplier == vm.globals().yield_reads.destination_multiplier == 0


def test_fogged_menu_endpoint_benefits_need_no_visibility_or_tile_or_raw_path_reads(yields_engine):
    vm, run = yields_engine
    # Even absent revelation only removes coordinates. An established route's
    # known endpoint benefit menu is still public; IsVisible/Map/path are traps.
    vm.execute("unrevealed['7,3']=true")
    _, values = run()
    assert values["route:10:origin_yield:YIELD_FOOD"] == 9
    assert values["route:10:destination_yield:YIELD_GOLD"] == 6
    assert "route:10:destination_x" not in values


def test_totals_keep_the_stock_overview_one_decimal_display_precision(yields_engine):
    vm, run = yields_engine
    vm.execute('yield_data.Destination.FromPotentialRoute[1]=1.23456789')
    _, values = run()
    assert values["route:10:destination_yield:YIELD_FOOD"] == 2.5
    assert values["route:11:destination_yield:YIELD_FOOD"] == 1.2


@pytest.mark.parametrize("change", [
    'Game.GetTradeManager=nil', 'Game.GetTradeManager=function() return nil end',
    'Game.GetTradeManager=function() error("private error") end',
    'GameInfo.Yields=nil', 'GameInfo.Yields.YIELD_GOLD=nil',
    'GameInfo.Yields.YIELD_GOLD.Index=0/0',
])
def test_missing_shared_yield_capabilities_preserve_inventory_without_fake_zero(yields_engine, change):
    vm, run = yields_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is True and values["active_count"] == 2
    assert values["trader:12:status"] == "idle"
    assert not any("_yield:" in key for key in values)


@pytest.mark.parametrize("change", [
    'yield_manager.CalculateOriginYieldsFromPath=nil',
    'yield_manager.CalculateOriginYieldsFromPath=function() error("private error") end',
    'yield_manager.CalculateOriginYieldsFromPath=function() return nil end',
    'yield_data.Origin.FromPath[3]=false',
    'yield_data.Origin.FromModifiers[3]=0/0',
    'yield_data.Origin.FromModifiers[3]=math.huge',
    'yield_data.Origin.FromModifiers[3]=2000000',
])
def test_one_bad_benefit_side_is_omitted_without_erasing_other_side_or_route(yields_engine, change):
    vm, run = yields_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is True
    assert not any(":origin_yield:" in key for key in values)
    assert values["route:10:destination_yield:YIELD_GOLD"] == 6
    assert values["route:11:destination_yield:YIELD_GOLD"] == 3


@pytest.mark.parametrize("change", [
    'foreign_trade.GetInternationalYieldModifier=nil',
    'foreign_trade.GetInternationalYieldModifier=function() return "unknown" end',
    'foreign_trade.GetInternationalYieldModifier=function() error("private error") end',
])
def test_missing_destination_multiplier_does_not_invent_one_or_erase_own_benefits(yields_engine, change):
    vm, run = yields_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is True
    assert not any(key.startswith("route:10:destination_yield:") for key in values)
    assert values["route:10:origin_yield:YIELD_FOOD"] == 9
    assert values["route:11:destination_yield:YIELD_GOLD"] == 3


@pytest.mark.parametrize("change", ['settings.busy=true', 'settings.active=1', 'settings.change_count=true'])
def test_unstable_inventory_cannot_publish_any_benefits(yields_engine, change):
    vm, run = yields_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is False and raw["items"] == [] and values == {}


@pytest.mark.parametrize("proof", [
    {"menu_yields_calculated": False}, {"menu_yields_calculated": 1},
    {"menu_destination_known": False}, {"menu_destination_owner_id": 64},
    {"menu_origin_owner_id": 1}, {"menu_unit_id": 11}, {"menu_source": "trade"},
    {"scope": "self", "owner_id": 0}, {"action": {}},
])
@pytest.mark.parametrize("side", ["origin", "destination"])
def test_yield_proof_is_checked_before_value_or_any_optional_raw_fields(yields_engine, proof, side):
    _, run = yields_engine
    raw, _ = run()
    row = next(item for item in raw["items"] if item["id"] == f"route:10:{side}_yield:YIELD_FOOD")
    raw["items"] = [{**row, **proof, "value": {"private": object()}}]
    assert public_inspection(raw, "own_trade_routes")["items"] == []


@pytest.mark.parametrize("value", [True, "1", None, float("nan"), float("inf"), -1_000_001, 1_000_001, 10**400, {}])
def test_numeric_yield_projection_rejects_bad_values(yields_engine, value):
    _, run = yields_engine
    raw, _ = run()
    row = next(item for item in raw["items"] if item["id"] == "route:10:origin_yield:YIELD_FOOD")
    raw["items"] = [{**deepcopy(row), "value": value}]
    with pytest.raises(PolicyError):
        public_inspection(raw, "own_trade_routes")


def test_unknown_yield_names_and_breakdowns_are_not_projected(yields_engine):
    _, run = yields_engine
    raw, _ = run()
    row = next(item for item in raw["items"] if item["id"] == "route:10:origin_yield:YIELD_FOOD")
    raw["items"] = [{**row, "id": identifier, "value": {"secret": object()}} for identifier in (
        "route:10:origin_yield:YIELD_URANIUM", "route:10:origin_path:YIELD_FOOD",
        "route:10:destination_yield:YIELD_RELIGIOUS_PRESSURE", "route:10:OriginYields",
    )]
    assert public_inspection(raw, "own_trade_routes")["items"] == []
