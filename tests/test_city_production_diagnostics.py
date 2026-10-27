"""Normal-menu disabled production and own district condition regression tests."""
import json

import pytest

from civ6_fair_mcp.inspection_policy import public_inspection
from test_city_costs import PRICES
from test_extension_empire import engine  # noqa: F401


DIAGNOSTICS = PRICES + r'''
current_production=-1; blocked_hash=115; menu_visible=true
failure_values={'LOC_BUILDING_CONSTRUCT_DISTRICT_IS_OCCUPIED_BY_ENEMY'}
condition_calls=0; blocked_quote_reads=0
CityCommandResults.FAILURE_REASONS='failure_reasons'
queue.GetCurrentProductionTypeHash=function(self) assert(self==queue);return current_production end
queue.CanProduce=function(self,item,exclusion,results)
    assert(self==queue)
    local hash=type(item)=='table' and item.UnitType or item
    if hash==blocked_hash then
        if exclusion then return menu_visible end
        assert(results==true)
        condition_calls=condition_calls+1
        return false,{failure_reasons=failure_values}
    end
    return true
end
Locale={}
Locale.Lookup=function(value)
    assert(value~='SECRET_UNMET_PLAYER' and value~='LOC_REQUIRES_SECRET_RESOURCE|URANIUM')
    if value=='LOC_BUILDING_CONSTRUCT_DISTRICT_IS_OCCUPIED_BY_ENEMY' then return '所需区域被敌人占领。' end
    if value=='LOC_BUILDING_CONSTRUCT_DISTRICT_IS_PILLAGED' then return '所需区域受到伤害。' end
    if value=='LOC_DISTRICT_REPAIR_LOCATION_FLOODED' then return '洪灾区域，无法修复。' end
    return value
end
'''


def rows(run):
    result = run("city_production", {"city_id": 42}, True)
    assert result["supported"] is True
    return {row["id"]: row for row in result["items"].values()}


def test_occupied_normal_building_retains_cost_progress_and_reason_without_action(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS)
    result = rows(run)
    prefix = "BUILDING_MONUMENT:build"
    assert result[prefix]["action"] is None
    assert result[prefix]["value"] is False  # unchanged placement-required meaning
    assert result[prefix + ":production_available"]["value"] is False
    assert result[prefix + ":repair"]["value"] is False
    assert result[prefix + ":production_cost"]["value"] == 84
    assert result[prefix + ":production_progress"]["value"] == 13
    assert result[prefix + ":failure_reason:1"]["value"] == "所需区域被敌人占领。"
    assert result[prefix + ":failure_explanation_available"]["value"] is True
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("reason", [
    "LOC_BUILDING_CONSTRUCT_IS_OCCUPIED",
    "LOC_BUILDING_CONSTRUCT_DISTRICT_IS_OCCUPIED_BY_ENEMY",
    "LOC_BUILDING_CONSTRUCT_DISTRICT_IS_PILLAGED",
    "LOC_DISTRICT_REPAIR_LOCATION_FLOODED",
    "所需区域被敌人占领。",
])
def test_accepts_only_reviewed_keys_or_their_exact_localized_text(engine, reason):
    from civ6_fair_mcp.extensions.base import lua
    vm, run = engine
    vm.execute(DIAGNOSTICS + "\nfailure_values={" + lua(reason) + "}")
    result = rows(run)
    assert result["BUILDING_MONUMENT:build:failure_explanation_available"]["value"] is True
    assert "BUILDING_MONUMENT:build:failure_reason:1" in result


def test_unknown_dynamic_reasons_are_never_localized_or_returned(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + r'''
failure_values={'SECRET_UNMET_PLAYER','LOC_REQUIRES_SECRET_RESOURCE|URANIUM',
    'LOC_BUILDING_CONSTRUCT_DISTRICT_IS_OCCUPIED_BY_ENEMY|secret args',
    'LOC_DISTRICT_ZONE_NO_SUITABLE_LOCATION',42,{text='hidden'}}
''')
    result = rows(run)
    assert result["BUILDING_MONUMENT:build:failure_explanation_available"]["value"] is False
    assert not any(":failure_reason:" in key for key in result)
    assert not any("SECRET" in str(row["value"]) for row in result.values())


def test_matching_raw_and_localized_reason_is_not_repeated(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + "\nfailure_values={'LOC_BUILDING_CONSTRUCT_DISTRICT_IS_OCCUPIED_BY_ENEMY','所需区域被敌人占领。'}")
    result = rows(run)
    assert len([key for key in result if ":failure_reason:" in key]) == 1


@pytest.mark.parametrize("mutation", [
    "failure_values=nil",
    "failure_values={}",
    "CityCommandResults.FAILURE_REASONS=nil",
])
def test_missing_reasons_are_explicitly_unprovided_not_invented(engine, mutation):
    vm, run = engine
    vm.execute(DIAGNOSTICS + "\n" + mutation)
    result = rows(run)
    assert result["BUILDING_MONUMENT:build:production_available"]["value"] is False
    assert result["BUILDING_MONUMENT:build:failure_explanation_available"]["value"] is False


def test_outer_visibility_rejection_never_requests_condition_results_or_quotes(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + r'''
menu_visible=false
CityManager.CanStartCommand=function() return false end
local previous=queue.GetBuildingCost
queue.GetBuildingCost=function(self,index)
    if index==1 then error('hidden building quote') end
    return previous(self,index)
end
''')
    result = rows(run)
    assert not any(key.startswith("BUILDING_MONUMENT:") for key in result)
    assert vm.globals().condition_calls == 0


