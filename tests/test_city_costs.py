"""Exercise actual city quote signatures, eligibility and optional-data failures."""

import json

import pytest

from civ6_fair_mcp.inspection_policy import public_inspection
from test_extension_empire import engine  # noqa: F401 -- shared real Lua VM


PRICES = r'''
quote_reads={}
local function record_quote(name,...)
    quote_reads[#quote_reads+1]={name=name,args={...}}
end
for _,kind in ipairs({'Units','Buildings','Districts','Projects'}) do
    for row in GameInfo[kind]() do row.Cost=9999;row.PurchaseYield='YIELD_GOLD' end
end
queue.GetUnitCost=function(self,index) assert(self==queue and index==0);record_quote('unit',index);return 31.5 end
queue.GetUnitCorpsCost=function(self,index) assert(self==queue and index==0);record_quote('corps',index);return 55 end
queue.GetUnitArmyCost=function(self,index) assert(self==queue and index==0);record_quote('army',index);return 72 end
queue.GetUnitProgress=function(self,index) assert(self==queue and index==0);return 7.25 end
queue.GetBuildingCost=function(self,index) assert(self==queue and (index==0 or index==1));return 83+index end
queue.GetBuildingProgress=function(self,index) assert(self==queue and (index==0 or index==1));return 12+index end
queue.GetDistrictCost=function(self,index) assert(self==queue and index==0);return 123.5 end
queue.GetDistrictProgress=function(self,index) assert(self==queue and index==0);return 17.5 end
queue.GetProjectCost=function(self,index) assert(self==queue and index==0);return 48 end
queue.GetProjectProgress=function(self,index) assert(self==queue and index==0);return 0 end
queue.GetTurnsLeft=function(self,target,formation)
    assert(self==queue)
    record_quote('turns',target,formation)
    if target==113 then
        assert(formation==nil or formation==1 or formation==2)
        return 3+(formation or 0)
    elseif target==114 or target==115 then assert(formation==nil);return 6
    elseif target=='DISTRICT_CAMPUS' then assert(formation==nil);return 9
    elseif target=='PROJECT_REPAIR' then assert(formation==nil);return -1 end
    error('wrong production estimate target')
end
gold={
 GetPurchaseCost=function(self,yield,hash,...)
    assert(self==gold and (yield==2 or yield==5))
    local formation=select(1,...)
    if hash==113 then assert(select('#',...)==1 and (formation==0 or formation==1 or formation==2))
    else assert(select('#',...)==0 and (hash==114 or hash==115 or hash==116)) end
    record_quote('purchase',yield,hash,formation)
    return hash+yield*100+(formation or 0)*1000
 end,
 GetPlotPurchaseCost=function(self,index)
    assert(self==gold and index==2);record_quote('plot',index);return 37.5
 end,
 IsUnitFaithPurchaseEnabled=function(self,hash) assert(self==gold and hash==113);return true end,
 IsBuildingFaithPurchaseEnabled=function(self,hash) assert(self==gold and (hash==114 or hash==115));return true end
}
city.GetGold=function() return gold end
treasury={GetGoldBalance=function() return controls.money end,
 CanAfford=function(self,city_id,hash,...)
    assert(self==treasury and city_id==42 and hash>=113 and hash<=116)
    assert(select('#',...)==0 or (hash==113 and (select(1,...)==1 or select(1,...)==2)))
    return true
 end}
player.GetTreasury=function() return treasury end
religion.CanAfford=function(self,city_id,hash,...)
    assert(self==religion and city_id==42 and hash>=113 and hash<=116)
    assert(select('#',...)==0 or (hash==113 and (select(1,...)==1 or select(1,...)==2)))
    return true
end
local original_plot=plot
function plot(x,y)
    local value=original_plot(x,y)
    value.GetIndex=function() return x==2 and 2 or 9 end
    return value
end
'''


def options(run, category="city_production", **extra):
    result = run(category, {"city_id": 42, **extra}, True)
    assert result["supported"] is True
    return {r["id"]: r for r in result["items"].values()}


