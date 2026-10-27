"""Only the current own-unit UI recommendation menu may cross the boundary."""
from copy import deepcopy

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.stock_recommendations import CATEGORY, FIELDS, recommendations
from civ6_fair_mcp.policy import PolicyError
from civ6_fair_mcp.stock_recommendations_policy import public_unit_recommendations

PARAMS = {"unit_id": 12}


@pytest.fixture
def engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
rawget=nil;unpack=nil;table.unpack=nil
settings={owner=0,unit_id=12,unit_type=1,charges=2,busy=false,city_owner=0,x=1,y=1}
reads={forbidden=0,builder=0,settler=0,geometry=0,city=0}
function forbidden() reads.forbidden=reads.forbidden+1;error("PRIVATE") end
function members(rows) local n=0;return function() n=n+1;if rows[n] then return n,rows[n] end end end
unit={GetOwner=function() return settings.owner end,
 GetID=function() assert(settings.owner==0);return settings.unit_id end,
 GetUnitType=function() assert(settings.owner==0);return settings.unit_type end,
 GetBuildCharges=function() assert(settings.owner==0);return settings.charges end,
 GetX=function() assert(settings.owner==0);return settings.x end,
 GetY=function() assert(settings.owner==0);return settings.y end,
 GetComponentID=function() assert(settings.owner==0);return component end}
component={}
foreign=setmetatable({GetOwner=function() return 3 end},{__index=forbidden})
localAdvisor=setmetatable({GetImprovementRecommendationsForBuilder=function(self,id)
 assert(self==localAdvisor and id==component and settings.city_owner==0)
 reads.builder=reads.builder+1;return records end},{__index=forbidden})
grandAdvisor=setmetatable({GetSettlementRecommendations=function(self,count)
 assert(self==grandAdvisor and count==5);reads.settler=reads.settler+1;return records end},{__index=forbidden})
city=setmetatable({GetOwner=function() return settings.city_owner end,
 GetCityAI=function() assert(settings.city_owner==0);return localAdvisor end},{__index=forbidden})
player=setmetatable({GetUnits=function() return {Members=function() return members({foreign,unit}) end} end,
 GetGrandStrategicAI=function() assert(settings.owner==0);return grandAdvisor end},{__index=forbidden})
UI={IsGameCoreBusy=function() return settings.busy end,SelectUnit=forbidden}
GameInfo={Units={[1]={FoundCity=false},[2]={FoundCity=true},[3]={FoundCity=false}},
 Improvements={[-99]={ImprovementType="IMPROVEMENT_MINE",Name="LOC_MINE"}}}
Locale={Lookup=function(key) assert(key=="LOC_MINE");return "矿山" end}
hidden={[19]=true};unrevealed={[18]=true}
vis={IsVisible=function(self,x,y) local id=y and y*8+x or x;return not hidden[id] end,
 IsRevealed=function(self,x,y) local id=y and y*8+x or x;return not unrevealed[id] end}
Map=setmetatable({GetGridSize=function() return 8.0,6.0 end,
 GetPlotIndex=function(x,y) assert(x==1 and y==1);return 9.0 end,
 GetPlotByIndex=function(index)
  assert(not hidden[index] and not unrevealed[index]);reads.geometry=reads.geometry+1
  return setmetatable({GetX=function() return (index%8)+0.0 end,
    GetY=function() return math.floor(index/8)+0.0 end},{__index=forbidden})
 end},{__index=forbidden})
Cities={GetPlotPurchaseCity=function(index) assert(index==9);reads.city=reads.city+1;return city end}
records={
 [0]={ImprovementLocation=10.0,ImprovementHash=-99.0},
 [4]=setmetatable({ImprovementLocation=19.0},{__index=forbidden}),
 [9]=setmetatable({ImprovementLocation=18.0},{__index=forbidden})}
