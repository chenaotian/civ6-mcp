"""Execute the menu projection with poisoned non-menu getters, without a game.

TRADE_FIXTURE may also be installed over test_extension_units.ENGINE. It only
replaces the trade-related APIs; change `trade.candidates`, `trade.can`, or the
`trade_manager` methods after installing it to exercise another menu state.
"""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.trade_menus import (
    trade_body, trade_destinations, trade_options,
)


TRADE_FIXTURE = r'''
trade={owner=0,moves=2,activity=0,tactical=true,can=true,origin=true,hash=901,
    own_reads=0,name_reads=0,yield_reads=0,can_calls=0,path_calls=0,requests={},
    origin_multiplier=1.5,destination_multiplier=2,can_order={}}
function trade_forbidden() error("NON_MENU_SECRET") end
function trade_members(values)
    local i=0; return function() i=i+1; if values[i] then return i,values[i] end end
end
function trade_own(value)
    assert(trade.owner==0,"foreign actor fields"); trade.own_reads=trade.own_reads+1; return value
end
unit=unit or {GetOwner=function() return trade.owner end,
    GetID=function() return trade_own(10) end,GetX=function() return trade_own(2) end,
    GetY=function() return trade_own(2) end,GetUnitType=function() return trade_own(1) end,
    GetMovesRemaining=function() return trade_own(trade.moves) end}
origin_city={GetOwner=function() return 0 end,GetID=function() return 20 end,
    GetX=function() return 2 end,GetY=function() return 2 end,GetName=trade_forbidden}
function trade_city(owner,id,x,y,allowed,path,name)
    local c={owner=owner,id=id,x=x,y=y,allowed=allowed,path=path,name=name or ("Menu city "..id)}
    c.GetOwner=function(self) return self.owner end
    c.GetID=function(self) return self.id end
    c.GetX=function(self) return self.x end
    c.GetY=function(self) return self.y end
    c.GetName=function(self)
        assert(self.allowed and self.gate_passed and self.path_passed,"name before both gates")
        trade.name_reads=trade.name_reads+1; return self.name
    end
    return setmetatable(c,{__index=function(_,key)
        if key=="gate_passed" or key=="path_passed" then return nil end
        return trade_forbidden
    end})
end
trade.candidates={trade_city(1,21,3,2,true,true,"Offered fog city")}
trade.own_candidates={origin_city}
player=player or {}
player.GetID=function() return 0 end
player.GetCities=function() return {Members=function() return trade_members(trade.own_candidates) end} end
player.GetUnits=function() return {Members=function() return trade_members({unit}) end} end
player.GetTrade=function() return {GetInternationalYieldModifier=function(_,index)
    assert(index>=0 and index<=5); return trade.origin_multiplier end} end
foreign_player={GetID=function() return 1 end,
    GetCities=function() return {Members=function() return trade_members(trade.candidates) end} end,
    GetTrade=function() return {GetInternationalYieldModifier=function(_,index)
        assert(index>=0 and index<=5); return trade.destination_multiplier end} end}
Players=Players or {}; Players[0]=player; Players[1]=foreign_player
Game=Game or {}
Game.GetPlayers=function() return {foreign_player,player} end
Game.IsAllowTacticalCommands=function() return trade.tactical end
ActivityTypes={ACTIVITY_AWAKE=0,ACTIVITY_SLEEP=1}
GameInfo=GameInfo or {}
GameInfo.Units=GameInfo.Units or {}; GameInfo.Units[1]={MakeTradeRoute=true}
GameInfo.UnitOperations=GameInfo.UnitOperations or {}
GameInfo.UnitOperations.UNITOPERATION_MAKE_TRADE_ROUTE={Hash=901,VisibleInUI=true}
GameInfo.Yields={}
for i,name in ipairs({"YIELD_FOOD","YIELD_PRODUCTION","YIELD_GOLD","YIELD_SCIENCE","YIELD_CULTURE","YIELD_FAITH"}) do
    GameInfo.Yields[name]={Index=i-1}
end
Locale={Lookup=function(value) return value end}
UnitOperationTypes=UnitOperationTypes or {}
UnitOperationTypes.PARAM_X0="x0"; UnitOperationTypes.PARAM_Y0="y0"
UnitOperationTypes.PARAM_X1="x1"; UnitOperationTypes.PARAM_Y1="y1"
UnitOperationTypes.MAKE_TRADE_ROUTE=901
UnitManager=UnitManager or {}
UnitManager.GetActivityType=function(u) assert(u==unit); return trade.activity end
local previous_can=UnitManager.CanStartOperation
UnitManager.CanStartOperation=function(u,hash,plot,params,want_results)
    if hash~=901 and previous_can then return previous_can(u,hash,plot,params,want_results) end
    assert(u==unit and hash==901 and plot==nil)
    assert(params.x1==2 and params.y1==2 and want_results~=true)
    trade.can_calls=trade.can_calls+1
    table.insert(trade.can_order,params.x0)
    for _,list in ipairs({trade.own_candidates,trade.candidates}) do
        for _,c in ipairs(list) do
            if c:GetX()==params.x0 and c:GetY()==params.y0 then
                local allowed=c~=origin_city and c.allowed==true and trade.can
                if c~=origin_city then c.gate_passed=allowed end
                return allowed
            end
        end
    end
    return false
end
local previous_request=UnitManager.RequestOperation
UnitManager.RequestOperation=function(u,hash,params)
    table.insert(trade.requests,{unit=u,hash=hash,params=params})
    if previous_request then previous_request(u,hash,params) end
end
Cities=Cities or {}
Cities.GetCityInPlot=function(x,y)
    assert(x==2 and y==2); if trade.origin then return origin_city end
end
Cities.GetPlotPurchaseCity=trade_forbidden
Map={GetPlot=trade_forbidden,GetGridSize=trade_forbidden,GetPlotByIndex=trade_forbidden}
vis={IsVisible=trade_forbidden,IsRevealed=trade_forbidden}
trade_manager={}
Game.GetTradeManager=function() return trade_manager end
function trade_entry(owner,id)
    for _,list in ipairs({trade.own_candidates,trade.candidates}) do
        for _,c in ipairs(list) do if c:GetOwner()==owner and c:GetID()==id then return c end end
    end
    error("not a candidate")
end
trade_manager.GetTradeRoutePath=function(_,origin_owner,origin_id,owner,id)
    assert(origin_owner==0 and origin_id==20)
    local c=trade_entry(owner,id)
    assert(c.gate_passed,"path before qualification")
    trade.path_calls=trade.path_calls+1
    if c.path=="nil" then return nil end
    c.path_passed=c.path==true
    if c.path_passed then return {"SECRET_PATH_COORDINATES"} else return {} end
end
trade.yield_arrays={
    Origin={FromPotentialRoute={2,0,-4,1,0,2},FromPath={1,0,1,2,0,0},FromModifiers={3,0,1,3,0,0}},
    Destination={FromPotentialRoute={1,2,3,4,5,6},FromPath={0,0,0,0,0,0},FromModifiers={0,0,0,0,0,0}},
}
for _,side in ipairs({"Origin","Destination"}) do
    for _,suffix in ipairs({"FromPotentialRoute","FromPath","FromModifiers"}) do
        trade_manager["Calculate"..side.."Yields"..suffix]=function(_,origin_owner,origin_id,owner,id)
            assert(origin_owner==0 and origin_id==20)
            local c=trade_entry(owner,id)
            assert(c.gate_passed and c.path_passed,"yield before both gates")
            trade.yield_reads=trade.yield_reads+1
            return trade.yield_arrays[side][suffix]
        end
    end
end
'''


