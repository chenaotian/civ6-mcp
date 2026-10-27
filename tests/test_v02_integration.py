"""Run combined map templates through JSON projection and the service boundary."""

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.policy import parse_response, public_map
from civ6_fair_mcp.queries import build_map_query
from civ6_fair_mcp.service import FairGameService
from test_queries import ENGINE


EXTENSION = r'''
integration={enumerations=0, hidden_unit_reads=0, hidden_city_reads=0,
    gates=0, city_lookups=0, city_details=0, center_lookups=0}
function integration_forbidden()
    error('SECRET_UNAUTHORIZED_VALUE')
end
units={}
detection={}
gate_seen={}
local function hidden_unit()
    local unit=setmetatable({}, {__index=function()
        integration.hidden_unit_reads=integration.hidden_unit_reads+1
        integration_forbidden()
    end})
    detection[unit]=false
    return unit
end
function add_hidden_units(count)
    for i=1,count do units[#units+1]=hidden_unit() end
end
function observable_unit(id)
    local unit={}
    local function read(value)
        assert(gate_seen[unit]==true, 'GETTER_BEFORE_DETECTION')
        return value
    end
    unit.IsDelayedDeath=function() return read(false) end
    unit.GetOwner=function() return read(9) end
    unit.GetID=function() return read(id) end
    unit.GetX=function() return read(2) end
    unit.GetY=function() return read(0) end
    unit.GetUnitType=function() return read(0) end
    unit.GetName=function() return read('visible warrior') end
    unit.GetDamage=function() return read(5) end
    unit.GetMaxDamage=function() return read(100) end
    unit.GetCombat=function() return read(20) end
    unit.GetRangedCombat=function() return read(0) end
    detection[unit]=true
    return unit
end
visible_unit=observable_unit(10)
stealth_unit=observable_unit(11)
detection[stealth_unit]=false
units={visible_unit,stealth_unit}
add_hidden_units(3)
visibility.IsUnitVisible=function(self,unit)
    integration.gates=integration.gates+1
    if detection[unit]==true then gate_seen[unit]=true end
    return detection[unit]
end
MapLayers={ANY=99}
Units={GetUnitsInPlotLayerID=function(x,y,layer)
    assert(x==2 and y==0 and layer==99)
    integration.enumerations=integration.enumerations+1
    return units
end}
for index=0,1 do
    plots[index].IsCity=function()
        integration.hidden_city_reads=integration.hidden_city_reads+1
        integration_forbidden()
    end
end
plots[2].IsCity=function() return true end
GameInfo.Buildings[0].Index=0
GameInfo.Buildings[101]=GameInfo.Buildings[0]
GameInfo.Religions={[1]={ReligionType='RELIGION_BUDDHISM'}}
local center_definition={Index=1,Hash=201,DistrictType='DISTRICT_CITY_CENTER'}
GameInfo.Districts=setmetatable({[1]=center_definition,[201]=center_definition},
    {__call=function() local done=false; return function()
        if not done then done=true; return center_definition end
    end end})
local function city_detail(value)
    integration.city_details=integration.city_details+1
    return value
end
visible_city={GetX=function() return 2 end,GetY=function() return 0 end,
    GetOwner=function() return city_detail(9) end, GetID=function() return city_detail(22) end,
    GetName=function() return city_detail('visible city') end,
    GetPopulation=function() return city_detail(6) end,
    GetReligion=function() return {GetMajorityReligion=function() return 1 end} end,
    GetBuildQueue=function() return {
        GetCurrentProductionTypeHash=function() return 101 end,
        GetTurnsLeft=function(self,identifier) assert(identifier=='BUILDING_MONUMENT'); return 4 end
    } end,
    GetBuildings=function() return {HasBuilding=function(self,index) return index==0 end} end,
    GetDistricts=function() return {HasDistrict=function(self,index,completed)
        assert(completed==true); return index==1
    end} end}
local center={GetX=function() return 2 end,GetY=function() return 0 end,
    GetOwner=function() return 9 end,GetType=function() return 1 end,
    GetDamage=function(self,kind) return kind==0 and 20 or 10 end,
    GetMaxDamage=function(self,kind) return kind==0 and 200 or 100 end}
DefenseTypes={DISTRICT_GARRISON=0,DISTRICT_OUTER=1}
CityManager={GetCityAt=function(x,y)
    assert(x==2 and y==0); integration.city_lookups=integration.city_lookups+1
    return visible_city
end,GetDistrictAt=function(x,y)
    assert(x==2 and y==0); integration.center_lookups=integration.center_lookups+1
    return center
end}
'''


