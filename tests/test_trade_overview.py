"""Own active-route inventory, direct menu endpoint proof and no fog probes."""
from copy import deepcopy

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions import registries
from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.trade_overview import ACTIONS, QUERIES
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import PolicyError


@pytest.fixture
def overview_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
rawget=nil;table.unpack=nil;unpack=nil
settings={active=2,capacity=4,busy=false,met=true,change_count=false}
reads={secret=0,foreign_lookup=0,foreign_name=0,foreign_geometry=0,count=0}
function forbidden() reads.secret=reads.secret+1;error("SECRET_WORLD") end
function members(list)
    local i=0;return function() i=i+1;if list[i] then return i,list[i] end end
end
routes_a={{OriginCityPlayer=0,OriginCityID=20,DestinationCityPlayer=1,DestinationCityID=31,
    TraderUnitID=10,TurnsRemaining='SECRET_UNAUDITED',OriginYields='UNUSED'}}
routes_b={{OriginCityPlayer=0,OriginCityID=21,DestinationCityPlayer=0,DestinationCityID=20,TraderUnitID=11}}
city_a={GetOwner=function() return 0 end,GetID=function() return 20 end,GetName=function() return '首都' end,
    GetX=function() return 2 end,GetY=function() return 2 end,
    GetTrade=function() return {GetOutgoingRoutes=function() return routes_a end} end}
city_b={GetOwner=function() return 0 end,GetID=function() return 21 end,GetName=function() return '第二城' end,
    GetX=function() return 3 end,GetY=function() return 2 end,
    GetTrade=function() return {GetOutgoingRoutes=function() return routes_b end} end}
foreign_city=setmetatable({GetOwner=function() return 1 end,
    GetID=function() return 31 end,GetName=function() reads.foreign_name=reads.foreign_name+1;return '已遇见目的地' end,
    GetX=function() reads.foreign_geometry=reads.foreign_geometry+1;return 7 end,
    GetY=function() reads.foreign_geometry=reads.foreign_geometry+1;return 3 end},{__index=forbidden})
function unit(id,kind)
    return setmetatable({GetOwner=function() return 0 end,GetID=function() return id end,
        GetUnitType=function() return kind end},{__index=forbidden})
end
trader_a=unit(10,1);trader_b=unit(11,1);trader_idle=unit(12,1);warrior=unit(13,2)
foreign=setmetatable({GetOwner=function() return 1 end},{__index=forbidden})
city_list={foreign,city_a,city_b};unit_list={foreign,trader_a,trader_b,trader_idle,warrior}
own_cities={Members=function() return members(city_list) end,
    FindID=function(self,id) if id==20 then return city_a elseif id==21 then return city_b end end}
own_units={Members=function() return members(unit_list) end}
own_trade={GetNumOutgoingRoutes=function()
    reads.count=reads.count+1
    if settings.change_count and reads.count>1 then return settings.active+1 end
    return settings.active
end,GetOutgoingRouteCapacity=function() return settings.capacity end}
diplomacy={HasMet=function(self,id) assert(id==1 or id==2);return id==1 and settings.met end}
player={GetCities=function() return own_cities end,GetUnits=function() return own_units end,
    GetTrade=function() return own_trade end,GetDiplomacy=function() return diplomacy end}