@pytest.mark.parametrize("item,cost,progress,turns", [
    ("UNIT_WARRIOR", 31.5, 7.25, 3),
    ("BUILDING_MONUMENT", 84, 13, 6),
    ("BUILDING_WONDER", 83, 12, 6),
    ("DISTRICT_CAMPUS", 123.5, 17.5, 9),
    ("PROJECT_REPAIR", 48, 0, None),
])
def test_production_uses_city_values_and_exact_index_hash_or_type_signatures(engine, item, cost, progress, turns):
    vm, run = engine
    vm.execute(PRICES)
    rows = options(run)
    prefix = item + ":build:"
    assert rows[prefix + "production_cost"]["value"] == cost
    assert rows[prefix + "production_progress"]["value"] == progress
    assert "生产力点" in rows[prefix + "production_cost"]["description"]
    if turns is None:
        assert prefix + "production_turns" not in rows
        assert rows[prefix + "production_indefinite"]["value"] is True
    else:
        assert rows[prefix + "production_turns"]["value"] == turns
        assert prefix + "production_indefinite" not in rows
    assert rows[item + ":build"]["value"] is (item in {"BUILDING_WONDER", "DISTRICT_CAMPUS"})


@pytest.mark.parametrize("yield_name,yield_index", [("GOLD", 2), ("FAITH", 5)])
@pytest.mark.parametrize("item,hash_value", [("UNIT_WARRIOR", 113), ("BUILDING_MONUMENT", 115), ("DISTRICT_CAMPUS", 116)])
def test_purchase_cost_uses_city_gold_for_both_currencies_without_static_cost_math(engine, yield_name, yield_index, item, hash_value):
    vm, run = engine
    vm.execute(PRICES)
    rows = options(run)
    prefix = f"{item}:buy:{yield_name}"
    assert rows[prefix + ":purchase_cost"]["value"] == hash_value + yield_index * 100
    assert rows[prefix + ":purchase_available"]["value"] is True
    assert ("金币" if yield_name == "GOLD" else "信仰值") in rows[prefix + ":purchase_cost"]["description"]
    # Purchase tooltips expose production cost/progress, not invented zero turns.
    assert prefix + ":production_cost" in rows
    assert prefix + ":production_turns" not in rows


FORMATIONS = r'''
CityOperationResults={CAN_TRAIN_CORPS='corps',CAN_TRAIN_ARMY='army'}
queue.CanProduce=function(self,item,exclusion,results)
    if type(item)=='table' and results then return true,{corps=true,army=true} end
    return true
end
CityManager.CanStartCommand=function(c,op,exclusion,p,results)
    if exclusion then return true end
    if p.unit and results then return true,{corps=true,army=true} end
    return true
end
'''


@pytest.mark.parametrize("formation,number,cost", [("CORPS", 1, 55), ("ARMY", 2, 72)])
def test_corps_army_cost_progress_turns_and_currency_quotes_are_distinct(engine, formation, number, cost):
    vm, run = engine
    vm.execute(PRICES + FORMATIONS)
    rows = options(run)
    prefix = f"UNIT_WARRIOR:build:{formation}"
    assert rows[prefix + ":production_cost"]["value"] == cost
    assert rows[prefix + ":production_progress"]["value"] == 7.25
    assert rows[prefix + ":production_turns"]["value"] == 3 + number
    for name, index in [("GOLD", 2), ("FAITH", 5)]:
        prefix = f"UNIT_WARRIOR:buy:{name}:{formation}"
        assert rows[prefix + ":purchase_cost"]["value"] == 113 + 100 * index + 1000 * number
        assert rows[prefix]["action"]["formation"] == formation


def test_disabled_public_purchase_quotes_have_no_action_and_do_not_authorize_purchase(engine):
    vm, run = engine
    vm.execute(PRICES + FORMATIONS + r'''
CityManager.CanStartCommand=function(c,op,exclusion,p,results)
    if exclusion then return true end
    if p.unit and results then return false,{corps=true,army=true} end
    return false
end
''')
    rows = options(run)
    for prefix in ["UNIT_WARRIOR:buy:GOLD", "UNIT_WARRIOR:buy:GOLD:CORPS", "BUILDING_MONUMENT:buy:FAITH", "DISTRICT_CAMPUS:buy:FAITH"]:
        assert rows[prefix]["action"] is None
        assert rows[prefix + ":purchase_cost"]["value"] > 0
        assert rows[prefix + ":purchase_available"]["value"] is False
        assert "仅提供" in rows[prefix]["description"]
    assert rows["DISTRICT_CAMPUS:buy:FAITH"]["value"] is True  # placement, not availability
    assert not run("city_purchase", {"city_id": 42, "item": "UNIT_WARRIOR", "yield": "GOLD", "formation": "CORPS"})["accepted"]
    assert len(vm.globals().calls) == 0