@pytest.fixture
def menu_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute(TRADE_FIXTURE)

    def run(kind="options", **values):
        build = {"options": trade_options, "destinations": trade_destinations, "action": trade_body}[kind]
        args = {"unit_id": 10, "x": 3, "y": 2, "offset": 0, **values}
        return vm.execute('''
            local out={items={},supported=true,accepted=false}
            local me,player,unit=0,Players[0],unit
            local function add_item(item) table.insert(out.items,item) end
            local function tactical() return Game.IsAllowTacticalCommands(me)==true end
            local function operation(name)
                local row=GameInfo.UnitOperations["UNITOPERATION_"..name]
                return row and row.VisibleInUI==true and row.Hash or nil
            end
            local function can_operation(u,hash,params)
                return UnitManager.CanStartOperation(u,hash,nil,params,false)==true
            end
            local function attempt(fn,...)
                local ok=pcall(fn,...); out.accepted=ok
            end
            local function execute()
        ''' + build(args) + '\nend\nexecute()\nreturn out')

    return vm, run


def records(result):
    return [dict(result["items"][i].items()) for i in range(1, len(result["items"]) + 1)]


def test_fog_menu_uses_only_both_stock_gates_and_minimal_authorized_fields(menu_engine):
    vm, run = menu_engine
    result = run()
    items = records(result)
    assert result["supported"] is True and len(items) == 13
    assert items[0]["name"] == "Offered fog city"
    assert dict(items[0]["action"].items()) == {"type": "trade_route", "unit_id": 10, "x": 3, "y": 2}
    allowed = {"id", "name", "description", "value", "action", "scope", "menu_owner_id", "menu_source", "menu_offered", "menu_unit_id"}
    for item in items:
        assert set(item) <= allowed
        assert {k: item[k] for k in ("scope", "menu_owner_id", "menu_source", "menu_offered", "menu_unit_id")} == {
            "scope": "menu", "menu_owner_id": 0, "menu_source": "trade", "menu_offered": True, "menu_unit_id": 10,
        }
    assert vm.globals().trade.name_reads == 1
    assert vm.globals().trade.path_calls == 1
    assert len(vm.globals().trade.requests) == 0


