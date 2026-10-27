"""Execute real extension Lua: normal requests and hostile visibility fixtures."""
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.units import ACTIONS, QUERIES, COMMANDS, ORDERS, SPY_MISSIONS, TARGETS
from civ6_fair_mcp.lua_common import wrap


ENGINE = r'''
settings={visible=true,revealed=true,detected=true,owner=0,can=true,tactical=true,war=false,foreign_city=false,escape=-1,promotion=7,target_x=3,moves=2,combat=20,religious_strength=0,ranged_combat=0,bombard_combat=0}
reads={hidden=0,unit=0,plot=0,can=0,foreign=0}
calls={}
function forbidden() reads.hidden=reads.hidden+1; error("SECRET_HIDDEN_DATA") end
GameConfiguration={IsAnyMultiplayer=function() return false end,IsHotseat=function() return false end,
    IsWorldBuilderEditor=function() return false end}
Automation={IsActive=function() return false end}
Events={LoadGameViewStateDone={Add=function() end},LocalPlayerChanged={Add=function() end}}
Game={GetLocalPlayer=function() return 0 end,GetLocalObserver=function() return 0 end,
    GetCurrentGameTurn=function() return 8 end,IsAllowTacticalCommands=function() return settings.tactical end}
UI={IsProcessingMessages=function() return false end,
    RequestPlayerOperation=function(player,op,params) table.insert(calls,{kind="player",op=op,params=params}) end}
Locale={Lookup=function(s) return s end}
function members(values)
    local i=0; return function() i=i+1; if values[i] then return i,values[i] end end
end
function own_read(value) assert(settings.owner==0,"wrong owner"); reads.unit=reads.unit+1; return value end
unit={GetOwner=function() return settings.owner end,GetID=function() return own_read(10) end,
    GetX=function() return own_read(2) end,GetY=function() return own_read(2) end,
    GetMovesRemaining=function() return settings.moves end,GetUnitType=function() return own_read(1) end,
    GetCombat=function() return own_read(settings.combat) end,
    GetRangedCombat=function() return own_read(settings.ranged_combat) end,
    GetBombardCombat=function() return own_read(settings.bombard_combat) end,
    GetReligiousStrength=function() return own_read(settings.religious_strength) end,
    GetComponentID=function() return {player=0,id=10} end}
other={GetOwner=function() return 0 end,GetID=function() return 11 end}
own_district={GetOwner=function() return 0 end,GetID=function() return 30 end}
city={GetOwner=function() return 0 end,GetID=function() return 20 end,
    GetName=function() return "Own city" end,
    GetX=function() return 2 end,GetY=function() return 2 end,
    GetDistricts=function() return {Members=function() return members({own_district}) end,
        HasDistrict=function(self,index) return index==1 or index==4 end} end}
target_unit=setmetatable({}, {__index=function(self,key)
    if not settings.detected then return forbidden end
    if key=="GetOwner" then return function() return 1 end end
    if key=="GetX" then return function() return settings.target_x end end
    if key=="GetY" then return function() return 2 end end
    return forbidden
end})
target_city={GetOwner=function() reads.foreign=reads.foreign+1; return 1 end,
    GetID=function() return 21 end,GetName=function() return "Visible city" end,
    GetX=function() return 3 end,GetY=function() return 2 end}
plot={GetX=function() return 3 end,GetY=function() return 2 end,GetOwner=function() return 0 end}
Map={GetGridSize=function() return 100,80 end,
    GetPlot=function(x,y) assert(settings.visible and settings.revealed); reads.plot=reads.plot+1; return plot end,
    GetPlotDistance=function() return 1 end,GetPlotByIndex=forbidden}
MapLayers={ANY=9}
Units={GetUnitsInPlotLayerID=function() return {target_unit} end}
PlayersVisibility={[0]={IsRevealed=function() return settings.revealed end,
    IsVisible=function() return settings.visible end,
    IsUnitVisible=function(self,u) return settings.detected end}}
dip={HasMet=function(self,id) return id==1 end,GetNextEscapingSpyID=function() return settings.escape end}
player={IsAlive=function() return true end,IsHuman=function() return true end,
    IsTurnActive=function() return true end,IsTurnActiveComplete=function() return true end,
    GetUnits=function() return {Members=function() return members({unit,other}) end} end,
    GetCities=function() return {Members=function() return members({city}) end} end,
    GetDiplomacy=function() return dip end}
Players=setmetatable({[0]=player},{__index=forbidden})
Cities={GetPlotPurchaseCity=function() assert(settings.escape==10); return city end}
CityManager={GetCityAt=function(x,y)
    assert(settings.visible and settings.revealed)
    if settings.foreign_city then return target_city end
end, CanStartCommand=function(c,hash,params) reads.can=reads.can+1; return settings.can end,
    RequestCommand=function(c,hash,params) table.insert(calls,{kind="city",op=hash,params=params}) end}
CombatManager={IsAttackChangeWarState=function() if settings.war then return {1} else return {} end end}
function enums()
    local id=100
    return setmetatable({PARAM_X="x",PARAM_Y="y",PARAM_X0="x0",PARAM_Y0="y0",PARAM_X1="x1",PARAM_Y1="y1",
        PARAM_MODIFIERS="mods",PARAM_UNIT_PLAYER="player",PARAM_UNIT_ID="unit",PARAM_PROMOTION_TYPE="promotion",
        PARAM_IMPROVEMENT_TYPE="improvement",PARAM_WMD_TYPE="weapon"},{__index=function(self,name)
        id=id+1; rawset(self,name,id); return id
    end})
end
UnitOperationTypes=enums(); UnitCommandTypes=enums(); CityCommandTypes=enums()
UnitOperationMoveModifiers={ATTACK=1,NONE=0,MOVE_IGNORE_UNEXPLORED_DESTINATION=16}
UnitCommandResults={PROMOTIONS="promotions"}
PlayerOperations={SET_ESCAPE_ROUTE=901,PARAM_DISTRICT_TYPE="district"}
function enum_rows(values)
    return setmetatable({}, {__index=function(self,key)
        local name=string.gsub(tostring(key),"^UNITOPERATION_","")
        name=string.gsub(name,"^UNITCOMMAND_","")
        return {VisibleInUI=true,Hash=values[name]}
    end})
end
GameInfo={UnitOperations=enum_rows(UnitOperationTypes),UnitCommands=enum_rows(UnitCommandTypes),Units={[1]={MakeTradeRoute=true,Spy=true,Domain="DOMAIN_LAND"}},
    UnitPromotions={[7]={Index=7,UnitPromotionType="PROMOTION_TEST",Description="PUBLIC_PROMOTION"},
        PROMOTION_TEST={Index=7,UnitPromotionType="PROMOTION_TEST",Description="PUBLIC_PROMOTION"}},
    Improvements={IMPROVEMENT_TUNNEL={Hash=222,Buildable=true}},
    WMDs={WMD_NUCLEAR_DEVICE={Index=1}},
    Districts={DISTRICT_AERODROME={Index=1,TravelTime=1},DISTRICT_HARBOR={Index=2,TravelTime=2},
        DISTRICT_COMMERCIAL_HUB={Index=3,TravelTime=3},DISTRICT_CITY_CENTER={Index=4,TravelTime=4}}}
UnitManager={CanStartOperation=function(u,hash,unused,params,results)
        reads.can=reads.can+1; return settings.can,{private=forbidden}
    end,
    RequestOperation=function(u,hash,params) table.insert(calls,{kind="operation",op=hash,params=params}) end,
    CanStartCommand=function(u,hash,params,results)
        reads.can=reads.can+1
        if hash==UnitCommandTypes.PROMOTE and results==true then return true,{promotions={settings.promotion}} end
        return settings.can,{private=forbidden}
    end,
    RequestCommand=function(u,hash,params) table.insert(calls,{kind="command",op=hash,params=params}) end}
'''