def test_preview_obeys_purchase_yield_and_faith_unlock_menu_gate(engine):
    vm, run = engine
    vm.execute(PRICES + r'''
gold.IsUnitFaithPurchaseEnabled=function() return false end
gold.IsBuildingFaithPurchaseEnabled=function() return false end
CityManager.CanStartCommand=function(c,op,exclusion,p,results) return exclusion==true end
''')
    rows = options(run)
    assert "UNIT_WARRIOR:buy:GOLD:purchase_cost" in rows
    assert not any(k.startswith("UNIT_WARRIOR:buy:FAITH") or k.startswith("BUILDING_MONUMENT:buy:FAITH") for k in rows)


@pytest.mark.parametrize("item,kind", [("UNIT_WARRIOR", "Units"), ("BUILDING_MONUMENT", "Buildings")])
@pytest.mark.parametrize("yield_name", ["GOLD", "FAITH"])
def test_permissive_engine_cannot_bypass_original_purchase_menu_gate(engine, item, kind, yield_name):
    vm, run = engine
    vm.execute(PRICES + f'''
GameInfo.{kind}.{item}.PurchaseYield='YIELD_NOT_PURCHASEABLE'
gold.IsUnitFaithPurchaseEnabled=function() return false end
gold.IsBuildingFaithPurchaseEnabled=function() return false end
''')
    # The command checker and currency CanAfford still return true. The stock
    # outer menu gate must nevertheless prevent both quote and action.
    rows = options(run)
    assert not any(k.startswith(item + ":buy:" + yield_name) for k in rows)
    assert not run("city_purchase", {"city_id": 42, "item": item, "yield": yield_name, "formation": "STANDARD"})["accepted"]
    assert len(vm.globals().calls) == 0


def test_placement_purchase_obeys_building_menu_gate_but_districts_need_no_purchase_yield(engine):
    vm, run = engine
    vm.execute(PRICES + '''
GameInfo.Buildings.BUILDING_WONDER.PurchaseYield=nil
gold.IsBuildingFaithPurchaseEnabled=function() return false end
GameInfo.Districts.DISTRICT_CAMPUS.PurchaseYield=nil
''')
    rows = options(run, "city_placement", item="BUILDING_WONDER")
    assert "build:2:2" in rows and not any(k.startswith("buy:") for k in rows)
    assert not run("city_purchase_at", {"city_id": 42, "item": "BUILDING_WONDER", "yield": "GOLD", "formation": "STANDARD", "x": 2, "y": 2})["accepted"]
    rows = options(run, "city_placement", item="DISTRICT_CAMPUS")
    assert rows["buy:GOLD:2:2"]["action"]["type"] == "city_purchase_at"


@pytest.mark.parametrize("method", ["nil", "function() return false end", "function() error('unavailable') end"])
def test_gold_affordability_is_independent_of_command_legality_and_faith(engine, method):
    vm, run = engine
    vm.execute(PRICES + FORMATIONS + f"treasury.CanAfford={method}")
    rows = options(run)
    for suffix in ["", ":CORPS", ":ARMY"]:
        prefix = "UNIT_WARRIOR:buy:GOLD" + suffix
        assert rows[prefix]["action"] is None
        assert rows[prefix + ":purchase_available"]["value"] is False
        assert prefix + ":purchase_cost" in rows
    assert rows["UNIT_WARRIOR:buy:FAITH"]["action"]["type"] == "city_purchase"
    assert not run("city_purchase", {"city_id": 42, "item": "UNIT_WARRIOR", "yield": "GOLD", "formation": "ARMY"})["accepted"]
    assert len(vm.globals().calls) == 0


def test_faith_affordability_uses_religion_without_treasury_fallback(engine):
    vm, run = engine
    vm.execute(PRICES + "religion.CanAfford=function() return false end")
    rows = options(run)
    assert rows["BUILDING_MONUMENT:buy:FAITH"]["action"] is None
    assert rows["BUILDING_MONUMENT:buy:GOLD"]["action"]["type"] == "city_purchase"
    assert not run("city_purchase", {"city_id": 42, "item": "BUILDING_MONUMENT", "yield": "FAITH", "formation": "STANDARD"})["accepted"]


