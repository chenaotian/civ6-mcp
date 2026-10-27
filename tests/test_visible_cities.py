"""Hostile Lua fixtures ensure city details remain gated by exact visibility."""

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.visible_cities import CITY_HELPERS


BOOTSTRAP = r'''
controls={revealed=true, visible=true, is_city=true, city_exists=true,
    city_x=4, city_y=6, owner=2, population=7, center_x=4, center_y=6,
    center_owner=2, center_type=1, majority=3, hash=303, turns=8, walls=100}
reads={city_lookup=0, is_city=0, city_details=0, health=0, district_lookup=0,
    districts=0, buildings=0, production=0, visibility=0}
function forbidden() error('SECRET_OFFSCREEN_CITY') end
function array(value) return value end
vis={IsRevealed=function(self,index) assert(index==77); return controls.revealed end,
    IsVisible=function(self,index)
        assert(index==77); reads.visibility=reads.visibility+1
        if controls.hide_after and reads.visibility>controls.hide_after then return false end
        return controls.visible
    end}
test_plot={GetIndex=function() return 77 end, GetX=function() return 4 end,
    GetY=function() return 6 end, IsCity=function() reads.is_city=reads.is_city+1; return controls.is_city end}
Locale={Lookup=function(value) return value end}
Players=setmetatable({},{__index=forbidden})
Game={GetReligion=forbidden}
Map=setmetatable({},{__index=forbidden})
DefenseTypes={DISTRICT_GARRISON=0,DISTRICT_OUTER=1}
function definitions(field, rows)
    local result={}
    for _,row in ipairs(rows) do
        result[row[field]]=row
        result[row.Index]=row
        result[row.Hash]=row
    end
    return setmetatable(result,{__call=function()
        local i=0
        return function() i=i+1; return rows[i] end
    end})
end
GameInfo={
    Districts=definitions('DistrictType',{
        {DistrictType='DISTRICT_CITY_CENTER',Index=1,Hash=101},
        {DistrictType='DISTRICT_CAMPUS',Index=2,Hash=102},
        {DistrictType='DISTRICT_HIDDEN_PLACEMENT',Index=3,Hash=103}}),
    Buildings=definitions('BuildingType',{
        {BuildingType='BUILDING_MONUMENT',Index=1,Hash=201},
        {BuildingType='BUILDING_LIBRARY',Index=2,Hash=202},
        {BuildingType='BUILDING_INTERNAL_ONLY',Index=3,Hash=203,InternalOnly=true}}),
    Units=definitions('UnitType',{{UnitType='UNIT_WARRIOR',Index=1,Hash=303}}),
    Projects=definitions('ProjectType',{{ProjectType='PROJECT_ENHANCE_DISTRICT_CAMPUS',Index=1,Hash=401}}),
    Religions=definitions('ReligionType',{{ReligionType='RELIGION_BUDDHISM',Index=3,Hash=501}})}
local function detail(value) reads.city_details=reads.city_details+1; return value end
districts={HasDistrict=function(self,index,completed)
    assert(completed==true); reads.districts=reads.districts+1
    return index<3
end, Members=forbidden, GetDistrictAt=forbidden}
buildings={HasBuilding=function(self,index)
    reads.buildings=reads.buildings+1; return index==1
end, GetBuildingsAtLocation=forbidden}
queue={GetCurrentProductionTypeHash=function() reads.production=reads.production+1; return controls.hash end,
    GetCurrentProductionTypeModifier=function() return 2 end,
    GetTurnsLeft=function(self,identifier,formation)
        if identifier=='UNIT_WARRIOR' then assert(formation==2) else assert(formation==nil) end
        return controls.turns
    end, GetSize=forbidden, GetAt=forbidden, GetUnitProgress=forbidden}
city={GetX=function() return controls.city_x end, GetY=function() return controls.city_y end,
    GetOwner=function() return detail(controls.owner) end,
    GetID=function() return detail(80002) end, GetName=function() return detail('测试城市') end,
    GetPopulation=function() return detail(controls.population) end,
    GetReligion=function() detail(); return {GetMajorityReligion=function() return controls.majority end} end,
    GetBuildQueue=function() detail(); return queue end,
    GetDistricts=function() detail(); return districts end,
    GetBuildings=function() detail(); return buildings end,
    GetYield=forbidden, GetGrowth=forbidden, GetPurchasedPlots=forbidden}
center={GetX=function() return controls.center_x end, GetY=function() return controls.center_y end,
    GetOwner=function() return controls.center_owner end, GetType=function() return controls.center_type end,
    GetDamage=function(self,kind) reads.health=reads.health+1; return kind==0 and 30 or 20 end,
    GetMaxDamage=function(self,kind) reads.health=reads.health+1; return kind==0 and 200 or controls.walls end}
CityManager={GetCityAt=function(x,y)
    assert(x==4 and y==6); reads.city_lookup=reads.city_lookup+1
    if controls.city_exists then return city end
end, GetDistrictAt=function(x,y)
    assert(x==4 and y==6); reads.district_lookup=reads.district_lookup+1; return center
end, GetCity=forbidden}
'''