@pytest.fixture
def engine():
    vm=LuaRuntime(unpack_returned_tuples=True)
    vm.execute(ENGINE)
    lines=[]
    vm.globals().print=lines.append

    def run(kind, values, query=False):
        spec=(QUERIES if query else ACTIONS)[kind]
        values=validate(values,spec.fields)
        body='out.items=array({}); out.supported=true; out.accepted=false\n'
        body+='local function attempt(fn,...) pcall(fn,...); out.accepted=true end\n'+LUA_HELPERS
        body+='\nlocal function execute()\n'+spec.body(values)+'\nend\nexecute()'
        lines.clear()
        vm.execute(wrap(body,"units_test"))
        assert len(lines)==2 and "SECRET" not in lines[0]
        return json.loads(lines[0].split(":",1)[1])
    return vm,run


def menu_fixture(vm, kind):
    """Extend only menu tests with the native chooser context they require."""
    vm.execute('''
        settings.foreign_city=true
        ActivityTypes={ACTIVITY_AWAKE=1}
        UnitManager.GetActivityType=function() return 1 end
        unit.IsReadyToMove=function() return true end
        player.GetID=function() return 0 end
        player.GetTeam=function() return 0 end
        player.GetDiplomaticAI=function() return {GetDiplomaticStateIndex=function() return 0 end} end
        player.IsFreeCities=function() return false end
        player.IsMajor=function() return true end
        local foreign={GetID=function() return 1 end,GetTeam=function() return 1 end,
            GetCities=function() return {Members=function() return members({target_city}) end} end,
            GetDiplomaticAI=function() return {GetDiplomaticStateIndex=function() return settings.met==false and -1 or 0 end} end,
            IsFreeCities=function() return false end,IsMajor=function() return true end}
        Players[1]=foreign
        Game.GetPlayers=function() return {player,foreign} end
        Cities.GetCityInPlot=function(x,y) if x==2 and y==2 then return city end end
        local manager={GetTradeRoutePath=function(_,a,b,c,d) return d==21 and {"PRIVATE_ROUTE"} or {} end}
        for _,side in ipairs({"Origin","Destination"}) do
            manager["Calculate"..side.."YieldsFromPotentialRoute"]=function() return {2,0,0,0,0,0} end
            manager["Calculate"..side.."YieldsFromPath"]=function() return {1,0,0,0,0,0} end
            manager["Calculate"..side.."YieldsFromModifiers"]=function() return {3,0,0,0,0,0} end
        end
        Game.GetTradeManager=function() return manager end
        player.GetTrade=function() return {GetInternationalYieldModifier=function() return 1.5 end} end
        foreign.GetTrade=player.GetTrade
        GameInfo.Yields={}
        for i,name in ipairs({"YIELD_FOOD","YIELD_PRODUCTION","YIELD_GOLD","YIELD_SCIENCE","YIELD_CULTURE","YIELD_FAITH"}) do
            GameInfo.Yields[name]={Index=i-1}
        end
    ''')
    if kind == "spy":
        vm.execute('''
            GameConfiguration.GetValue=function() return "RULESET_EXPANSION_2" end
            GameInfo.DiplomaticStates={[0]={StateType="DIPLO_STATE_NEUTRAL"}}
            UnitOperationResults={PLOTS="plots"}
            target_city.GetDistricts=function() return {Members=function() return members({}) end} end
            Cities.GetPlotPurchaseCity=function() return settings.spy_home and city or target_city end
            unit.GetX=function() return settings.spy_home and 2 or 3 end
            own_district.GetX=function() return 3 end
            own_district.GetY=function() return 2 end
            own_district.GetType=function() return 0 end
            own_district.IsComplete=function() return true end
            GameInfo.Districts[0]={Name="Campus",DistrictType="DISTRICT_CAMPUS"}
            Map.GetPlotByIndex=function(index) assert(index==203); return plot end
            setmetatable(GameInfo.UnitOperations,{__index=function(_,key)
                local name=string.gsub(key,"^UNITOPERATION_","")
                return {VisibleInUI=true,Hash=UnitOperationTypes[name],Index=1,
                    CategoryInUI=name=="SPY_COUNTERSPY" and "COUNTERSPY" or "OFFENSIVESPY"}
            end})
            UnitManager.CanStartOperation=function(u,hash,p,params,results)
                reads.can=reads.can+1
                return settings.can,{plots={203}}
            end
        ''')