def test_missing_treasury_getter_never_falls_back_to_religion_affordability(engine):
    vm, run = engine
    vm.execute(PRICES + "player.GetTreasury=nil")
    rows = options(run)
    assert rows["UNIT_WARRIOR:buy:GOLD"]["action"] is None
    assert rows["UNIT_WARRIOR:buy:GOLD:purchase_available"]["value"] is False
    assert rows["UNIT_WARRIOR:buy:FAITH"]["action"]["type"] == "city_purchase"
    assert not run("city_purchase", {"city_id": 42, "item": "UNIT_WARRIOR", "yield": "GOLD", "formation": "STANDARD"})["accepted"]


def test_unaffordable_district_has_menu_price_but_no_placement_purchase_action(engine):
    vm, run = engine
    vm.execute(PRICES + "treasury.CanAfford=function() return false end")
    rows = options(run, "city_placement", item="DISTRICT_CAMPUS")
    assert "build:2:2" in rows and "buy:FAITH:2:2" in rows
    assert "buy:GOLD:2:2" not in rows
    assert not run("city_purchase_at", {"city_id": 42, "item": "DISTRICT_CAMPUS", "yield": "GOLD", "formation": "STANDARD", "x": 2, "y": 2})["accepted"]


def test_excluded_future_items_never_read_quotes_even_if_current_constraints_pass(engine):
    vm, run = engine
    vm.execute(PRICES + r'''
queue.CanProduce=function(self,item,exclusion,results) return exclusion==false end
CityManager.CanStartCommand=function(c,op,exclusion,p,results) return exclusion==false end
''')
    assert options(run) == {}
    assert len(vm.globals().quote_reads) == 0


def test_repair_cost_comes_from_current_queue_without_subtracting_database_cost(engine):
    vm, run = engine
    vm.execute(PRICES + r'''
GameInfo.Buildings.BUILDING_MONUMENT.MustPurchase=true
controls.pillaged=true
queue.GetBuildingCost=function(self,index) return 19.75 end
queue.GetBuildingProgress=function(self,index) return 8.25 end
''')
    rows = options(run)
    assert rows["BUILDING_MONUMENT:build:production_cost"]["value"] == 19.75
    assert rows["BUILDING_MONUMENT:build:production_progress"]["value"] == 8.25
    assert rows["BUILDING_MONUMENT:build"]["action"]["type"] == "city_build"


@pytest.mark.parametrize("value", ["nil", "true", "'12'", "-2", "0/0", "math.huge", "1e12"])
def test_invalid_optional_values_are_omitted_without_breaking_valid_options(engine, value):
    vm, run = engine
    vm.execute(PRICES + f'''
queue.GetUnitCost=function() return {value} end
queue.GetUnitProgress=function() return {value} end
queue.GetTurnsLeft=function() return {value} end
gold.GetPurchaseCost=function() return {value} end
''')
    rows = options(run)
    assert rows["UNIT_WARRIOR:build"]["action"]["type"] == "city_build"
    assert "UNIT_WARRIOR:build:production_cost" not in rows
    assert "UNIT_WARRIOR:build:production_progress" not in rows
    assert "UNIT_WARRIOR:build:production_turns" not in rows
    assert "UNIT_WARRIOR:build:production_indefinite" not in rows
    assert "UNIT_WARRIOR:buy:GOLD:purchase_cost" not in rows


@pytest.mark.parametrize("failure", ["nil", "function() error('unavailable') end"])
def test_missing_or_throwing_optional_api_preserves_other_quote_fields(engine, failure):
    vm, run = engine
    vm.execute(PRICES + f"queue.GetUnitCost={failure};gold.GetPurchaseCost={failure}")
    rows = options(run)
    assert "UNIT_WARRIOR:build:production_cost" not in rows
    assert rows["UNIT_WARRIOR:build:production_progress"]["value"] == 7.25
    assert rows["UNIT_WARRIOR:build:production_turns"]["value"] == 3
    assert "UNIT_WARRIOR:buy:GOLD:purchase_cost" not in rows
    assert rows["UNIT_WARRIOR:buy:GOLD"]["action"]["type"] == "city_purchase"