@pytest.fixture
def engine():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(BOOTSTRAP)

    def read(index=77):
        return lua.execute(CITY_HELPERS + f"\nreturn visible_city_at(test_plot, {index})")

    return lua, read


EXPECTED = {
    "id": 80002, "owner_id": 2, "x": 4, "y": 6, "name": "测试城市",
    "population": 7, "visible": True, "damage": 30, "max_damage": 200,
    "wall_damage": 20, "wall_max_damage": 100, "religion": "RELIGION_BUDDHISM",
    "production": "UNIT_WARRIOR", "production_turns": 8,
}


def test_visible_foreign_city_has_only_authorized_fields(engine):
    lua, read = engine
    result = dict(read())
    assert list(result.pop("districts").values()) == ["DISTRICT_CAMPUS", "DISTRICT_CITY_CENTER"]
    assert list(result.pop("buildings").values()) == ["BUILDING_MONUMENT"]
    assert result == EXPECTED
    assert lua.globals().reads.city_lookup == 1
    assert lua.globals().reads.district_lookup == 1


@pytest.mark.parametrize("visible,revealed", [(False, False), (False, True), (True, False)])
def test_hidden_city_getters_and_even_city_existence_are_never_read(engine, visible, revealed):
    lua, read = engine
    lua.globals().controls.visible = visible
    lua.globals().controls.revealed = revealed
    assert read() is None
    counts = dict(lua.globals().reads)
    assert all(value == 0 for key, value in counts.items() if key != "visibility")


@pytest.mark.parametrize("setting,value", [("is_city", False), ("city_exists", False)])
def test_empty_visible_cell_has_no_city_detail_reads(engine, setting, value):
    lua, read = engine
    lua.globals().controls[setting] = value
    assert read() is None
    assert lua.globals().reads.city_details == 0
    assert lua.globals().reads.district_lookup == 0


@pytest.mark.parametrize("axis", ["city_x", "city_y"])
def test_purchase_city_or_remote_city_mismatch_rejected_before_details(engine, axis):
    lua, read = engine
    lua.globals().controls[axis] = 40
    assert read() is None
    assert lua.globals().reads.city_details == 0
    assert lua.globals().reads.district_lookup == 0


def test_wrong_plot_index_is_rejected_before_city_existence_query(engine):
    lua, read = engine
    lua.execute("test_plot.GetIndex=function() return 99 end")
    assert read() is None
    assert lua.globals().reads.is_city == 0
    assert lua.globals().reads.city_lookup == 0


def test_visibility_revoked_during_lookup_prevents_detail_reads(engine):
    lua, read = engine
    lua.globals().controls.hide_after = 1
    assert read() is None
    assert lua.globals().reads.city_details == 0


def test_visibility_revoked_at_completion_discards_result(engine):
    lua, read = engine
    lua.globals().controls.hide_after = 2
    assert read() is None


@pytest.mark.parametrize("setting,value", [
    ("center_x", 40), ("center_y", 40), ("center_owner", 3), ("center_type", 2),
])
def test_noncenter_district_never_supplies_defense_or_offscreen_details(engine, setting, value):
    lua, read = engine
    lua.globals().controls[setting] = value
    result = dict(read())
    assert "damage" not in result and "max_damage" not in result
    assert "wall_damage" not in result and "wall_max_damage" not in result
    assert lua.globals().reads.health == 0
    assert result["population"] == 7