@pytest.mark.parametrize("order",list(ORDERS))
def test_normal_order_matches_exact_engine_operation(engine,order):
    vm,run=engine
    result=run("unit_order",{"unit_id":10,"order":order})
    assert result["accepted"] is True
    assert len(vm.globals().calls)==1
    assert vm.globals().calls[1]["op"]==vm.globals().UnitOperationTypes[ORDERS[order]]


def test_database_operation_hash_does_not_require_optional_named_engine_enum(engine):
    vm,run=engine
    vm.execute('GameInfo.UnitOperations.UNITOPERATION_SLEEP={VisibleInUI=true,Hash=7654321}; setmetatable(UnitOperationTypes,nil); UnitOperationTypes.SLEEP=nil')
    result=run("unit_order",{"unit_id":10,"order":"sleep"})
    assert result["accepted"] is True
    assert vm.globals().calls[1]["op"]==7654321


@pytest.mark.parametrize("command",list(COMMANDS))
def test_normal_command_matches_exact_engine_command(engine,command):
    vm,run=engine
    vm.globals().settings.target_x=2
    result=run("unit_command",{"unit_id":10,"command":command})
    assert result["accepted"] is True
    assert len(vm.globals().calls)==1
    assert vm.globals().calls[1]["op"]==vm.globals().UnitCommandTypes[COMMANDS[command]]


