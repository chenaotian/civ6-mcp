"""Native adjacency only, including wrapping/boundaries without plot inspection."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions import build_inspection_query, registries
from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.neighbors import unit_neighbors
from civ6_fair_mcp.inspection_policy import public_inspection


@pytest.fixture
def neighbor_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
reads={secret=0,geometry=0}
function secret() reads.secret=reads.secret+1;error("SECRET_DESTINATION") end
settings={owner=0,x=2,y=2,width=8,height=6}
unit=setmetatable({GetOwner=function() return settings.owner end,
    GetID=function() assert(settings.owner==0);return 12 end,
    GetX=function() assert(settings.owner==0);return settings.x end,
    GetY=function() assert(settings.owner==0);return settings.y end},{__index=secret})
foreign=setmetatable({GetOwner=function() return 1 end},{__index=secret})
player=setmetatable({GetUnits=function() return {Members=function()
    local rows={foreign,unit};local i=0;return function() i=i+1;if rows[i] then return i,rows[i] end end
end} end},{__index=secret})
DirectionTypes={NUM_DIRECTION_TYPES=6,NO_DIRECTION=-1,
    DIRECTION_NORTHEAST=0,DIRECTION_EAST=1,DIRECTION_SOUTHEAST=2,
    DIRECTION_SOUTHWEST=3,DIRECTION_WEST=4,DIRECTION_NORTHWEST=5}
destinations={{2,1},{3,2},{2,3},{1,3},{1,2},{1,1}}
Map=setmetatable({
    GetGridSize=function() return settings.width,settings.height end,
    GetAdjacentPlot=function(x,y,direction)
        assert(x==settings.x and y==settings.y and direction>=0 and direction<6)
        reads.geometry=reads.geometry+1
        local value=destinations[direction+1]
        if value then
            return setmetatable({GetX=function() return value[1] end,
                GetY=function() return value[2] end},{__index=secret})
        end
    end}, {__index=secret})
vis=setmetatable({},{__index=secret})
UnitManager=setmetatable({},{__index=secret})
GameInfo=setmetatable({},{__index=secret})
''')

    def run(unit_id=12):
        result = vm.execute("local me=0;local out={items={}};\n" + LUA_HELPERS
            + "\nlocal function collect()\n" + unit_neighbors({"unit_id": unit_id})
            + "\nend\ncollect()\nreturn out")
        raw = {"ok": True, "session": "neighbor_tests_own", "player_id": 0, "turn": 62,
            "active_turn": True, "category": "unit_neighbors", "supported": result["supported"],
            "items": [dict(item) for item in result["items"].values()]}
        # Lupa nested tables need conversion for the actual action schema boundary.
        for item in raw["items"]:
            if "action" in item:
                item["action"] = dict(item["action"])
        projected = public_inspection(raw, "unit_neighbors")
        assert vm.globals().reads.secret == 0
        return projected
    return vm, run


def coords(result):
    return {(item["action"]["x"], item["action"]["y"]) for item in result["items"]}


def test_six_native_neighbors_are_existing_move_actions_without_destination_reads(neighbor_engine):
    vm, run = neighbor_engine
    result = run()
    assert result["supported"] is True and len(result["items"]) == 6
    assert coords(result) == {(2, 1), (3, 2), (2, 3), (1, 3), (1, 2), (1, 1)}
    assert vm.globals().reads.geometry == 6
    for item in result["items"]:
        assert item["action"]["type"] == "move" and item["action"]["unit_id"] == 12
        assert "不代表可通行" in item["description"]
        assert item["name"] == f'({item["action"]["x"]},{item["action"]["y"]})'


def test_off_map_native_nil_directions_are_omitted(neighbor_engine):
    vm, run = neighbor_engine
    vm.execute("settings.y=0;destinations={nil,{3,0},{2,1},{1,1},{1,0},nil}")
    result = run()
    assert result["supported"] is True and coords(result) == {(3, 0), (2, 1), (1, 1), (1, 0)}
    assert vm.globals().reads.geometry == 6


def test_wrapping_coordinates_are_taken_from_native_api_not_guessed(neighbor_engine):
    vm, run = neighbor_engine
    vm.execute("settings.x=0;destinations={{0,1},{1,2},{0,3},{7,3},{7,2},{7,1}}")
    result = run()
    assert result["supported"] is True
    assert coords(result) == {(0, 1), (1, 2), (0, 3), (7, 3), (7, 2), (7, 1)}


def test_degenerate_wrap_deduplicates_and_excludes_own_coordinate(neighbor_engine):
    vm, run = neighbor_engine
    vm.execute("settings.x=0;settings.width=1;destinations={{0,1},{0,2},{0,3},{0,3},{0,2},{0,1}}")
    result = run()
    assert result["supported"] is True and len(result["items"]) == 2
    assert coords(result) == {(0, 1), (0, 3)}


@pytest.mark.parametrize("x,y,returned", [
    (2, 2, "{{7,1},{5,2}}"), (2, 3, "{{0,5},{4,2}}"),
])
def test_no_parity_or_distance_formula_replaces_native_coordinates(neighbor_engine, x, y, returned):
    vm, run = neighbor_engine
    vm.execute(f"settings.x={x};settings.y={y};destinations={returned}")
    result = run()
    assert len(result["items"]) == 2
    # Deliberately unusual native answers prove there is no hand-coded offset
    # or wrap formula here; actual move remains responsible for distance checks.
    assert coords(result) == ({(7, 1), (5, 2)} if y == 2 else {(0, 5), (4, 2)})


@pytest.mark.parametrize("change", [
    "settings.owner=1;unit.GetID=secret;unit.GetX=secret;unit.GetY=secret",
    "unit.GetID=function() return 13 end;unit.GetX=secret;unit.GetY=secret",
])
def test_foreign_or_missing_unit_never_reads_location_or_geometry(neighbor_engine, change):
    vm, run = neighbor_engine
    vm.execute(change)
    result = run()
    assert result["supported"] is False and result["items"] == []
    assert vm.globals().reads.geometry == 0


@pytest.mark.parametrize("change", [
    "Map.GetAdjacentPlot=nil", "Map.GetGridSize=nil", "DirectionTypes=nil",
    "DirectionTypes.DIRECTION_EAST=nil", "DirectionTypes.DIRECTION_EAST=0",
    "DirectionTypes.NUM_DIRECTION_TYPES=7",
    "Map.GetAdjacentPlot=function() error('SECRET_FAILURE') end",
])
def test_missing_native_geometry_fails_closed(neighbor_engine, change):
    vm, run = neighbor_engine
    vm.execute("setmetatable(Map,nil)")
    vm.execute(change)
    result = run()
    assert result["supported"] is False and result["items"] == []


@pytest.mark.parametrize("change", [
    "settings.width=0", "settings.height=4097", "settings.x=-1", "settings.y=6",
    "destinations[6]={8,1}", "destinations[6]={1,-1}",
    "destinations[6]={1.5,1}", "destinations[6]={0/0,1}",
])
def test_bad_or_out_of_bounds_coordinate_discards_partial_output(neighbor_engine, change):
    vm, run = neighbor_engine
    vm.execute(change)
    result = run()
    assert result["supported"] is False and result["items"] == []


def test_registry_only_adds_read_category_with_owned_unit_parameter():
    actions, queries = registries()
    assert "unit_neighbors" not in actions
    assert queries["unit_neighbors"].fields == {"unit_id": "id"}
    for params in ({}, {"unit_id": True}, {"unit_id": 12, "player_id": 1}):
        with pytest.raises(ValueError):
            build_inspection_query("neighbor_check", "unit_neighbors", params)
    LuaRuntime().execute("assert(load(...))", build_inspection_query(
        "neighbor_check", "unit_neighbors", {"unit_id": 12}))