@pytest.mark.parametrize("change", ["trade.can=false", "trade.candidates[1].allowed=false", "trade.candidates[1].path=false", 'trade.candidates[1].path="nil"'])
def test_non_menu_city_never_exposes_names_yields_or_actions(menu_engine, change):
    vm, run = menu_engine
    vm.execute(change)
    assert records(run()) == []
    assert run("action")["accepted"] is False
    assert vm.globals().trade.name_reads == 0
    assert vm.globals().trade.yield_reads == 0
    assert len(vm.globals().trade.requests) == 0
    if "can=false" in change or "allowed=false" in change:
        assert vm.globals().trade.path_calls == 0


def test_origin_and_destination_benefits_use_their_own_international_multiplier(menu_engine):
    _, run = menu_engine
    values = {item["id"]: item.get("value") for item in records(run())}
    assert values["origin:YIELD_FOOD"] == 9  # (2+1+3)*1.5
    assert values["origin:YIELD_PRODUCTION"] == 0
    assert values["origin:YIELD_GOLD"] == -2  # negative does not multiply
    assert values["destination:YIELD_FOOD"] == 2
    assert values["destination:YIELD_FAITH"] == 12


def test_domestic_benefits_do_not_read_international_modifiers(menu_engine):
    vm, run = menu_engine
    vm.execute('''
        trade.candidates={}
        table.insert(trade.own_candidates,trade_city(0,22,3,2,true,true,"Own destination"))
        player.GetTrade=trade_forbidden; foreign_player.GetTrade=trade_forbidden
    ''')
    values = {item["id"]: item.get("value") for item in records(run())}
    assert values["origin:YIELD_FOOD"] == 6
    assert values["destination:YIELD_FOOD"] == 1