@pytest.mark.parametrize("mission",list(TARGETS))
def test_target_actions_use_operation_or_command_parameter_family(engine,mission):
    vm,run=engine
    result=run("unit_target",{"unit_id":10,"mission":mission,"x":3,"y":2})
    assert result["accepted"] is True
    assert vm.globals().calls[1]["kind"]==TARGETS[mission][0]
    assert vm.globals().calls[1]["params"]["x"]==3


@pytest.mark.parametrize("mission",list(SPY_MISSIONS))
def test_all_curated_spy_missions_use_normal_request(engine,mission):
    vm,run=engine
    menu_fixture(vm,"spy")
    vm.globals().settings.spy_home = mission == "SPY_COUNTERSPY"
    result=run("spy_mission",{"unit_id":10,"mission":mission,"x":3,"y":2})
    assert result["accepted"] is True
    assert vm.globals().calls[1]["op"]==vm.globals().UnitOperationTypes[mission]
    if mission != "SPY_COUNTERSPY":
        assert vm.globals().calls[1]["params"] is None


@pytest.mark.parametrize("setting",["visible","revealed"])
def test_fog_target_never_queries_engine_validity_or_map(engine,setting):
    vm,run=engine
    vm.globals().settings[setting]=False
    result=run("unit_target",{"unit_id":10,"mission":"ranged_attack","x":3,"y":2})
    assert result["accepted"] is False
    assert vm.globals().reads["can"]==0
    assert vm.globals().reads["plot"]==0
    assert len(vm.globals().calls)==0


@pytest.mark.parametrize("kind,params",[
    ("unit_target",{"unit_id":10,"mission":"ranged_attack","x":3,"y":2}),
    ("melee_attack",{"unit_id":10,"x":3,"y":2}),
    ("city_attack",{"city_id":20,"x":3,"y":2}),
    ("district_attack",{"city_id":20,"district_id":30,"x":3,"y":2}),
])
def test_invisible_enemy_does_not_allow_attack_or_read_getters(engine,kind,params):
    vm,run=engine
    vm.globals().settings.detected=False
    result=run(kind,params)
    assert result["accepted"] is False
    assert vm.globals().reads["hidden"]==0
    assert vm.globals().reads["can"]==0
    assert len(vm.globals().calls)==0


def test_missing_detection_api_fails_closed(engine):
    vm,run=engine
    vm.execute("PlayersVisibility[0].IsUnitVisible=nil")
    assert run("melee_attack",{"unit_id":10,"x":3,"y":2})["accepted"] is False
    assert vm.globals().reads["hidden"]==0


def test_foreign_entity_id_rejected_before_unit_fields(engine):
    vm,run=engine
    vm.globals().settings.owner=1
    assert run("unit_command",{"unit_id":10,"command":"upgrade"})["accepted"] is False
    assert vm.globals().reads["unit"]==0


def test_melee_does_not_implicitly_declare_war_or_query_path(engine):
    vm,run=engine
    vm.globals().settings.war=True
    assert run("melee_attack",{"unit_id":10,"x":3,"y":2})["accepted"] is False
    assert len(vm.globals().calls)==0
    vm.globals().settings.war=False
    assert run("melee_attack",{"unit_id":10,"x":3,"y":2})["accepted"] is True
    assert vm.globals().calls[1]["params"]["mods"]==1
    assert vm.globals().reads["can"]==0


