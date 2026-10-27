"""Stock resource aggregates are owned and unlock-gated before any detail read."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions import build_inspection_query, registries
from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.resources import _FIELDS, own_resources
from civ6_fair_mcp.inspection_policy import public_inspection


@pytest.fixture
def resource_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
reads={secret=0,amount=0,gates=0}
function secret() reads.secret=reads.secret+1;error("SECRET_FOREIGN_OR_LOCKED") end
local gated={}
settings={rules="RULESET_EXPANSION_2",coal=false,visible=true}
amounts={amount=38,stockpile_cap=50,reserved=15,accumulation_per_turn=2,
    import_per_turn=1,bonus_per_turn=3,unit_demand_per_turn=5,power_demand_per_turn=4}
iron={Hash=101,ResourceClassType="RESOURCECLASS_STRATEGIC",ResourceType="RESOURCE_IRON",Name="LOC_IRON"}
coal=setmetatable({Hash=102,ResourceClassType="RESOURCECLASS_STRATEGIC"}, {__index=function(_,key)
    if not settings.coal then return secret() end
    if key=="ResourceType" then return "RESOURCE_COAL" end
    if key=="Name" then return "LOC_COAL" end
end})
luxury=setmetatable({ResourceClassType="RESOURCECLASS_LUXURY"},{__index=secret})
bonus=setmetatable({ResourceClassType="RESOURCECLASS_BONUS"},{__index=secret})
definitions={iron,coal,luxury,bonus}
GameInfo={Resources=function()
    local i=0;return function() i=i+1;return definitions[i] end
end}
resources={IsResourceVisible=function(self,hash)
    assert(self==resources)
    reads.gates=reads.gates+1
    assert(hash==101 or hash==102,"resource visibility uses Hash")
    local visible=hash==101 and settings.visible or hash==102 and settings.coal
    if visible then gated[hash==101 and "RESOURCE_IRON" or "RESOURCE_COAL"]=true end
    return visible
end}
function install(method,key)
    resources[method]=function(self,id)
        assert(self==resources and gated[id],"value read before unlock")
        reads.amount=reads.amount+1
        if id=="RESOURCE_COAL" then return 0 end
        return amounts[key]
    end
end
install("GetResourceAmount","amount")
install("GetResourceStockpileCap","stockpile_cap")
install("GetReservedResourceAmount","reserved")
install("GetResourceAccumulationPerTurn","accumulation_per_turn")
install("GetResourceImportPerTurn","import_per_turn")
install("GetBonusResourcePerTurn","bonus_per_turn")
install("GetUnitResourceDemandPerTurn","unit_demand_per_turn")
install("GetPowerResourceDemandPerTurn","power_demand_per_turn")
player=setmetatable({GetResources=function() return resources end},{__index=secret})
Players=setmetatable({[0]=player},{__index=secret})
Map=setmetatable({},{__index=secret})
Game=setmetatable({},{__index=secret})
GameConfiguration={GetValue=function(key) assert(key=="RULESET");return settings.rules end}
Locale={Lookup=function(key)
    if key=="LOC_IRON" then return "铁" end
    if key=="LOC_COAL" then assert(settings.coal);return "煤" end
    return secret()
end}
''')

    def run():
        result = vm.execute("local me=0;local out={items={}};\n" + LUA_HELPERS
            + "\nlocal function collect()\n" + own_resources({})
            + "\nend\ncollect()\nreturn out")
        raw = {"ok": True, "session": "resources_tests_own", "player_id": 0, "turn": 48,
            "active_turn": True, "category": "own_resources", "supported": result["supported"],
            "items": [dict(row) for row in result["items"].values()]}
        projected = public_inspection(raw, "own_resources")
        assert vm.globals().reads.secret == 0
        return projected, {row["id"]: row for row in projected["items"]}
    return vm, run


def test_own_unlocked_gs_balances_and_exact_top_panel_arithmetic(resource_engine):
    _, run = resource_engine
    result, rows = run()
    assert result["supported"] is True
    assert rows["RESOURCE_IRON"]["name"] == "铁"
    values = {key.split(":")[-1]: row["value"] for key, row in rows.items() if ":" in key}
    assert values == {
        "amount": 38, "stockpile_cap": 50, "reserved": 15, "stockpile_total": 50,
        "accumulation_per_turn": 2, "import_per_turn": 1, "bonus_per_turn": 3,
        "income_per_turn": 6, "unit_demand_per_turn": 5, "power_demand_per_turn": 4,
        "demand_per_turn": 9, "net_per_turn": -3,
    }
    assert all("action" not in row for row in rows.values())
    assert not any("COAL" in key for key in rows)


@pytest.mark.parametrize("change", ["table.unpack=nil", "table.unpack=nil;unpack=nil"])
def test_native_calls_do_not_depend_on_any_unpack_api(resource_engine, change):
    vm, run = resource_engine
    vm.execute(change + '''
player.GetResources=function(self,...)
    assert(self==player and select("#",...)==0)
    return resources
end
local previous=resources.GetResourceAmount
resources.GetResourceAmount=function(self,...)
    assert(select("#",...)==1)
    return previous(self,...)
end
''')
    result, rows = run()
    assert result["supported"] is True
    assert rows["RESOURCE_IRON:amount"]["value"] == 38
    assert rows["RESOURCE_IRON:net_per_turn"]["value"] == -3


def test_locked_resources_are_not_named_localized_or_counted(resource_engine):
    vm, run = resource_engine
    vm.execute("settings.visible=false;iron.ResourceType=nil;iron.Name=nil;setmetatable(iron,{__index=secret})")
    result, rows = run()
    assert result["supported"] is True and rows == {}
    assert vm.globals().reads.amount == 0


def test_unlock_exposes_known_zero_without_assuming_possession(resource_engine):
    vm, run = resource_engine
    assert "RESOURCE_COAL" not in run()[1]
    vm.execute("settings.coal=true")
    _, rows = run()
    assert rows["RESOURCE_COAL"]["name"] == "煤"
    assert rows["RESOURCE_COAL:amount"]["value"] == 0
    assert rows["RESOURCE_COAL:net_per_turn"]["value"] == 0


@pytest.mark.parametrize("change", [
    "player.GetResources=nil", "player.GetResources=function() return false end",
    "player.GetResources=function() error('missing') end", "resources.IsResourceVisible=nil",
    "resources.IsResourceVisible=function() error('SECRET_GATE_FAILURE') end",
    "resources.IsResourceVisible=function() return nil end",
    "resources.IsResourceVisible=function() return 1 end", "GameInfo.Resources=nil",
])
def test_required_capability_failure_is_closed(resource_engine, change):
    vm, run = resource_engine
    # Deliberately missing local APIs are not foreign-component reads.
    vm.execute("setmetatable(player,nil)")
    vm.execute(change)
    result, rows = run()
    assert result["supported"] is False and rows == {}
    assert vm.globals().reads.amount == 0


@pytest.mark.parametrize("rules", ["RULESET_STANDARD", "RULESET_EXPANSION_1", "RULESET_CUSTOM", None])
def test_non_gs_never_probes_gs_stockpile_or_rates(resource_engine, rules):
    vm, run = resource_engine
    vm.globals().settings.rules = rules
    for _, getter, _, _ in _FIELDS:
        vm.globals().resources[getter] = vm.globals().secret
    result, rows = run()
    assert result["supported"] is True
    assert set(rows) == {"RESOURCE_IRON", "RESOURCE_IRON:amount"}


@pytest.mark.parametrize("change", [
    "GameConfiguration=nil", "GameConfiguration.GetValue=nil",
    "GameConfiguration.GetValue=function() error('missing') end",
])
def test_unavailable_ruleset_preserves_amount_without_inventing_stockpile_semantics(resource_engine, change):
    vm, run = resource_engine
    vm.execute(change)
    _, rows = run()
    assert set(rows) == {"RESOURCE_IRON", "RESOURCE_IRON:amount"}


@pytest.mark.parametrize("change", [
    "resources.GetBonusResourcePerTurn=nil",
    "resources.GetBonusResourcePerTurn=function() error('SECRET_OPTIONAL_ERROR') end",
    "resources.GetBonusResourcePerTurn=function() return '3' end",
    "resources.GetBonusResourcePerTurn=function() return 0/0 end",
    "resources.GetBonusResourcePerTurn=function() return math.huge end",
])
def test_optional_missing_rate_omits_dependent_totals_only(resource_engine, change):
    vm, run = resource_engine
    vm.execute(change)
    result, rows = run()
    assert result["supported"] is True
    assert rows["RESOURCE_IRON:amount"]["value"] == 38
    for key in ("bonus_per_turn", "income_per_turn", "net_per_turn"):
        assert "RESOURCE_IRON:" + key not in rows
    assert rows["RESOURCE_IRON:demand_per_turn"]["value"] == 9


@pytest.mark.parametrize("value", ["nil", "false", "'0'", "-1", "0/0", "math.huge", "1e12"])
def test_invalid_stockpile_amount_is_omitted_not_guessed(resource_engine, value):
    vm, run = resource_engine
    vm.execute("resources.GetResourceAmount=function() return " + value + " end")
    _, rows = run()
    assert "RESOURCE_IRON:amount" not in rows and "RESOURCE_IRON:stockpile_total" not in rows
    assert rows["RESOURCE_IRON:income_per_turn"]["value"] == 6


def test_signed_rate_is_preserved_and_no_future_stockpile_is_predicted(resource_engine):
    vm, run = resource_engine
    vm.execute("amounts.bonus_per_turn=-10")
    _, rows = run()
    assert rows["RESOURCE_IRON:income_per_turn"]["value"] == -7
    assert rows["RESOURCE_IRON:net_per_turn"]["value"] == -16
    assert "下回合实际库存变化" in rows["RESOURCE_IRON:net_per_turn"]["description"]
    assert "RESOURCE_IRON:next_turn_amount" not in rows


@pytest.mark.parametrize("change", [
    "Locale=nil", "Locale.Lookup=function() error('missing') end",
    "Locale.Lookup=function(key) return key end",
    "Locale.Lookup=function() return 'bad\\0text' end",
])
def test_optional_localization_does_not_remove_public_values(resource_engine, change):
    vm, run = resource_engine
    vm.execute(change)
    _, rows = run()
    assert rows["RESOURCE_IRON"]["name"] == "RESOURCE_IRON"
    assert rows["RESOURCE_IRON:amount"]["value"] == 38


def test_visibility_failure_later_in_iteration_discards_partial_output(resource_engine):
    vm, run = resource_engine
    vm.execute('''
local previous=resources.IsResourceVisible
resources.IsResourceVisible=function(self,hash)
    if hash==102 then error("SECRET_HIDDEN_STATE") end
    return previous(self,hash)
end
''')
    result, rows = run()
    assert result["supported"] is False and rows == {}


def test_resource_definition_scan_is_bounded_and_does_not_output_counts(resource_engine):
    vm, run = resource_engine
    vm.execute('''GameInfo.Resources=function()
    return function() return {ResourceClassType="RESOURCECLASS_BONUS"} end
end''')
    result, rows = run()
    assert result["supported"] is False and rows == {}
    assert vm.globals().reads.amount == 0


def test_invalid_identifier_cannot_reach_amount_getter(resource_engine):
    vm, run = resource_engine
    vm.execute('iron.ResourceType="RESOURCE_IRON\\n"')
    result, rows = run()
    assert result["supported"] is True and rows == {}
    assert vm.globals().reads.amount == 0


def test_registration_has_no_actions_and_rejects_foreign_or_arbitrary_parameters():
    actions, queries = registries()
    assert "own_resources" in queries and "own_resources" not in actions
    assert queries["own_resources"].fields == {}
    for params in ({"player_id": 1}, {"resource": "RESOURCE_URANIUM"}, {"getter": "GetResourceAmount"}):
        with pytest.raises(ValueError):
            build_inspection_query("test_resource", "own_resources", params)
    assert "IsResourceVisible" in build_inspection_query("test_resource", "own_resources", {})


def test_projection_filters_foreign_claim_before_resource_text():
    raw = {"ok": True, "session": "resources_tests_own", "player_id": 0, "turn": 48,
        "active_turn": True, "category": "own_resources", "supported": True,
        "items": [{"scope": "self", "owner_id": 1, "id": None, "name": {"hidden": True}}]}
    assert public_inspection(raw, "own_resources")["items"] == []