def test_action_uses_city_on_tile_and_rebuilds_both_menu_gates(menu_engine):
    vm, run = menu_engine
    assert run()["supported"] is True
    vm.execute("trade.candidates[1].path=false")
    assert run("action")["accepted"] is False
    vm.execute("trade.candidates[1].path=true")
    assert run("action")["accepted"] is True
    call = vm.globals().trade.requests[1]
    assert call["hash"] == 901
    assert dict(call["params"].items()) == {"x0": 3, "y0": 2, "x1": 2, "y1": 2}
    assert vm.globals().trade.name_reads == 1  # submissions never read labels


def test_action_rechecks_native_qualification_immediately_before_request(menu_engine):
    vm, run = menu_engine
    vm.execute('''
        local previous=UnitManager.CanStartOperation
        local destination_checks=0
        UnitManager.CanStartOperation=function(u,hash,plot,params,results)
            local allowed=previous(u,hash,plot,params,results)
            if params.x0==3 then destination_checks=destination_checks+1 end
            return allowed and destination_checks<2
        end
    ''')
    assert run("action")["accepted"] is False
    assert len(vm.globals().trade.requests) == 0


@pytest.mark.parametrize("change", [
    "trade.moves=0", "trade.activity=1", "trade.origin=false", "GameInfo.Units[1].MakeTradeRoute=false",
    "origin_city.GetOwner=function() return 1 end",
])
def test_actor_state_must_allow_opening_stock_chooser(menu_engine, change):
    vm, run = menu_engine
    vm.execute(change)
    assert records(run()) == []
    assert run("action")["accepted"] is False
    assert vm.globals().trade.can_calls == 0
    assert vm.globals().trade.name_reads == 0


def test_foreign_actor_rejected_before_any_field(menu_engine):
    vm, run = menu_engine
    vm.execute("trade.owner=1")
    assert records(run()) == []
    assert run("action")["accepted"] is False
    assert vm.globals().trade.own_reads == 0


def test_action_requires_tactical_permission(menu_engine):
    vm, run = menu_engine
    vm.execute("trade.tactical=false")
    assert run("action")["accepted"] is False
    assert vm.globals().trade.can_calls == 0


@pytest.mark.parametrize("change", [
    "UnitManager.GetActivityType=nil", "UnitManager.CanStartOperation=nil", "Cities.GetCityInPlot=nil",
    "Game.GetPlayers=nil", "Game.GetTradeManager=nil", "trade_manager.GetTradeRoutePath=nil",
    "trade_manager.CalculateDestinationYieldsFromModifiers=nil", "trade_manager.CalculateOriginYieldsFromPath=nil",
    "GameInfo.Yields.YIELD_FAITH=nil", "foreign_player.GetTrade=nil", "player.GetCities=nil",
    "trade.yield_arrays.Destination.FromPath={}", "UnitOperationTypes.PARAM_X1=nil",
    "GameInfo.UnitOperations.UNITOPERATION_MAKE_TRADE_ROUTE=nil",
])
def test_missing_required_capability_is_explicit_and_never_returns_partial_results(menu_engine, change):
    vm, run = menu_engine
    vm.execute(change)
    result = run("destinations")
    assert result["supported"] is False
    assert records(result) == []


def test_pagination_counts_qualified_menu_entries_and_only_reads_page_names(menu_engine):
    vm, run = menu_engine
    vm.execute('''
        trade.candidates={}
        for i=1,70 do
            table.insert(trade.candidates,trade_city(1,1000+i,i+100,3,false,true,"REJECTED"))
            table.insert(trade.candidates,trade_city(1,2000+i,i+200,4,true,false,"NO_PATH"))
            table.insert(trade.candidates,trade_city(1,3000+i,i+300,5,true,true,"Allowed "..i))
        end
    ''')
    first = records(run("destinations"))
    choices = [i for i in first if "action" in i]
    assert len(choices) == 64 and len(first) == 64 * 13 + 1
    assert choices[0]["name"] == "Allowed 1" and choices[-1]["name"] == "Allowed 64"
    assert first[-1]["id"] == "next_offset" and first[-1]["value"] == 64
    assert vm.globals().trade.name_reads == 64
    second = records(run("destinations", offset=64))
    assert [i["name"] for i in second if "action" in i] == [f"Allowed {i}" for i in range(65, 71)]
    assert second[-1]["value"] == -1
    assert vm.globals().trade.name_reads == 70
    assert len(records(run("destinations", offset=4096))) == 1
    assert vm.globals().trade.name_reads == 70