def test_zero_cost_and_progress_are_real_values_and_fractional_turns_are_not_estimates(engine):
    vm, run = engine
    vm.execute(PRICES + '''
queue.GetUnitCost=function() return 0 end
queue.GetUnitProgress=function() return 0 end
queue.GetTurnsLeft=function() return 1.5 end
gold.GetPurchaseCost=function() return 0 end
''')
    rows = options(run)
    assert rows["UNIT_WARRIOR:build:production_cost"]["value"] == 0
    assert rows["UNIT_WARRIOR:build:production_progress"]["value"] == 0
    assert rows["UNIT_WARRIOR:buy:GOLD:purchase_cost"]["value"] == 0
    assert "UNIT_WARRIOR:build:production_turns" not in rows


@pytest.mark.parametrize("category,extra", [("city_production", {}), ("city_placement", {"item": "DISTRICT_CAMPUS"}), ("city_tiles", {})])
def test_foreign_city_cannot_trigger_price_reads(engine, category, extra):
    vm, run = engine
    vm.execute(PRICES + "controls.owner=1;city.GetGold=forbid;city.GetBuildQueue=forbid")
    result = run(category, {"city_id": 42, **extra}, True)
    assert not result["supported"] and len(result["items"]) == 0
    assert len(vm.globals().quote_reads) == 0


@pytest.mark.parametrize("item,cost", [("DISTRICT_CAMPUS", 123.5), ("BUILDING_WONDER", 83)])
def test_visible_placement_actions_include_actual_quotes_without_hidden_plot_reads(engine, item, cost):
    vm, run = engine
    vm.execute(PRICES)
    rows = options(run, "city_placement", item=item)
    assert rows["build:2:2:production_cost"]["value"] == cost
    assert rows["build:2:2:production_turns"]["value"] in (6, 9)
    assert rows["buy:GOLD:2:2:purchase_cost"]["value"] in (314, 316)
    assert not any(":9:2" in key for key in rows)
    assert vm.globals().controls.plot_reads == 1


def test_failed_placement_does_not_read_or_return_prices(engine):
    vm, run = engine
    vm.execute(PRICES + "controls.can=false")
    assert options(run, "city_placement", item="DISTRICT_CAMPUS") == {}
    assert len(vm.globals().quote_reads) == 0


def test_plot_prices_only_read_visible_menu_targets_and_disable_unavailable_purchase(engine):
    vm, run = engine
    vm.execute(PRICES + "controls.can=false")
    rows = options(run, "city_tiles")
    assert rows["city_purchase_plot:2:2"]["action"] is None
    assert rows["city_purchase_plot:2:2:purchase_cost"]["value"] == 37.5
    assert rows["city_purchase_plot:2:2:purchase_available"]["value"] is False
    assert not any(":9:2" in key for key in rows)
    assert len(vm.globals().quote_reads) == 1


def test_plot_purchase_rechecks_actual_price_against_balance_before_action(engine):
    vm, run = engine
    vm.execute(PRICES + "controls.money=37")
    rows = options(run, "city_tiles")
    assert rows["city_purchase_plot:2:2:purchase_cost"]["value"] == 37.5
    assert rows["city_purchase_plot:2:2"]["action"] is None
    assert not run("city_purchase_plot", {"city_id": 42, "x": 2, "y": 2})["accepted"]
    vm.globals().controls.money = 38
    rows = options(run, "city_tiles")
    assert rows["city_purchase_plot:2:2"]["action"]["type"] == "city_purchase_plot"
    assert run("city_purchase_plot", {"city_id": 42, "x": 2, "y": 2})["accepted"]
    assert len(vm.globals().calls) == 1


def test_quote_scalar_records_survive_public_projection_without_new_schema(engine):
    vm, run = engine
    vm.execute(PRICES)
    # Round-trip the Lua-produced scalar records through JSON; no new nested
    # metadata schema is required by the projection.
    rows = options(run)
    records = []
    for row in rows.values():
        records.append({k: v for k, v in row.items() if k != "action"})
    raw = {"ok": True, "session": "city_prices_session_45", "player_id": 0, "turn": 45, "active_turn": True,
           "category": "city_production", "supported": True, "items": records}
    projected = public_inspection(json.loads(json.dumps(raw)), "city_production")
    values = {r["id"]: r.get("value") for r in projected["items"]}
    assert values["UNIT_WARRIOR:build:production_cost"] == 31.5
    assert values["PROJECT_REPAIR:build:production_indefinite"] is True
    assert values["DISTRICT_CAMPUS:buy:FAITH:purchase_cost"] == 616