def test_zero_movement_ranged_unit_is_not_offered_or_submitted_when_engine_says_yes(engine):
    vm,run=engine
    vm.globals().settings.moves=0
    items=run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"]
    assert "ranged_attack" not in {item["id"] for item in items}
    # Availability remains permissive in this fixture, matching the stock-UI
    # documented engine quirk; our own movement check must still reject it.
    vm.globals().reads.can=0
    result=run("unit_target",{"unit_id":10,"mission":"ranged_attack","x":3,"y":2})
    assert result["accepted"] is False and vm.globals().reads.can==0
    assert len(vm.globals().calls)==0


def test_ranged_action_rechecks_movement_after_target_observation(engine):
    vm,run=engine
    item=next(i for i in run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"] if i["id"]=="ranged_attack")
    vm.globals().settings.moves=0
    action=dict(item["action"])
    kind=action.pop("type")
    assert run(kind,action)["accepted"] is False
    assert len(vm.globals().calls)==0


@pytest.mark.parametrize("combat,religious,allowed",[(0,0,False),(20,0,True),(0,100,True)])
def test_melee_capability_excludes_civilians_but_preserves_military_and_religious_units(engine,combat,religious,allowed):
    vm,run=engine
    vm.globals().settings.combat=combat
    vm.globals().settings.religious_strength=religious
    items=run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"]
    assert ("melee_attack" in {item["id"] for item in items}) is allowed
    assert run("melee_attack",{"unit_id":10,"x":3,"y":2})["accepted"] is allowed
    assert len(vm.globals().calls)==int(allowed)


@pytest.mark.parametrize("combat,ranged,bombard,domain,allowed",[
    (15,25,0,"DOMAIN_LAND",False),   # Archer: combat is also defense, not melee permission.
    (5,15,0,"DOMAIN_LAND",False),    # Slinger.
    (25,0,35,"DOMAIN_LAND",False),   # Catapult uses bombard.
    (10,0,0,"DOMAIN_LAND",True),     # Scout has no UNITTYPE_MELEE AI tag.
    (130,120,0,"DOMAIN_LAND",True),  # Giant Death Robot supports both weapons.
    (35,25,0,"DOMAIN_LAND",True),    # Persian Immortal supports both weapons.
    (60,70,0,"DOMAIN_SEA",False),    # Naval ranged weapons must not imply melee.
    (55,0,0,"DOMAIN_SEA",True),      # Naval melee remains available.
    (105,105,0,"DOMAIN_AIR",False),  # Air missions have their own request path.
    (20,0,0,"UNKNOWN_DOMAIN",False),
])
def test_melee_candidates_follow_stock_right_click_weapon_priority(engine,combat,ranged,bombard,domain,allowed):
    vm,run=engine
    settings=vm.globals().settings
    settings.combat=combat
    settings.ranged_combat=ranged
    settings.bombard_combat=bombard
    vm.globals().GameInfo.Units[1].Domain=domain
    items=run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"]
    assert ("melee_attack" in {item["id"] for item in items}) is allowed
    # The fixture intentionally permits ranged operations for all units; the
    # extra melee filter must not suppress the ordinary engine ranged option.
    assert "ranged_attack" in {item["id"] for item in items}
    assert run("melee_attack",{"unit_id":10,"x":3,"y":2})["accepted"] is allowed
    assert len(vm.globals().calls)==int(allowed)


def test_archer_cannot_fall_back_to_melee_when_ranged_operation_is_unavailable(engine):
    vm,run=engine
    vm.execute("settings.combat=15; settings.ranged_combat=25; settings.can=false")
    assert run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"]==[]
    assert run("melee_attack",{"unit_id":10,"x":3,"y":2})["accepted"] is False
    assert len(vm.globals().calls)==0


@pytest.mark.parametrize("missing",["GetRangedCombat","GetBombardCombat","GetUnitType"])
def test_melee_weapon_capability_missing_api_fails_closed(engine,missing):
    vm,run=engine
    vm.globals().unit[missing]=None
    assert "melee_attack" not in {
        item["id"] for item in run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"]
    }
    assert run("melee_attack",{"unit_id":10,"x":3,"y":2})["accepted"] is False
    assert len(vm.globals().calls)==0


def test_melee_action_rechecks_weapon_capability_after_observation(engine):
    vm,run=engine
    action=dict(next(item["action"] for item in run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"]
                     if item["id"]=="melee_attack"))
    vm.globals().settings.ranged_combat=25
    kind=action.pop("type")
    assert run(kind,action)["accepted"] is False
    assert len(vm.globals().calls)==0


@pytest.mark.parametrize("mission",["air_attack","air_deploy","air_rebase","coastal_raid","priority_attack"])
def test_ranged_movement_guard_does_not_override_engine_rules_for_other_missions(engine,mission):
    vm,run=engine
    vm.globals().settings.moves=0
    items=run("unit_targets",{"unit_id":10,"x":3,"y":2},True)["items"]
    assert mission in {item["id"] for item in items}
    assert run("unit_target",{"unit_id":10,"mission":mission,"x":3,"y":2})["accepted"] is True


def test_promotion_revalidates_actual_offered_index(engine):
    vm,run=engine
    vm.globals().settings.promotion=9
    assert run("unit_promote",{"unit_id":10,"promotion":"PROMOTION_TEST"})["accepted"] is False
    vm.globals().settings.promotion=7
    assert run("unit_promote",{"unit_id":10,"promotion":"PROMOTION_TEST"})["accepted"] is True
    assert vm.globals().calls[1]["params"]["promotion"]==7


def test_formation_requires_two_own_entities(engine):
    vm,run=engine
    assert run("unit_form",{"unit_id":10,"other_unit_id":999,"formation":"army"})["accepted"] is False
    assert run("unit_form",{"unit_id":10,"other_unit_id":11,"formation":"army"})["accepted"] is True
    assert vm.globals().calls[1]["params"]["player"]==0
    assert vm.globals().calls[1]["params"]["unit"]==11


def test_trade_source_and_destination_are_not_reversed(engine):
    vm,run=engine
    menu_fixture(vm,"trade")
    assert run("trade_route",{"unit_id":10,"x":3,"y":2})["accepted"] is True
    params=vm.globals().calls[1]["params"]
    assert params["x0"]==3 and params["x1"]==2


def test_spy_destination_missing_or_unmet_not_probed(engine):
    vm,run=engine
    menu_fixture(vm,"spy")
    vm.globals().settings.met=False
    # Menu-entry checks are actor-local; the excluded city itself is never probed.
    vm.execute('Map.GetPlot=function() error("excluded city") end')
    assert run("spy_travel",{"unit_id":10,"x":3,"y":2})["accepted"] is False
    assert len(vm.globals().calls)==0


def test_escape_only_pending_own_spy_routes_and_not_foreign_city_identity(engine):
    vm,run=engine
    assert run("spy_escape_routes",{},True)["items"]==[]
    vm.globals().settings.escape=10
    vm.globals().settings.visible=False
    items=run("spy_escape_routes",{},True)["items"]
    assert {i["id"] for i in items}=={"DISTRICT_AERODROME","DISTRICT_CITY_CENTER"}
    assert vm.globals().reads["foreign"]==0
    assert run("spy_escape",{"district":"DISTRICT_HARBOR"})["accepted"] is False
    assert run("spy_escape",{"district":"DISTRICT_CITY_CENTER"})["accepted"] is True


@pytest.mark.parametrize("kind,params",[
    ("unit_promotions",{"unit_id":10}),
    ("unit_formations",{"unit_id":10}),
    ("unit_targets",{"unit_id":10,"x":3,"y":2}),
    ("trade_routes",{"unit_id":10,"x":3,"y":2}),
    ("spy_missions",{"unit_id":10,"x":3,"y":2}),
])
def test_discovery_only_returns_validated_action_payloads(engine,kind,params):
    vm,run=engine
    vm.globals().settings.foreign_city=True
    if kind in {"trade_routes","spy_missions"}:
        menu_fixture(vm,"trade" if kind=="trade_routes" else "spy")
    result=run(kind,params,True)
    assert result["ok"] is True and result["supported"] is True
    for item in result["items"]:
        if "action" not in item:
            continue
        action=item["action"]
        validate(action,{"type":"enum:"+action["type"],**ACTIONS[action["type"]].fields})
        assert item.get("owner_id",item.get("menu_owner_id"))==0
    assert len(vm.globals().calls)==0


def test_source_orders_and_commands_discovery(engine):
    vm,run=engine
    vm.globals().settings.target_x=2
    vm.execute('GameInfo.Improvements=setmetatable({}, {__call=function() return function() return nil end end})')
    result=run("unit_actions",{"unit_id":10},True)
    assert {i["id"] for i in result["items"]}==set(ORDERS)|set(COMMANDS)|{"found_city","fortify"}
    assert len(vm.globals().calls)==0


@pytest.mark.parametrize("kind,params",[
    ("transfer_trader",{"unit_id":10,"city_id":20}),
    ("district_attack",{"city_id":20,"district_id":30,"x":3,"y":2}),
    ("city_attack",{"city_id":20,"x":3,"y":2}),
    ("wmd_strike",{"unit_id":10,"weapon":"WMD_NUCLEAR_DEVICE","x":3,"y":2}),
    ("build_adjacent_improvement",{"unit_id":10,"improvement":"IMPROVEMENT_TUNNEL","x":3,"y":2}),
])
def test_remaining_request_families_run_normal_engine_request(engine,kind,params):
    vm,run=engine
    assert run(kind,params)["accepted"] is True
    assert len(vm.globals().calls)==1


def test_icbm_source_must_belong_to_own_city_and_xy0_xy1_match_stock(engine):
    vm,run=engine
    vm.execute("Cities.GetPlotPurchaseCity=function() return city end")
    params={"city_id":20,"source_x":2,"source_y":2,"x":3,"y":2,"weapon":"WMD_NUCLEAR_DEVICE"}
    assert run("icbm_strike",params)["accepted"] is True
    called=vm.globals().calls[1]["params"]
    assert called["x0"]==2 and called["x1"]==3 and called["weapon"]==1
    vm.execute("plot.GetOwner=function() return 1 end")
    assert run("icbm_strike",params)["accepted"] is False
    assert len(vm.globals().calls)==1


@pytest.mark.parametrize("category",["trade_destinations","spy_destinations"])
def test_menu_destination_discovery_accepts_offered_fog_without_map_dump(engine,category):
    vm,run=engine
    menu_fixture(vm,"trade" if category=="trade_destinations" else "spy")
    vm.execute('''
        PlayersVisibility[0].IsVisible=function() return false end
        Map.GetPlot=function(x,y) assert((x==3 or x==2) and y==2); reads.plot=reads.plot+1; return plot end
        CityManager.GetCityAt=forbidden
    ''')
    result=run(category,{"unit_id":10,"offset":0},True)
    assert result["ok"] is True and result["supported"] is True
    choices=[i for i in result["items"] if "action" in i]
    assert any(i["action"]["x"]==3 and i["action"]["y"]==2 for i in choices)
    assert result["items"][-1]["value"]==-1
    assert "path" not in json.dumps(result)
    assert len(vm.globals().calls)==0


def test_trade_destination_requires_stock_path_existence_but_never_returns_path(engine):
    vm,run=engine
    menu_fixture(vm,"trade")
    vm.execute('''
        Game.GetTradeManager=function() return {GetTradeRoutePath=function() return {} end} end
    ''')
    result=run("trade_destinations",{"unit_id":10,"offset":0},True)
    assert result["ok"] and result["supported"]
    assert all("action" not in i for i in result["items"])


def test_trader_origins_and_city_combat_discovery(engine):
    vm,run=engine
    vm.execute("city.GetDistrictID=function() return 29 end")
    origins=run("trader_origins",{"unit_id":10},True)
    assert origins["items"][0]["action"]=={"type":"transfer_trader","unit_id":10,"city_id":20}
    combat=run("city_combat",{"city_id":20,"x":3,"y":2},True)
    assert {i["action"]["type"] for i in combat["items"]}=={"city_attack","district_attack"}
    assert len(vm.globals().calls)==0


@pytest.mark.parametrize("field,value",[("order","EXECUTE_SCRIPT"),("order","FORTIFY;cheat()")])
def test_operation_escape_hatches_rejected(field,value):
    with pytest.raises(ValueError):
        validate({"unit_id":10,field:value},ACTIONS["unit_order"].fields)


def test_public_target_query_noninterference_for_hidden_units(engine):
    vm,run=engine
    vm.globals().settings.detected=False
    a=run("unit_targets",{"unit_id":10,"x":3,"y":2},True)
    vm.execute("Units.GetUnitsInPlotLayerID=function() return {} end")
    b=run("unit_targets",{"unit_id":10,"x":3,"y":2},True)
    assert a==b
    assert vm.globals().reads["hidden"]==0


def test_specialist_details_only_read_own_actor(engine):
    vm,run=engine
    vm.execute('''
        unit.GetActionCharges=function() return 2 end
        unit.GetSpreadCharges=function() return 3 end
        unit.GetExperience=function() return {GetExperiencePoints=function() return 12 end,
            GetLevel=function() return 2 end,GetPromotions=function() return {7} end} end
        unit.GetGreatPerson=function() return {GetActionCharges=function() return 1 end,
            GetIndividual=function() return 3 end} end
        GameInfo.GreatPersonIndividuals={[3]={GreatPersonIndividualType="GREAT_PERSON_INDIVIDUAL_TEST"}}
        unit.GetSpyOperation=function() return -1 end
    ''')
    result=run("unit_details",{"unit_id":10},True)
    values={i["id"]:i["value"] for i in result["items"]}
    assert values["action_charges"]==2 and values["spread_charges"]==3
    assert values["experience"]==12 and values["great_person_charges"]==1
    assert values["promotion:PROMOTION_TEST"]=="PROMOTION_TEST"
    assert values["spy_operation"]=="NONE"
    vm.globals().settings.owner=1
    assert run("unit_details",{"unit_id":10},True)["items"]==[]


def test_trade_public_origin_yields_apply_stock_own_multiplier(engine):
    vm,run=engine
    menu_fixture(vm,"trade")
    result=run("trade_routes",{"unit_id":10,"x":3,"y":2},True)
    assert result["items"][1]["id"]=="origin:YIELD_FOOD"
    assert result["items"][1]["value"]==9
    assert "PRIVATE_ROUTE" not in json.dumps(result)


@pytest.mark.parametrize("activity",["ACTIVITY_HEAL","ACTIVITY_SLEEP","ACTIVITY_OPERATION"])
def test_unit_readiness_does_not_infer_needs_orders_from_unspent_moves(engine,activity):
    vm,run=engine
    vm.execute('''
        settings.moves=3
        unit.IsReadyToMove=function() return true end
        unit.IsReadyToSelect=function() return false end
        unit.GetFortifyTurns=function() return 2 end
        UnitManager.GetActivityType=function(u) assert(u==unit); return 4 end
        local collection=player:GetUnits()
        collection.GetFirstReadyUnit=function() return nil end
        player.GetUnits=function() return collection end
    ''')
    vm.execute(f'ActivityTypes={{ {activity}=4 }}')
    values={i["id"]:i["value"] for i in run("unit_details",{"unit_id":10},True)["items"]}
    assert values["ready_to_move"] is True and values["ready_to_select"] is False
    assert values["first_ready"] is False
    assert values["activity"]==activity and values["activity_type"]==4
    assert values["fortify_turns"]==2 and "needs_orders" not in values
    assert len(vm.globals().calls)==0


def test_unit_details_identifies_first_ready_own_unit_using_stock_collection_query(engine):
    vm,run=engine
    vm.execute('''
        first_ready=unit
        local collection=player:GetUnits()
        collection.GetFirstReadyUnit=function() return first_ready end
        player.GetUnits=function() return collection end
    ''')
    def values():
        return {i["id"]:i["value"] for i in run("unit_details",{"unit_id":10},True)["items"]}
    assert values()["first_ready"] is True
    vm.execute('first_ready=other')
    assert values()["first_ready"] is False
    vm.execute('first_ready={GetOwner=function() return 1 end,GetID=forbidden}')
    assert "first_ready" not in values()
    assert vm.globals().reads.hidden==0


def test_missing_readiness_capabilities_are_omitted_not_reported_false(engine):
    _,run=engine
    values={i["id"]:i["value"] for i in run("unit_details",{"unit_id":10},True)["items"]}
    assert not {"ready_to_move","ready_to_select","activity_type","activity","first_ready","fortify_turns"}&values.keys()


def test_unknown_activity_keeps_numeric_value_without_inventing_name(engine):
    vm,run=engine
    vm.execute('UnitManager.GetActivityType=function() return 99 end; ActivityTypes={ACTIVITY_AWAKE=1}')
    values={i["id"]:i["value"] for i in run("unit_details",{"unit_id":10},True)["items"]}
    assert values["activity_type"]==99 and "activity" not in values
