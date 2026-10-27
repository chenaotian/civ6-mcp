"""Luxury inventory mirrors the stock own-player row, including non-map goods."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions import build_inspection_query, registries
from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.resources import own_luxuries
from civ6_fair_mcp.inspection_policy import public_inspection


@pytest.fixture
def luxury_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
reads={forbidden=0,amount=0}
function secret() reads.forbidden=reads.forbidden+1;error("FORBIDDEN_DATA") end
toys=setmetatable({Index=3.0,ResourceClassType="RESOURCECLASS_LUXURY",ResourceType="RESOURCE_TOYS",Name="LOC_TOYS"},
 {__index=secret}) -- Frequency/Hash/plots are deliberately forbidden.
diamonds={Index=4,ResourceClassType="RESOURCECLASS_LUXURY",ResourceType="RESOURCE_DIAMONDS",Name="LOC_DIAMONDS"}
absent=setmetatable({Index=5,ResourceClassType="RESOURCECLASS_LUXURY"},{__index=secret})
strategic=setmetatable({ResourceClassType="RESOURCECLASS_STRATEGIC"},{__index=secret})
bonus=setmetatable({ResourceClassType="RESOURCECLASS_BONUS"},{__index=secret})
artifact=setmetatable({ResourceClassType="RESOURCECLASS_ARTIFACT"},{__index=secret})
definitions={toys,diamonds,absent,strategic,bonus,artifact}
amounts={[3]=1.0,[4]=2,[5]=0}
GameInfo={Resources=function()
 local i=0;return function() i=i+1;return definitions[i] end
end}
resources=setmetatable({GetResourceAmount=function(self,index)
 assert(self==resources and type(index)=="number" and amounts[index]~=nil)
 reads.amount=reads.amount+1;return amounts[index]
end},{__index=secret})
player=setmetatable({GetResources=function(self) assert(self==player);return resources end},{__index=secret})
Players=setmetatable({},{__index=secret});Map=setmetatable({},{__index=secret})
DealManager=setmetatable({},{__index=secret});GameConfiguration=setmetatable({},{__index=secret})
Locale={Lookup=function(key)
 if key=="LOC_TOYS" then return "玩具" end
 if key=="LOC_DIAMONDS" then return "钻石" end
 return secret()
end}
''')

    def run():
        result = vm.execute("local me=0;local out={items={}};\n" + LUA_HELPERS
            + "\nlocal function collect()\n" + own_luxuries({})
            + "\nend\ncollect()\nreturn out")
        raw = {"ok": True, "session": "own_luxuries_tests", "player_id": 0, "turn": 104,
            "active_turn": True, "category": "own_luxuries", "supported": result["supported"],
            "items": [dict(row) for row in result["items"].values()]}
        projected = public_inspection(raw, "own_luxuries")
        assert vm.globals().reads.forbidden == 0
        return projected, {row["id"]: row for row in projected["items"]}
    return vm, run


def test_inventory_includes_great_merchant_goods_without_map_or_trade_queries(luxury_engine):
    vm, run = luxury_engine
    result, rows = run()
    assert result["supported"] is True
    assert set(rows) == {"RESOURCE_TOYS", "RESOURCE_TOYS:amount", "RESOURCE_DIAMONDS", "RESOURCE_DIAMONDS:amount"}
    assert rows["RESOURCE_TOYS"]["name"] == "玩具"
    assert rows["RESOURCE_TOYS:amount"]["value"] == 1
    assert type(rows["RESOURCE_TOYS:amount"]["value"]) is int
    assert rows["RESOURCE_DIAMONDS:amount"]["value"] == 2
    assert "不是" in rows["RESOURCE_TOYS:amount"]["description"]
    assert all("action" not in row for row in rows.values())
    assert vm.globals().reads.amount == 3


def test_empty_holdings_are_supported_without_reading_resource_names(luxury_engine):
    vm, run = luxury_engine
    vm.execute("amounts[3]=0;amounts[4]=0;toys.Name=nil;toys.ResourceType=nil")
    result, rows = run()
    assert result["supported"] is True and rows == {}


@pytest.mark.parametrize("change", [
    "player.GetResources=nil", "player.GetResources=function() error('PRIVATE') end",
    "player.GetResources=function() return false end", "resources.GetResourceAmount=nil",
    "resources.GetResourceAmount=function() error('PRIVATE') end", "GameInfo.Resources=nil",
])
def test_missing_required_api_fails_closed(luxury_engine, change):
    vm, run = luxury_engine
    vm.execute("setmetatable(player,nil);setmetatable(resources,nil);" + change)
    result, rows = run()
    assert result["supported"] is False and rows == {}


@pytest.mark.parametrize("invalid", ["nil", "false", "'1'", "1.5", "0/0", "math.huge", "1e12"])
def test_unknown_later_quantity_discards_partial_inventory(luxury_engine, invalid):
    vm, run = luxury_engine
    vm.execute(f"local previous=resources.GetResourceAmount;resources.GetResourceAmount=function(self,id) if id==4 then return {invalid} end;return previous(self,id) end")
    result, rows = run()
    assert result["supported"] is False and rows == {}


def test_nonpositive_balance_is_omitted_like_stock_menu_not_a_query_failure(luxury_engine):
    vm, run = luxury_engine
    vm.execute("amounts[5]=-1")
    result, rows = run()
    assert result["supported"] is True
    assert rows["RESOURCE_TOYS:amount"]["value"] == 1
    assert len(rows) == 4


@pytest.mark.parametrize("change", [
    "diamonds.Index=3", "diamonds.Index=-1", "diamonds.Index=3.5", "diamonds.Index='4'",
    "diamonds.ResourceType='RESOURCE_TOYS'", "diamonds.ResourceType='RESOURCE_DIAMONDS\\n'",
    "GameInfo.Resources=function() return function() return {ResourceClassType='RESOURCECLASS_BONUS'} end end",
])
def test_invalid_or_unbounded_rule_rows_do_not_report_a_partial_inventory(luxury_engine, change):
    vm, run = luxury_engine
    vm.execute(change)
    result, rows = run()
    assert result["supported"] is False and rows == {}


@pytest.mark.parametrize("change", [
    "Locale=nil", "Locale.Lookup=nil", "Locale.Lookup=function() error('unavailable') end",
    "Locale.Lookup=function(key) return key end", "Locale.Lookup=function() return 'bad\\0text' end",
])
def test_missing_localized_name_keeps_holdings_with_identifier(luxury_engine, change):
    vm, run = luxury_engine
    vm.execute(change)
    _, rows = run()
    assert rows["RESOURCE_TOYS"]["name"] == "RESOURCE_TOYS"
    assert rows["RESOURCE_TOYS:amount"]["value"] == 1


def test_new_query_has_no_player_or_resource_selector():
    actions, queries = registries()
    assert "own_luxuries" in queries and "own_luxuries" not in actions
    assert queries["own_luxuries"].fields == {}
    for params in ({"player_id": 1}, {"resource": "RESOURCE_TOYS"}, {"getter": "GetResourceAmount"}):
        with pytest.raises(ValueError):
            build_inspection_query("own_luxuries_tests", "own_luxuries", params)
    LuaRuntime().compile(build_inspection_query("own_luxuries_tests", "own_luxuries", {}))