def test_own_cities_are_first_and_own_player_from_game_list_is_not_duplicated(menu_engine):
    vm, run = menu_engine
    vm.execute('table.insert(trade.own_candidates,trade_city(0,22,4,2,true,true,"Own destination"))')
    choices = [i for i in records(run("destinations")) if "action" in i]
    assert [i["name"] for i in choices] == ["Own destination", "Offered fog city"]
    assert list(vm.globals().trade.can_order.values()) == [2, 4, 3]


def test_later_missing_yield_data_discards_whole_page(menu_engine):
    vm, run = menu_engine
    vm.execute('''
        table.insert(trade.candidates,trade_city(1,22,4,2,true,true,"Second"))
        local previous=trade_manager.CalculateDestinationYieldsFromModifiers
        trade_manager.CalculateDestinationYieldsFromModifiers=function(self,a,b,c,id)
            if id==22 then return {} end
            return previous(self,a,b,c,id)
        end
    ''')
    result = run("destinations")
    assert result["supported"] is False and records(result) == []


def test_native_integral_float_ids_and_coordinates_are_normalized(menu_engine):
    vm, run = menu_engine
    vm.execute('''
        unit.GetID=function() return 10.0 end
        trade.candidates[1].x=3.0; trade.candidates[1].y=2.0
        trade.candidates[1].id=21.0; trade.candidates[1].owner=1.0
    ''')
    item = records(run("destinations"))[0]
    assert item["id"] == "trade:3:2"
    assert type(item["menu_unit_id"]) is int
    assert type(item["action"]["x"]) is int
    assert type(item["action"]["unit_id"]) is int


@pytest.mark.parametrize("change", [
    "trade.yield_arrays.Origin.FromPath[1]=math.huge",
    "trade.yield_arrays.Destination.FromModifiers[6]=0/0",
    "trade.destination_multiplier=-math.huge",
])
def test_nonfinite_yields_fail_closed_without_partial_results(menu_engine, change):
    vm, run = menu_engine
    vm.execute(change)
    result = run("destinations")
    assert result["supported"] is False and records(result) == []


@pytest.mark.parametrize("field,value", [("x", "-1"), ("y", "4096"), ("id", "0.5"), ("owner", '"1"')])
def test_invalid_candidate_identifiers_fail_before_name_or_eligibility(menu_engine, field, value):
    vm, run = menu_engine
    vm.execute(f"trade.candidates[1].{field}={value}")
    result = run("destinations")
    assert result["supported"] is False and records(result) == []
    assert vm.globals().trade.name_reads == 0
    assert vm.globals().trade.path_calls == 0


@pytest.mark.parametrize("kind", ["players", "cities"])
def test_native_enumeration_has_bounded_fail_closed_limits(menu_engine, kind):
    vm, run = menu_engine
    if kind == "players":
        vm.execute('''Game.GetPlayers=function()
            local list={}; for i=1,65 do table.insert(list,foreign_player) end; return list end''')
    else:
        vm.execute('''trade.candidates={}; for i=1,4096 do
            table.insert(trade.candidates,trade_city(1,i,3,2,false,false)) end''')
    result = run("destinations")
    assert result["supported"] is False and records(result) == []
    assert vm.globals().trade.name_reads == 0