class LuaTransport:
    connection_generation = 1

    def __init__(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(ENGINE + EXTENSION)
        self.lines = []
        self.lua.globals().print = self.lines.append
        self.closed = False

    def evaluate(self, script):
        self.lines.clear()
        self.lua.execute(script)
        assert len(self.lines) == 2
        assert self.lines[-1] == "---END---"
        serialized = "\n".join(self.lines)
        assert "SECRET" not in serialized
        return serialized

    async def execute(self, script, context="InGame", *, expected_generation=None):
        assert context == "InGame"
        return self.evaluate(script)

    async def close(self):
        self.closed = True


@pytest.fixture
def transport():
    return LuaTransport()


def projected(transport, x=1, radius=2):
    script = build_map_query("a" * 32, x, 0, radius)
    return public_map(parse_response(transport.evaluate(script)))


def test_combined_helpers_preserve_visibility_detection_and_projection(transport):
    result = projected(transport)
    tiles = {tile["x"]: tile for tile in result["tiles"]}
    assert tiles[0] == {"x": 0, "y": 0, "revealed": False, "visible": False}
    assert tiles[1] == {"x": 1, "y": 0, "revealed": True, "visible": False}
    assert tiles[2]["units"] == [{"owner_id": 9, "id": 10, "x": 2, "y": 0,
        "type": "UNIT_WARRIOR", "name": "visible warrior", "damage": 5,
        "max_damage": 100, "combat": 20, "ranged_combat": 0}]
    assert tiles[2]["city"] == {"owner_id": 9, "id": 22, "x": 2, "y": 0,
        "name": "visible city", "population": 6, "damage": 20, "max_damage": 200,
        "wall_damage": 10, "wall_max_damage": 100, "religion": "RELIGION_BUDDHISM",
        "production": "BUILDING_MONUMENT", "production_turns": 4,
        "districts": ["DISTRICT_CITY_CENTER"], "buildings": ["BUILDING_MONUMENT"]}
    assert tiles[2]["resource"] == "RESOURCE_IRON"
    assert transport.lua.globals().integration.hidden_unit_reads == 0
    assert transport.lua.globals().integration.hidden_city_reads == 0
    assert transport.lua.globals().counts.hidden_reads == 0
    assert transport.lua.globals().counts.foreign_reads == 0


def test_hidden_unit_count_and_unrevealed_city_changes_cannot_change_combined_output(transport):
    baseline = projected(transport)
    transport.lua.execute("""
        add_hidden_units(1000)
        plots[0].IsCity=function() integration.hidden_city_reads=integration.hidden_city_reads+1; return true end
        plots[1].IsCity=function() integration.hidden_city_reads=integration.hidden_city_reads+1; return true end
    """)
    assert projected(transport) == baseline
    assert transport.lua.globals().integration.hidden_unit_reads == 0
    assert transport.lua.globals().integration.hidden_city_reads == 0


def test_unit_detection_changes_without_using_visible_terrain_as_proxy(transport):
    assert [unit["id"] for unit in projected(transport, 2, 0)["tiles"][0]["units"]] == [10]
    transport.lua.execute("detection[stealth_unit]=true")
    assert [unit["id"] for unit in projected(transport, 2, 0)["tiles"][0]["units"]] == [10, 11]
    transport.lua.execute("detection[stealth_unit]=false; gate_seen[stealth_unit]=nil")
    assert [unit["id"] for unit in projected(transport, 2, 0)["tiles"][0]["units"]] == [10]


def test_missing_unit_detector_does_not_disable_visible_city_or_probe_units(transport):
    transport.lua.execute("visibility.IsUnitVisible=nil")
    tile = projected(transport, 2, 0)["tiles"][0]
    assert "units" not in tile
    assert tile["city"]["id"] == 22
    assert transport.lua.globals().integration.enumerations == 0


def test_misdirected_city_lookup_cannot_pull_remote_identity_into_visible_tile(transport):
    transport.lua.execute("""
        visible_city=setmetatable({GetX=function() return 99 end,GetY=function() return 99 end},
            {__index=function() integration.hidden_city_reads=integration.hidden_city_reads+1; integration_forbidden() end})
    """)
    tile = projected(transport, 2, 0)["tiles"][0]
    assert "city" not in tile
    assert len(tile["units"]) == 1
    assert transport.lua.globals().integration.hidden_city_reads == 0
    assert transport.lua.globals().integration.center_lookups == 0


@pytest.mark.asyncio
async def test_service_projects_combined_response_and_drops_contents_after_fog_returns(transport):
    service = FairGameService(transport)
    visible = await service.observe_area(2, 0, 0)
    assert visible["ok"] is True and "observation_token" in visible
    assert visible["tiles"][0]["city"]["id"] == 22
    assert "detected" not in visible["tiles"][0]["units"][0]
    assert "visible" not in visible["tiles"][0]["city"]
    before = dict(transport.lua.globals().integration)
    transport.lua.execute("visibility.IsVisible=function() return false end")
    fog = await service.observe_area(2, 0, 0)
    assert fog["ok"] is True and "observation_token" in fog
    assert fog["tiles"] == [{"x": 2, "y": 0, "revealed": True, "visible": False}]
    assert dict(transport.lua.globals().integration) == before
    assert not transport.closed