foreign_collection={Members=forbidden,FindID=function(self,id)
    assert(settings.met and id==31);reads.foreign_lookup=reads.foreign_lookup+1;return foreign_city
end}
foreign_player=setmetatable({GetCities=function() return foreign_collection end},{__index=forbidden})
Players=setmetatable({[0]=player,[1]=foreign_player},{__index=forbidden})
GameInfo={Units={[1]={MakeTradeRoute=true},[2]={MakeTradeRoute=false}}}
UI={IsGameCoreBusy=function() return settings.busy end}
Locale={Lookup=function(text) return text end}
unrevealed={}
vis={IsVisible=forbidden,IsRevealed=function(self,x,y)
    assert((x==7 and y==3) or (x==2 and y==2));return not unrevealed[x..','..y]
end}
Map=setmetatable({}, {__index=forbidden})
Game=setmetatable({GetTradeManager=function() return nil end}, {__index=function(_,key)
    if key=="GetTradeManager" then return nil end
    return forbidden()
end})
UnitManager=setmetatable({}, {__index=forbidden})
''')

    def run():
        result = vm.execute('local me=0;local out={items={}}\n' + LUA_HELPERS
            + '\nlocal function query()\n' + QUERIES['own_trade_routes'].body({})
            + '\nend\nquery()\nreturn out')
        raw = {"ok": True, "session": "trade_overview_tests", "player_id": 0, "turn": 108,
            "active_turn": True, "category": "own_trade_routes", "supported": result["supported"],
            "items": [dict(item) for item in result["items"].values()]}
        assert vm.globals().reads.secret == 0
        public = public_inspection(raw, "own_trade_routes")
        assert all(set(row) == {"id", "value"} for row in public["items"])
        return raw, {row["id"]: row["value"] for row in public["items"]}
    return vm, run


def test_current_routes_capacity_trader_association_and_idle_follow_stock_inventory(overview_engine):
    vm, run = overview_engine
    raw, values = run()
    assert raw["supported"] is True
    assert values["active_count"] == 2 and values["capacity"] == 4 and values["idle_trader_count"] == 1
    assert values["trader:10:status"] == values["trader:11:status"] == "active"
    assert values["trader:12:status"] == "idle" and "trader:13:status" not in values
    assert values["route:10:trader_unit_id"] == 10 and values["route:10:origin_city_id"] == 20
    assert values["route:10:origin_name"] == "首都"
    assert values["route:10:destination_name"] == "已遇见目的地"
    assert values["route:10:destination_owner_id"] == 1
    assert values["route:10:destination_x"] == 7 and values["route:10:destination_y"] == 3
    assert values["route:11:destination_name"] == "首都"
    assert vm.globals().reads.foreign_lookup == 1 and vm.globals().reads.foreign_name == 1
    assert not any("turns" in key or "yield" in key or "path" in key for key in values)
    assert not ACTIONS and not QUERIES['own_trade_routes'].fields


def test_active_routes_can_exceed_capacity_without_losing_the_native_inventory(overview_engine):
    vm, run = overview_engine
    vm.execute('settings.capacity=1')
    raw, values = run()
    assert raw["supported"] is True and values["active_count"] == 2 and values["capacity"] == 1


def test_zero_routes_marks_own_traders_idle_without_looking_up_any_foreign_city(overview_engine):
    vm, run = overview_engine
    vm.execute('routes_a={};routes_b={};settings.active=0')
    raw, values = run()
    assert raw["supported"] is True and values["active_count"] == 0 and values["idle_trader_count"] == 3
    assert all(values[f"trader:{unit_id}:status"] == "idle" for unit_id in (10, 11, 12))
    assert vm.globals().reads.foreign_lookup == 0


def test_idle_does_not_claim_route_finished_or_cancelled_or_infer_from_moves(overview_engine):
    _, run = overview_engine  # Unit position/move/activity getters are traps.
    _, values = run()
    assert values["trader:12:status"] == "idle"
    assert not any("cancel" in key or "finish" in key or "end_reason" in key for key in values)


@pytest.mark.parametrize("change", ['settings.met=false', 'routes_a[1].DestinationCityPlayer=2'])
def test_unknown_destination_owner_is_not_looked_up_or_named(overview_engine, change):
    vm, run = overview_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is True and values["trader:10:status"] == "active"
    assert not any(key.startswith("route:10:destination") for key in values)
    assert vm.globals().reads.foreign_lookup == vm.globals().reads.foreign_geometry == 0


def test_fog_known_menu_endpoint_is_named_but_unrevealed_coordinates_are_not_returned(overview_engine):
    vm, run = overview_engine
    vm.execute("unrevealed['7,3']=true")
    raw, values = run()
    assert raw["supported"] is True and values["route:10:destination_name"] == "已遇见目的地"
    assert not {"route:10:destination_x", "route:10:destination_y"} & values.keys()
    assert vm.globals().reads.foreign_geometry == 2


@pytest.mark.parametrize("change", [
    'foreign_collection.FindID=function() return nil end',
    'foreign_collection.FindID=function() error("unavailable") end',
    'foreign_city.GetOwner=function() return 2 end',
    'foreign_city.GetID=function() return 32 end',
])
def test_endpoint_loss_or_capture_does_not_erase_the_current_own_route_or_invent_reason(overview_engine, change):
    vm, run = overview_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is True and values["active_count"] == 2
    assert values["route:10:trader_unit_id"] == 10 and values["trader:10:status"] == "active"
    assert "route:10:destination_name" not in values
    assert vm.globals().reads.foreign_name == 0


@pytest.mark.parametrize("change", [
    'settings.busy=true', 'settings.busy=nil', 'UI.IsGameCoreBusy=nil',
    'player.GetTrade=nil', 'own_trade.GetNumOutgoingRoutes=nil', 'settings.active=-1',
    'settings.active=1', 'settings.capacity=0/0', 'settings.change_count=true',
    'city_a.GetTrade=nil', 'city_a.GetTrade=function() return nil end',
    'routes_a=nil', 'routes_a={[2]=routes_a[1]}', 'routes_b[1].TraderUnitID=10',
    'routes_a[1].OriginCityPlayer=1', 'routes_a[1].OriginCityID=21',
    'routes_a[1].TraderUnitID=-1', 'routes_a[1].DestinationCityPlayer=64',
    'routes_a[1].DestinationCityID=1.5', 'own_units.Members=nil', 'GameInfo.Units[1]=nil',
    'GameInfo.Units[1].MakeTradeRoute="unknown"', 'unit_list={trader_a,trader_a}',
    'city_list={city_a,city_a}',
])
def test_incomplete_or_inconsistent_inventory_never_reports_idle_or_partial_rows(overview_engine, change):
    vm, run = overview_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is False and raw["items"] == [] and values == {}


def test_wrong_origin_rejected_before_any_other_route_field(overview_engine):
    vm, run = overview_engine
    vm.execute('routes_a={setmetatable({OriginCityPlayer=1},{__index=forbidden})}')
    raw, values = run()
    assert raw["supported"] is False and values == {} and vm.globals().reads.foreign_lookup == 0


def test_linked_route_survives_an_own_unit_temporarily_missing_from_collection(overview_engine):
    vm, run = overview_engine
    vm.execute('unit_list={trader_b,trader_idle,warrior}')
    raw, values = run()
    assert raw["supported"] is True and values["route:10:trader_unit_id"] == 10
    assert "trader:10:status" not in values and values["idle_trader_count"] == 1


@pytest.mark.parametrize("change", [
    'foreign_city.GetName=function() error("unavailable") end',
    'Locale.Lookup=function() error("unavailable") end',
    'vis.IsRevealed=nil', 'vis.IsRevealed=function() error("unavailable") end',
    'foreign_city.GetX=function() return -1 end',
])
def test_optional_endpoint_fields_do_not_erase_an_established_route(overview_engine, change):
    vm, run = overview_engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is True and values["active_count"] == 2
    assert values["trader:10:status"] == "active"


@pytest.mark.parametrize("change", [
    {"scope": "self", "owner_id": 0}, {"scope": "public"}, {"scope": "met", "met": True},
    {"scope": "visible", "visible": True, "x": 7, "y": 3}, {"menu_offered": False},
    {"menu_source": "trade"}, {"menu_owner_id": 1}, {"menu_unit_id": 11},
    {"menu_origin_owner_id": 1}, {"menu_destination_known": False}, {"action": {}},
])
def test_endpoint_cannot_forge_scope_or_menu_proof_before_value_validation(overview_engine, change):
    _, run = overview_engine
    raw, _ = run()
    row = next(row for row in raw["items"] if row["id"] == "route:10:destination_name")
    raw["items"] = [{**row, **change, "value": {"secret": "DO_NOT_READ"}}]
    assert public_inspection(raw, "own_trade_routes")["items"] == []


def test_coordinates_require_menu_revelation_proof_and_arbitrary_fields_are_dropped(overview_engine):
    _, run = overview_engine
    raw, _ = run()
    coordinate = next(row for row in raw["items"] if row["id"] == "route:10:destination_x")
    raw["items"] = [{**coordinate, "menu_destination_revealed": False, "value": {}},
        {**coordinate, "id": "route:10:turns_remaining", "value": 10}]
    assert public_inspection(raw, "own_trade_routes")["items"] == []


def test_projection_has_an_exact_field_allowlist_no_raw_names_or_objects(overview_engine):
    _, run = overview_engine
    raw, expected = run()
    for row in raw["items"]:
        row.update(name="SECRET", description="SECRET", raw_path=[1, 2], secret=object())
    public = public_inspection(raw, "own_trade_routes")
    assert {row["id"]: row["value"] for row in public["items"]} == expected
    assert all(set(row) == {"id", "value"} for row in public["items"])


def test_unsupported_inventory_cannot_leak_partial_idle_counts_or_endpoint_records(overview_engine):
    _, run = overview_engine
    raw, _ = run()
    raw["supported"] = False
    for row in raw["items"]:
        row["value"] = {"untrusted_partial_value": object()}
    result = public_inspection(raw, "own_trade_routes")
    assert result["supported"] is False and result["items"] == []


@pytest.mark.parametrize("identifier,value", [
    ("active_count", True), ("capacity", -1), ("trader:10:status", "cancelled"),
    ("route:10:trader_unit_id", 11), ("route:10:origin_city_id", 21),
    ("route:10:destination_owner_id", 2), ("route:10:destination_x", 4096),
])
def test_projection_rejects_invalid_public_values_and_mismatched_identity(overview_engine, identifier, value):
    _, run = overview_engine
    raw, _ = run()
    row = next(row for row in raw["items"] if row["id"] == identifier)
    raw["items"] = [{**deepcopy(row), "value": value}]
    with pytest.raises(PolicyError):
        public_inspection(raw, "own_trade_routes")


def test_query_registration_has_no_selectors_or_executable_actions():
    actions, queries = registries()
    assert "own_trade_routes" in queries and "own_trade_routes" not in actions
    with pytest.raises(ValueError):
        validate({"player_id": 1}, queries["own_trade_routes"].fields)