@pytest.mark.parametrize("mutation", [
    "current_production=115",
    "queue.GetCurrentProductionTypeHash=nil",
    "queue.GetCurrentProductionTypeHash=function() error('unavailable') end",
    "current_production=116;GameInfo.Buildings.BUILDING_MONUMENT.PrereqDistrict='DISTRICT_CAMPUS'",
    "current_production=116;GameInfo.DistrictReplaces={DISTRICT_CAMPUS={ReplacesDistrictType='DISTRICT_OTHER'}};GameInfo.Buildings.BUILDING_MONUMENT.PrereqDistrict='DISTRICT_OTHER'",
])
def test_disabled_buildings_respect_current_item_and_prerequisite_repair_menu_gates(engine, mutation):
    vm, run = engine
    vm.execute(DIAGNOSTICS + "\n" + mutation)
    assert "BUILDING_MONUMENT:build" not in rows(run)


@pytest.mark.parametrize("hash_value", [114, 116])
def test_new_wonder_or_unplaced_district_disabled_branch_is_not_expanded(engine, hash_value):
    vm, run = engine
    vm.execute(DIAGNOSTICS + f"\nblocked_hash={hash_value};controls.placed=false;controls.built=false")
    item = "BUILDING_WONDER" if hash_value == 114 else "DISTRICT_CAMPUS"
    assert item + ":build" not in rows(run)


def test_existing_district_repair_uses_menu_exception_and_fixed_flood_reason(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + r'''
blocked_hash=116;menu_visible=false;controls.built=true
failure_values={'洪灾区域，无法修复。'}
city.GetDistricts=function() return {
    HasDistrict=function(self,index) assert(index==0);return true end,
    IsPillaged=function(self,index) assert(index==0);return true end
} end
''')
    result = rows(run)
    prefix = "DISTRICT_CAMPUS:build"
    assert result[prefix]["action"] is None
    assert result[prefix]["value"] is False
    assert result[prefix + ":repair"]["value"] is True
    assert result[prefix + ":production_available"]["value"] is False
    assert result[prefix + ":failure_reason:1"]["value"] == "洪灾区域，无法修复。"
    assert result[prefix + ":production_progress"]["value"] == 17.5


def test_purchased_only_building_repair_retains_original_exception(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + "\nGameInfo.Buildings.BUILDING_MONUMENT.MustPurchase=true")
    assert "BUILDING_MONUMENT:build" not in rows(run)
    vm.globals().controls.pillaged = True
    result = rows(run)
    assert result["BUILDING_MONUMENT:build:repair"]["value"] is True
    assert result["BUILDING_MONUMENT:build"]["action"] is None


DISTRICTS = r'''
district_state_reads=0
own_district={GetType=function() return 0 end,GetX=function() return 2.0 end,GetY=function() return 2.0 end,
    GetYield=function() error('district yields not requested') end,
    GetAdjacencyYield=function() error('adjacency not requested') end}
fog_district={GetType=function() return 0 end,GetX=function() return 9 end,GetY=function() return 2 end}
own_districts={HasDistrict=function() return true end,
    Members=function() return ipairs({own_district,fog_district}) end,
    IsPillaged=function(self,kind,index)
        assert(self==own_districts and kind==0)
        if index~=nil then assert(index==2);district_state_reads=district_state_reads+1 end
        return true
    end,
    IsComplete=function(self,kind,index)
        assert(self==own_districts and kind==0 and index==2)
        district_state_reads=district_state_reads+1;return false
    end}
city.GetDistricts=function() return own_districts end
'''


def test_own_district_conditions_have_exact_plot_binding_and_no_fog_reads(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + DISTRICTS)
    result = rows(run)
    assert result["district:2"]["value"] == "DISTRICT_CAMPUS"
    assert result["district:2"]["x"] == 2 and result["district:2"]["y"] == 2
    assert result["district:2:x"]["value"] == 2 and result["district:2:y"]["value"] == 2
    assert result["district:2:complete"]["value"] is False
    assert result["district:2:pillaged"]["value"] is True
    assert not any(key.startswith("district:9") for key in result)
    assert vm.globals().district_state_reads == 2


@pytest.mark.parametrize("mutation", [
    "own_districts.IsComplete=nil;own_districts.IsPillaged=nil",
    "own_districts.IsComplete=function() return 1 end;own_districts.IsPillaged=function() return nil end",
    "own_districts.IsComplete=function() error('not available') end;own_districts.IsPillaged=function() error('not available') end",
])
def test_missing_condition_is_omitted_not_reported_as_false(engine, mutation):
    vm, run = engine
    vm.execute(DIAGNOSTICS + DISTRICTS + "\n" + mutation)
    result = rows(run)
    assert "district:2" in result
    assert "district:2:complete" not in result and "district:2:pillaged" not in result


def test_foreign_owned_or_fogged_district_plot_never_reads_condition(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + DISTRICTS + r'''
local previous=plot
function plot(x,y)
    local value=previous(x,y);value.GetOwner=function() return 1 end;return value
end
''')
    result = rows(run)
    assert not any(key.startswith("district:") for key in result)
    assert vm.globals().district_state_reads == 0


def test_new_public_items_pass_existing_projection_without_schema_changes(engine):
    vm, run = engine
    vm.execute(DIAGNOSTICS + DISTRICTS)
    result = rows(run)
    data = [{key: value for key, value in row.items() if key != "action"} for row in result.values()]
    raw = {"session": "city_diagnostic_test", "player_id": 0, "turn": 60,
           "active_turn": True, "category": "city_production", "supported": True, "items": data}
    public = public_inspection(json.loads(json.dumps(raw)), "city_production")
    values = {row["id"]: row for row in public["items"]}
    assert values["district:2:pillaged"]["value"] is True
    assert values["district:2:x"]["value"] == 2 and values["district:2:y"]["value"] == 2
    assert type(values["district:2:x"]["value"]) is int
    assert values["BUILDING_MONUMENT:build:production_available"]["value"] is False