@pytest.mark.parametrize("missing,omitted", [
    ("CityManager.GetDistrictAt", {"damage", "max_damage", "wall_damage", "wall_max_damage"}),
    ("city.GetReligion", {"religion"}),
    ("city.GetBuildQueue", {"production", "production_turns"}),
    ("districts.HasDistrict", {"districts"}),
    ("buildings.HasBuilding", {"buildings"}),
])
def test_missing_optional_capabilities_are_omitted_without_guessing(engine, missing, omitted):
    lua, read = engine
    lua.execute(missing + "=nil")
    result = dict(read())
    assert not omitted & result.keys()
    assert result["name"] == "测试城市"


def test_optional_engine_errors_are_opaque_and_other_fields_survive(engine):
    lua, read = engine
    lua.execute("queue.GetCurrentProductionTypeHash=forbidden")
    result = dict(read())
    assert "production" not in result
    assert "SECRET" not in repr(result)
    assert result["religion"] == "RELIGION_BUDDHISM"


def test_multibyte_city_name_is_not_truncated_inside_a_utf8_character(engine):
    lua, read = engine
    lua.globals().long_name = "京" * 100
    lua.execute("city.GetName=function() return long_name end")
    assert read().name == "京" * 100


def test_oversized_city_name_is_rejected_without_partial_text(engine):
    lua, read = engine
    lua.globals().long_name = "京" * 257
    lua.execute("city.GetName=function() return long_name end")
    assert read() is None


@pytest.mark.parametrize("hash,identifier", [
    (201, "BUILDING_MONUMENT"), (102, "DISTRICT_CAMPUS"),
    (303, "UNIT_WARRIOR"), (401, "PROJECT_ENHANCE_DISTRICT_CAMPUS"),
])
def test_current_production_is_resolved_using_public_definitions(engine, hash, identifier):
    lua, read = engine
    lua.globals().controls.hash = hash
    result = read()
    assert result.production == identifier
    assert result.production_turns == 8


def test_empty_production_and_no_majority_are_explicit_none(engine):
    lua, read = engine
    lua.globals().controls.hash = 0
    lua.globals().controls.majority = -1
    result = read()
    assert result.production == "NONE"
    assert result.production_turns == 0
    assert result.religion == "NONE"


def test_unavailable_turn_estimate_does_not_invent_a_completion_time(engine):
    lua, read = engine
    lua.globals().controls.turns = -1
    result = read()
    assert result.production == "UNIT_WARRIOR"
    assert result.production_turns is None


@pytest.mark.parametrize("hash", [9999, 203])
def test_unknown_or_internal_production_is_omitted(engine, hash):
    lua, read = engine
    lua.globals().controls.hash = hash
    result = read()
    assert result.production is None
    assert result.production_turns is None


def test_internal_buildings_are_not_queried_or_reported(engine):
    lua, read = engine
    read()
    assert lua.globals().reads.buildings == 2


def test_absent_buildings_produce_empty_array(engine):
    lua, read = engine
    lua.execute("buildings.HasBuilding=function() return false end")
    assert len(read().buildings) == 0


def test_failed_collection_does_not_return_partial_results(engine):
    lua, read = engine
    lua.execute("buildings.HasBuilding=function(self,index) if index==2 then forbidden() end return true end")
    result = read()
    assert result.buildings is None
    assert result.districts is not None


def test_definition_scan_is_bounded(engine):
    lua, read = engine
    lua.execute('''
        local rows={}
        for i=1,4097 do rows[i]={BuildingType="BUILDING_TEST_"..i,Index=i,Hash=10000+i} end
        GameInfo.Buildings=definitions('BuildingType',rows)
        buildings.HasBuilding=function() return false end
    ''')
    assert read().buildings is None


def test_result_arrays_are_bounded_without_partial_list(engine):
    lua, read = engine
    lua.execute('''
        local rows={}
        for i=1,513 do rows[i]={BuildingType="BUILDING_TEST_"..i,Index=i,Hash=10000+i} end
        GameInfo.Buildings=definitions('BuildingType',rows)
        buildings.HasBuilding=function() return true end
    ''')
    assert read().buildings is None