''')

    def run(params=None):
        params = PARAMS if params is None else params
        body = recommendations(validate(params, FIELDS))
        result = vm.execute("local me=0;local out={items={}};\n" + LUA_HELPERS
            + "\nlocal function run()\n" + body + "\nend\nrun();return out")
        raw = {"ok": True, "session": "recommendation_test", "player_id": 0,
               "turn": 127, "active_turn": True, "category": CATEGORY,
               "supported": result["supported"],
               "items": [dict(item) for item in result["items"].values()]}
        if result["unit_recommendations"] is not None:
            raw["unit_recommendations"] = dict(result["unit_recommendations"])
        public = public_unit_recommendations(raw, params)
        assert vm.globals().reads.forbidden == 0
        return raw, public
    return vm, run


def values(public):
    return {item["id"]: item["value"] for item in public["items"]}


def make_settler(vm):
    vm.execute('''settings.unit_type=2;settings.charges=0
records={[0]=setmetatable({SettlingLocation=10.0},{__index=forbidden}),
 [2]=setmetatable({SettlingLocation=19.0},{__index=forbidden})}
unit.GetX=forbidden;unit.GetY=forbidden;Cities.GetPlotPurchaseCity=forbidden
''')


def test_builder_uses_current_own_city_native_recommendation_and_static_name(engine):
    vm, run = engine
    raw, public = run()
    assert public["supported"] is True
    assert values(public) == {"recommendation:0:x": 2, "recommendation:0:y": 1,
        "recommendation:0:kind": "builder", "recommendation:0:improvement": "IMPROVEMENT_MINE"}
    assert public["items"][-1]["name"] == "矿山"
    assert vm.globals().reads.builder == vm.globals().reads.geometry == 1
    assert vm.globals().reads.settler == 0
    assert all("action" not in item for item in public["items"])
    assert raw["unit_recommendations"]["unit_id"] == 12


def test_settler_uses_exact_five_recommendations_not_other_ai_methods_or_reason_text(engine):
    vm, run = engine
    make_settler(vm)
    _, public = run()
    assert values(public) == {"recommendation:0:x": 2, "recommendation:0:y": 1,
                              "recommendation:0:kind": "settler"}
    assert vm.globals().reads.settler == 1 and vm.globals().reads.city == 0
    assert vm.globals().reads.builder == 0


@pytest.mark.parametrize("change", [
    "settings.owner=1;unit.GetUnitType=forbidden;unit.GetBuildCharges=forbidden",
    "settings.unit_id=13;unit.GetUnitType=forbidden;unit.GetBuildCharges=forbidden",
])
def test_foreign_or_wrong_actor_never_reaches_advisor(engine, change):
    vm, run = engine
    vm.execute(change)
    _, public = run()
    assert public["supported"] is False and public["items"] == []
    assert vm.globals().reads.builder == vm.globals().reads.settler == 0


@pytest.mark.parametrize("change", [
    "settings.city_owner=2;city.GetCityAI=forbidden",
    "city=nil", "hidden[9]=true;Cities.GetPlotPurchaseCity=forbidden",
    "unrevealed[9]=true;Cities.GetPlotPurchaseCity=forbidden",
    "settings.charges=0;settings.unit_type=3",
])
def test_non_owned_city_hidden_origin_or_non_specialist_has_no_recommendations(engine, change):
    vm, run = engine
    vm.execute(change)
    _, public = run()
    assert public["supported"] is True and public["items"] == []
    assert vm.globals().reads.builder == vm.globals().reads.settler == 0


@pytest.mark.parametrize("change", [
    "UI.IsGameCoreBusy=nil", "settings.busy=true", "settings.busy=0",
    "unit.GetBuildCharges=nil", "settings.charges=-1", "settings.charges=1.5",
    "GameInfo.Units=nil", "unit.GetComponentID=nil", "city.GetCityAI=nil",
    "localAdvisor.GetImprovementRecommendationsForBuilder=nil",
    "localAdvisor.GetImprovementRecommendationsForBuilder=function() error('PRIVATE') end",
    "Map.GetPlotIndex=nil", "Map.GetPlotByIndex=nil", "vis.IsVisible=nil",
    "GameInfo.Improvements[-99]=nil", "records=false",
    "records={{ImprovementLocation=-1}}", "records={{ImprovementLocation=48}}",
    "records={{ImprovementLocation=10,ImprovementHash='private'}}",
])
def test_missing_throwing_or_invalid_native_inputs_fail_closed_without_partial_output(engine, change):
    vm, run = engine
    vm.execute("setmetatable(Map,nil);setmetatable(city,nil);setmetatable(localAdvisor,nil);" + change)
    _, public = run()
    assert public["supported"] is False and public["items"] == []


@pytest.mark.parametrize("change", [
    "settings.owner=2", "settings.unit_id=13", "settings.unit_type=3",
    "settings.charges=0", "settings.x=2", "settings.city_owner=2", "settings.busy=true",
    "hidden[10]=true",
])
def test_actor_city_or_visibility_changes_during_collection_discard_snapshot(engine, change):
    vm, run = engine
    vm.execute("local old=Map.GetPlotByIndex;Map.GetPlotByIndex=function(index) local p=old(index);"
               + change + ";return p end")
    _, public = run()
    assert public["supported"] is False and public["items"] == []


def test_native_duplicates_are_deduplicated_and_no_recommendation_score_is_read(engine):
    vm, run = engine
    vm.execute("records={[0]=setmetatable({ImprovementLocation=10,ImprovementHash=-99},{__index=forbidden}),[2]={ImprovementLocation=10,ImprovementHash=-99}}")
    _, public = run()
    assert len(public["items"]) == 4


def test_missing_optional_localization_retains_static_identifier(engine):
    vm, run = engine
    vm.execute("Locale=nil")
    _, public = run()
    assert public["items"][-1] == {"id": "recommendation:0:improvement", "value": "IMPROVEMENT_MINE"}


def test_settler_over_limit_or_missing_api_is_unknown_not_partial(engine):
    vm, run = engine
    make_settler(vm)
    vm.execute("records={};for i=1,6 do records[i]={SettlingLocation=10} end")
    assert run()[1]["supported"] is False
    vm.execute("setmetatable(grandAdvisor,nil);grandAdvisor.GetSettlementRecommendations=nil")
    assert run()[1]["supported"] is False


@pytest.mark.parametrize("field,value", [("owner_id", 1), ("owner_id", False), ("unit_id", 13),
                                        ("unit_id", 12.0), ("source", "private_ai"), ("kind", "raw")])
def test_python_checks_actor_and_source_before_touching_records(engine, field, value):
    _, run = engine
    raw, _ = run()
    raw["unit_recommendations"][field] = value
    raw["items"] = "PRIVATE_MALFORMED"
    assert public_unit_recommendations(raw, PARAMS)["items"] == []


@pytest.mark.parametrize("field", ["visible", "revealed", "recommended"])
def test_python_drops_unproven_site_before_validating_its_contents(engine, field):
    _, run = engine
    raw, _ = run()
    raw["items"] = [{field: False, "x": "PRIVATE"}]
    assert public_unit_recommendations(raw, PARAMS)["items"] == []


def test_python_only_emits_allowed_coordinates_kind_and_static_improvement(engine):
    _, run = engine
    raw, expected = run()
    extra = deepcopy(raw)
    extra["items"][0].update(score=12345, population=99, resource="RESOURCE_URANIUM",
                            description="PRIVATE", action={"type": "cheat"})
    assert public_unit_recommendations(extra, PARAMS) == expected
    assert public_unit_recommendations(extra, {"unit_id": 99})["items"] == []


@pytest.mark.parametrize("field,value", [("x", True), ("y", 4096), ("x", -1),
                                       ("improvement", "RESOURCE_URANIUM"), ("name", "bad\x00")])
def test_python_rejects_malformed_public_fields(engine, field, value):
    _, run = engine
    raw, _ = run()
    raw["items"][0][field] = value
    with pytest.raises(PolicyError):
        public_unit_recommendations(raw, PARAMS)
