"""Execute empire requests and discovery in Lua, with hidden-state traps."""

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.empire import ACTIONS, QUERIES


BOOT = r'''
calls = {}
controls = {strategic=true,owner=0,visible=true,known=true,can=true,appointed=false,
    discovered=false,policy_changed=false,policy_cost=0,selected_count=2,belief_taken=false,
    founded=-1,has_prophet=true,foreign_reads=0,city_reads=0,plot_reads=0,placed=false,
    civic_completed=true,government_changed=false,rebelled=true,considered=false,money=1000,earned=2,equipped=0,
    pillaged=false,built=false}
function forbid() error('SECRET') end
function defs(field, rows)
    local t = {}
    for _, row in ipairs(rows) do
        t[row[field]]=row; if row.Index then t[row.Index]=row end; if row.Hash then t[row.Hash]=row end
    end
    return setmetatable(t,{__call=function() local i=0; return function() i=i+1; return rows[i] end end})
end
function record(op,p) table.insert(calls,{op=op,p=p}) end
Game={IsAllowStrategicCommands=function() return controls.strategic end}
GameConfiguration={GetValue=function(key) assert(key=='RULESET');return controls.rules or 'RULESET_EXPANSION_2' end}
UI={RequestPlayerOperation=function(who,op,p) assert(who==0); record(op,p) end,
    GetInterfaceModeParameter=function() return true end}
PlayerOperations={APPOINT_GOVERNOR=1,PROMOTE_GOVERNOR=2,ASSIGN_GOVERNOR=3,
    RECRUIT_GREAT_PERSON=4,REJECT_GREAT_PERSON=5,PATRONIZE_GREAT_PERSON=6,
    UNLOCK_POLICIES=7,COMMEMORATE=8,FOUND_PANTHEON=9,ADD_BELIEF=10,FOUND_RELIGION=11,
    PARAM_GOVERNOR_TYPE='governor',PARAM_GOVERNOR_PROMOTION_TYPE='promotion',
    PARAM_PLAYER_ONE='owner',PARAM_CITY_DEST='city',PARAM_GREAT_PERSON_INDIVIDUAL_TYPE='person',
    PARAM_YIELD_TYPE='yield',PARAM_COMMEMORATION_TYPE='commemoration',PARAM_BELIEF_TYPE='belief',
    PARAM_INSERT_MODE='insert',VALUE_EXCLUSIVE=1,PARAM_RELIGION_TYPE='religion',PARAM_RELIGION_CUSTOM_NAME='name'}
CityOperationTypes={BUILD=20,PARAM_UNIT_TYPE='unit',PARAM_BUILDING_TYPE='building',
    PARAM_DISTRICT_TYPE='district',PARAM_PROJECT_TYPE='project',PARAM_X='x',PARAM_Y='y',
    PARAM_INSERT_MODE='insert',VALUE_APPEND=2,VALUE_EXCLUSIVE=1,VALUE_REMOVE_AT=3,VALUE_MOVE_TO=4,VALUE_REPLACE_AT=5,
    MILITARY_FORMATION_TYPE='formation',PARAM_QUEUE_LOCATION='index',
    PARAM_QUEUE_SOURCE_LOCATION='source',PARAM_QUEUE_DESTINATION_LOCATION='destination'}
CityCommandTypes={PURCHASE=21,MANAGE=22,SWAP_TILE_OWNER=23,SET_FOCUS=24,
    DESTROY=25,NAME_CITY=26,PARAM_NAME='name',
    PARAM_UNIT_TYPE='unit',PARAM_BUILDING_TYPE='building',PARAM_DISTRICT_TYPE='district',
    PARAM_YIELD_TYPE='yield',PARAM_MILITARY_FORMATION_TYPE='formation',PARAM_X='x',PARAM_Y='y',
    PARAM_PLOT_PURCHASE='plot',PARAM_MANAGE_CITIZEN='citizen',PARAM_SWAP_TILE_OWNER='swap',
    PARAM_FLAGS='flags',PARAM_DATA0='value'}
CityCommandResults={PLOTS='plots',CITIZENS='citizens',MAX_CITIZENS='max',LOCKED_CITIZENS='locked'}
MilitaryFormationTypes={STANDARD_MILITARY_FORMATION=0,CORPS_MILITARY_FORMATION=1,ARMY_MILITARY_FORMATION=2}
YieldTypes={GOLD=2,FAITH=5}
UnitOperationTypes={PARAM_FLAGS='flags'}
CityDestroyDirectives={KEEP=1,REJECT=2}
GlobalParameters={GOVERNMENT_UNLOCK_WITH_FAITH=0}
GameCapabilities={HasCapability=function() return true end}
GameInfo={
 Governors=defs('GovernorType',{{GovernorType='GOVERNOR_BUILDER',Index=0,Hash=100,Name='Builder'},
    {GovernorType='GOVERNOR_SECRET',Index=1,Hash=101,Name='SECRET_SOCIETY_NAME'}}),
 GovernorPromotions=defs('GovernorPromotionType',{{GovernorPromotionType='GOVERNOR_PROMOTION_TOOLS',Index=2,Hash=102,Name='Tools'}}),
 GovernorPromotionSets=defs('GovernorType',{{GovernorType='GOVERNOR_BUILDER',GovernorPromotion='GOVERNOR_PROMOTION_TOOLS'}}),
 GreatPersonIndividuals=defs('GreatPersonIndividualType',{{GreatPersonIndividualType='GREAT_PERSON_INDIVIDUAL_TEST',Index=3,Hash=103,Name='Great Person'}}),
 Governments=defs('GovernmentType',{{GovernmentType='GOVERNMENT_CHIEFDOM',Index=0,Hash=104,Name='Chiefdom'}}),
 GovernmentSlots=defs('GovernmentSlotType',{{GovernmentSlotType='SLOT_MILITARY',Index=0},{GovernmentSlotType='SLOT_ECONOMIC',Index=1}}),
 Policies=defs('PolicyType',{{PolicyType='POLICY_MILITARY',Index=0,Hash=105,GovernmentSlotType='SLOT_MILITARY'},
    {PolicyType='POLICY_ECONOMIC',Index=1,Hash=106,GovernmentSlotType='SLOT_ECONOMIC'}}),
 CommemorationTypes=defs('CommemorationType',{{CommemorationType='COMMEMORATION_SCIENCE',Index=0,Hash=107},
    {CommemorationType='COMMEMORATION_CULTURE',Index=1,Hash=108}}),
 Beliefs=defs('BeliefType',{{BeliefType='BELIEF_PANTHEON',Index=0,Hash=109,BeliefClassType='BELIEF_CLASS_PANTHEON'},
    {BeliefType='BELIEF_FEED',Index=1,Hash=110,BeliefClassType='BELIEF_CLASS_FOLLOWER'},
    {BeliefType='BELIEF_TITHE',Index=2,Hash=111,BeliefClassType='BELIEF_CLASS_FOUNDER'}}),
 Religions=defs('ReligionType',{{ReligionType='RELIGION_CUSTOM',Index=1,Hash=112,RequiresCustomName=true}}),
 Units=defs('UnitType',{{UnitType='UNIT_WARRIOR',Index=0,Hash=113,PurchaseYield='YIELD_GOLD'}}),
 Buildings=defs('BuildingType',{{BuildingType='BUILDING_WONDER',Index=0,Hash=114,RequiresPlacement=true,IsWonder=true,PurchaseYield='YIELD_GOLD'},
    {BuildingType='BUILDING_MONUMENT',Index=1,Hash=115,PurchaseYield='YIELD_GOLD'}}),
 Districts=defs('DistrictType',{{DistrictType='DISTRICT_CAMPUS',Index=0,Hash=116,RequiresPlacement=true}}),
 Projects=defs('ProjectType',{{ProjectType='PROJECT_REPAIR',Index=0,Hash=117}}),
 Yields=defs('YieldType',{{YieldType='YIELD_GOLD',Index=2},{YieldType='YIELD_FAITH',Index=5}})
}
governors={
 HasGovernor=function(self,hash) return hash==100 and controls.appointed end,
 CanEverAppointGovernor=function(self,hash) return hash==100 or controls.discovered end,
 CanAppoint=function() return controls.can end,
 CanEarnPromotion=function(self,hash,promo) return controls.can and hash==100 and promo==102 end,
 CanAssignGovernor=function(self,hash,city,visible) assert(visible==true);return controls.can end,
 GetGovernor=function() return {} end,GetGovernorPoints=function() return 3 end,GetGovernorPointsSpent=function() return 1 end,
 HasTitleBeenConsidered=function() return controls.considered end,
 SetTitleConsidered=function(self,value) record(32,{value=value}) end}
people={GetTimeline=function() return {{Individual=103,Cost=80}} end,
 CanRecruitPerson=function(self,me,id) assert(me==0 and id==103);return controls.can end,
 CanRejectPerson=function(self,me,id) assert(me==0 and id==103);return controls.can end,
 CanPatronizePerson=function(self,me,id,y) assert(me==0 and id==103);return controls.can end,
 GetPatronizeCost=function() return 300 end,GetRejectCost=function() return 16 end}
Game.GetGreatPeople=function() return people end
culture={CanChangeGovernmentAtAll=function() return controls.can end,IsGovernmentUnlocked=function() return true end,
 RequestChangeGovernment=function(self,hash) record(30,{hash=hash}) end,
 RequestPolicyChanges=function(self,clear,add) record(31,{clear=clear,add=add}) end,
 PolicyChangeMade=function() return controls.policy_changed end,GetCostToUnlockPolicies=function() return controls.policy_cost end,
 GetNumPolicySlots=function() return 2 end,GetSlotType=function(self,index) return index end,
 GetSlotPolicy=function(self,index) return index end,IsPolicyUnlocked=function() return true end,
 IsPolicyBanned=function() return false end,CanPolicyBeSlotted=function() return true end,
 IsPolicyObsolete=function() return false end,GetCurrentGovernment=function() return 0 end,
 GovernmentChangeMade=function() return controls.government_changed end,
 CivicCompletedThisTurn=function() return controls.civic_completed end,
 GovernmentChangeConsidered=function() return controls.considered end,
 SetGovernmentChangeConsidered=function(self,value) record(33,{value=value}) end}
eras={GetPlayerNumAllowedCommemorations=function() return controls.selected_count end,
    GetPlayerCommemorateChoices=function() return {0,1} end,
    HasGoldenAge=function() return false end,HasDarkAge=function() return false end}
Game.GetEras=function() return eras end
religion={GetReligionTypeCreated=function() return controls.founded end,
    CanCreatePantheon=function() return controls.can end,GetNumBeliefsEarned=function() return controls.earned end,
    HasReligiousFoundingUnit=function() return controls.has_prophet end,GetPantheon=function() return -1 end,
    GetFaithBalance=function() return controls.money end,CanAfford=function() return controls.can end}
religions={IsInSomePantheon=function() return controls.belief_taken end,
    IsInSomeReligion=function() return false end,IsTooManyForReligion=function() return false end,
    HasBeenFounded=function() return false end,
    GetReligions=function()
        local beliefs={};for i=1,controls.equipped do beliefs[i]=i end
        return {setmetatable({Founder=3},{__index=forbid}),{Founder=0,Beliefs=beliefs}}
    end}
Game.GetReligion=function() return religions end
queue={HasBeenPlaced=function() return controls.placed end,CanProduce=function() return controls.can end,
    GetSize=function() return 2 end,GetAt=function(self,index) if index==0 then return {UnitType=0} else return {BuildingType=1} end end}
city={GetOwner=function() return controls.owner end,GetID=function() controls.city_reads=controls.city_reads+1;assert(controls.owner==0);return 42 end,
    GetGold=function() return {IsUnitFaithPurchaseEnabled=function() return true end,IsBuildingFaithPurchaseEnabled=function() return true end} end,
    GetX=function() return 2 end,GetY=function() return 2 end,GetName=function() return 'Own City' end,
    GetBuildings=function() return {IsPillaged=function() return controls.pillaged end,HasBuilding=function() return controls.built end} end,
    GetDistricts=function() return {HasDistrict=function() return controls.built end} end,
    GetBuildQueue=function() return queue end,GetCitizens=function() return {IsFavoredYield=function() return false end,IsDisfavoredYield=function() return false end} end}
function members(entity) local done=false;return function() if not done then done=true;return 1,entity end end end
player={GetGovernors=function() return governors end,GetCulture=function() return culture end,
    GetReligion=function() return religion end,GetCities=function() return {Members=function() return members(city) end,
        GetNextRebelledCity=function() if controls.rebelled then return city end end} end,
    GetTreasury=function() return {GetGoldBalance=function() return controls.money end,CanAfford=function() return controls.can end} end,
    GetDiplomacy=function() return {HasMet=function() return controls.known end} end}
Players={[0]=player}
vis={IsVisible=function(self,x,y) return controls.visible and x~=9 end,
    IsRevealed=function(self,x,y) return controls.visible and x~=9 end}
function plot(x,y)
    return {GetX=function() return x end,GetY=function() return y end,
        GetOwner=function() controls.plot_reads=controls.plot_reads+1;assert(controls.visible and x~=9);return 0 end}
end
Map={GetGridSize=function() return 100,100 end,
    GetPlot=function(x,y) assert(controls.visible and x~=9);return plot(x,y) end,
    GetPlotByIndex=function(index) if index==9 then return plot(9,2) end;return plot(2,2) end,
    GetCityPlots=function() return {GetPurchasedPlots=function() return {2,9} end} end}
CityManager={GetCityAt=function(x,y) controls.foreign_reads=controls.foreign_reads+1;return {
    GetOwner=function() return 1 end,GetID=function() return 55 end,GetX=function() return x end,GetY=function() return y end} end,
    CanStartOperation=function(c,op,p,results) assert(c==city and results==false);return controls.can end,
    RequestOperation=function(c,op,p) assert(c==city);record(op,p) end,
    CanStartCommand=function(c,op,visibility,p,results)
        assert(c==city)
        if visibility==true then assert(results==false);return controls.can end
        if op~=25 then assert(visibility==false and results==(p.unit~=nil and p.formation==nil)) end;return controls.can end,
    RequestCommand=function(c,op,p) assert(c==city);record(op,p) end,
    GetCommandTargets=function(c,op,p) assert(c==city);return {plots={2,9},citizens={1,77},max={3,88},locked={1,99}} end}
'''


@pytest.fixture
def engine():
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(BOOT)

    def run(kind, args, query=False):
        spec = (QUERIES if query else ACTIONS)[kind]
        validate(args, spec.fields)
        full_args = args if query else {"type": kind, **args}
        script = "local me=0; local player=Players[0]; local out={items={}}; local function array(x) return x end\n"
        script += LUA_HELPERS
        script += "\nlocal function attempt(fn,...) fn(...);out.accepted=true end\nlocal function run()\n"
        script += spec.body(full_args) + "\nend\nrun()\nreturn out"
        return runtime.execute(script)

    return runtime, run


def test_governor_discovery_does_not_list_unknown_society(engine):
    vm, run = engine
    result = run("governors", {}, True)
    ids = [r["id"] for r in result["items"].values()]
    assert "GOVERNOR_BUILDER" in ids
    assert not any("SECRET" in i for i in ids)
    vm.globals().controls.discovered = True
    result = run("governors", {}, True)
    assert "GOVERNOR_SECRET" in [r["id"] for r in result["items"].values()]


def test_governor_current_assignment_establishment_and_earned_promotions(engine):
    vm, run = engine
    vm.execute('''
controls.appointed=true
governors.GetGovernor=function() return {
    GetAssignedCity=function() return city end,
    IsEstablished=function() return false end,
    GetTurnsToEstablish=function() return 5 end,
    GetTurnsOnSite=function() return 2 end,
    GetNeutralizedTurns=function() return 0 end,
    HasPromotion=function(self,hash) return hash==102 end
} end
''')
    rows = {row['id']: row for row in run('governors', {}, True)['items'].values()}
    assert rows['GOVERNOR_BUILDER:assigned_city']['value'] == 42
    assert rows['GOVERNOR_BUILDER:assigned_city']['name'] == 'Own City'
    assert rows['GOVERNOR_BUILDER:turns_until_established']['value'] == 3
    assert rows['GOVERNOR_BUILDER:established']['value'] is False
    assert rows['GOVERNOR_BUILDER:GOVERNOR_PROMOTION_TOOLS']['value'] is True
    assert rows['GOVERNOR_BUILDER:GOVERNOR_PROMOTION_TOOLS']['action'] is None


def test_city_production_discovers_formation_variants_from_normal_result_flags(engine):
    vm, run = engine
    vm.execute('''
CityOperationResults={CAN_TRAIN_CORPS='corps',CAN_TRAIN_ARMY='army'}
queue.CanProduce=function(self,item,exclusion,results)
    if exclusion==true then return true end
    assert(exclusion==false)
    if type(item)~='table' then return true end
    if item.MilitaryFormationType==0 then
        assert(results==true)
        return true,{corps=true,army=true}
    end
    assert(results==false)
    return item.MilitaryFormationType==1
end
CityManager.CanStartCommand=function(c,op,exclusion,p,results)
    assert(c==city and op==21)
    if exclusion==true then assert(results==false);return true end
    assert(exclusion==false)
    if not p.unit then assert(results==false);return true end
    if p.formation==nil then
        assert(results==true)
        return true,{corps=true,army=true}
    end
    assert(results==false)
    return p.formation==1
end
''')
    rows = {row['id']: row for row in run('city_production', {'city_id':42}, True)['items'].values()}
    assert rows['UNIT_WARRIOR:build:CORPS']['action']['formation'] == 'CORPS'
    assert rows['UNIT_WARRIOR:buy:GOLD:CORPS']['action']['formation'] == 'CORPS'
    assert rows['UNIT_WARRIOR:buy:FAITH:CORPS']['action']['formation'] == 'CORPS'
    assert not any(key.endswith(':ARMY') for key in rows)


def test_city_production_rejects_future_unlocks_when_only_current_constraints_pass(engine):
    vm,run=engine
    # Reproduces the live turn-one false-positive: false tests pass for a future
    # building, while the separate stock-UI exclusion test rejects it.
    vm.execute('''
queue.CanProduce=function(self,item,exclusion,results)
    local hash=type(item)=='table' and item.UnitType or item
    if hash==114 or hash==115 then return exclusion==false end
    return true
end
CityManager.CanStartCommand=function(c,op,exclusion,p,results)
    if p.building==114 or p.building==115 then return exclusion==false end
    return true
end
''')
    rows=run('city_production',{'city_id':42},True)['items']
    assert not any('BUILDING_' in row['id'] for row in rows.values())
    assert not run('city_build',{'city_id':42,'item':'BUILDING_MONUMENT','append':False,'formation':'STANDARD'})['accepted']
    assert not run('city_purchase',{'city_id':42,'item':'BUILDING_MONUMENT','yield':'GOLD','formation':'STANDARD'})['accepted']
    assert len(run('city_placement',{'city_id':42,'item':'BUILDING_WONDER'},True)['items'])==0
    assert not run('city_build_at',{'city_id':42,'item':'BUILDING_WONDER','x':2,'y':2,'append':False,'formation':'STANDARD'})['accepted']
    assert len(vm.globals().calls)==0


def test_city_build_replaces_only_queue_head_and_preserves_following_items(engine):
    vm,run=engine
    vm.execute('''
production_queue={113,115}
CityManager.RequestOperation=function(c,op,p)
    assert(c==city and op==20)
    if p.insert==CityOperationTypes.VALUE_EXCLUSIVE then production_queue={p.unit}
    elseif p.insert==CityOperationTypes.VALUE_REPLACE_AT then production_queue[p.destination+1]=p.unit
    else error('unexpected queue mode') end
end
''')
    assert run('city_build',{'city_id':42,'item':'UNIT_WARRIOR','append':False,'formation':'STANDARD'})['accepted']
    assert list(vm.globals().production_queue.values())==[113,115]


@pytest.mark.parametrize('met,visible', [(False,True),(True,False)])
def test_governor_foreign_assignment_detail_requires_met_and_visible(engine,met,visible):
    vm, run = engine
    vm.globals().controls.known = met
    vm.globals().controls.visible = visible
    vm.execute('''
controls.appointed=true
governors.GetGovernor=function() return {
    GetAssignedCity=function() return {
        GetOwner=function() return 1 end,
        GetX=function() if not controls.known then forbid() end;return 2 end,
        GetY=function() return 2 end,
        GetName=forbid,GetID=forbid
    } end
} end
''')
    ids = [row['id'] for row in run('governors', {}, True)['items'].values()]
    assert 'GOVERNOR_BUILDER:assigned' in ids
    assert 'GOVERNOR_BUILDER:assigned_city' not in ids


@pytest.mark.parametrize("kind,args,operation", [
    ("governor_appoint", {"governor":"GOVERNOR_BUILDER"},1),
    ("great_person_recruit", {"individual":"GREAT_PERSON_INDIVIDUAL_TEST"},4),
    ("great_person_pass", {"individual":"GREAT_PERSON_INDIVIDUAL_TEST"},5),
    ("great_person_patronize", {"individual":"GREAT_PERSON_INDIVIDUAL_TEST","yield":"FAITH"},6),
    ("change_government", {"government":"GOVERNMENT_CHIEFDOM"},30),
    ("found_pantheon", {"belief":"BELIEF_PANTHEON"},9),
])
def test_player_requests_match_normal_ui(engine,kind,args,operation):
    vm, run = engine
    if kind == "great_person_patronize":
        vm.execute("people.CanRecruitPerson=function() return false end;people.CanRejectPerson=function() return false end")
    assert run(kind,args)["accepted"]
    assert vm.globals().calls[1]["op"] == operation


def test_gp_request_uses_actual_timeline_id_not_assumed_index(engine):
    vm,run=engine
    run("great_person_recruit",{"individual":"GREAT_PERSON_INDIVIDUAL_TEST"})
    assert vm.globals().calls[1]["p"]["person"] == 103


def test_gp_cannot_target_an_unoffered_person(engine):
    vm,run=engine
    vm.execute("people.GetTimeline=function() return {} end")
    assert not run("great_person_recruit",{"individual":"GREAT_PERSON_INDIVIDUAL_TEST"})["accepted"]
    assert len(vm.globals().calls)==0


def test_gp_earned_own_claim_stays_on_current_board_with_recruit_and_pass(engine):
    vm, run = engine
    vm.execute('''
        people.GetTimeline=function() return {{Individual=103,Claimant=0,Cost=80,
            ActionEffectText='Public scientist ability'}} end
        people.GetPastTimeline=forbid
        PlayerConfigurations=setmetatable({}, {__index=forbid})
    ''')
    result = run("great_people", {}, True)
    rows = list(result["items"].values())
    assert result["supported"] is True
    assert rows[0]["description"] == "Public scientist ability"
    assert {row["action"]["type"] for row in rows if row["action"] is not None} == {
        "great_person_recruit", "great_person_pass"
    }
    assert all(row["Claimant"] is None and row["claimant"] is None for row in rows)
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("kind,args,operation", [
    ("great_person_recruit", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"}, 4),
    ("great_person_pass", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"}, 5),
    ("great_person_patronize", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST", "yield": "GOLD"}, 6),
])
def test_gp_own_claim_submits_only_normal_request_after_current_eligibility(engine, kind, args, operation):
    vm, run = engine
    vm.execute("people.GetTimeline=function() return {{Individual=103,Claimant=0,Cost=80}} end")
    if kind == "great_person_patronize":
        vm.execute("people.CanRecruitPerson=function() return false end;people.CanRejectPerson=function() return false end")
    assert run(kind, args)["accepted"] is True
    assert vm.globals().calls[1]["op"] == operation
    assert vm.globals().calls[1]["p"]["person"] == 103
    vm.globals().controls.can = False
    assert not run(kind, args)["accepted"]
    assert len(vm.globals().calls) == 1


def test_gp_foreign_claim_is_not_exposed_or_submitted_even_if_native_check_would_pass(engine):
    vm, run = engine
    vm.execute('''
        people.GetTimeline=function()
            return {setmetatable({Individual=103,Claimant=1},{__index=forbid})}
        end
        people.CanRecruitPerson=forbid
        people.CanRejectPerson=forbid
        people.CanPatronizePerson=forbid
        PlayerConfigurations=setmetatable({}, {__index=forbid})
    ''')
    assert len(run("great_people", {}, True)["items"]) == 0
    for kind, args in [
        ("great_person_recruit", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"}),
        ("great_person_pass", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"}),
        ("great_person_patronize", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST", "yield": "GOLD"}),
    ]:
        assert not run(kind, args)["accepted"]
    assert len(vm.globals().calls) == 0


def test_gp_claim_eligibility_is_rechecked_after_query(engine):
    vm, run = engine
    vm.execute('''
        pending_person={Individual=103,Claimant=0,Cost=80}
        people.GetTimeline=function() return {pending_person} end
    ''')
    assert any(row["action"] is not None for row in run("great_people", {}, True)["items"].values())
    vm.execute("pending_person.Claimant=1")
    assert not run("great_person_recruit", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"})["accepted"]
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("setup", ["people.GetTimeline=nil", "people.GetTimeline=function() return nil end"])
def test_gp_missing_current_board_is_explicitly_unsupported(engine, setup):
    vm, run = engine
    vm.execute(setup)
    result = run("great_people", {}, True)
    assert result["supported"] is False and len(result["items"]) == 0
    assert not run("great_person_recruit", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"})["accepted"]


def test_governor_promotion_requires_own_appointment(engine):
    vm, run=engine
    args={"governor":"GOVERNOR_BUILDER","promotion":"GOVERNOR_PROMOTION_TOOLS"}
    assert not run("governor_promote",args)["accepted"]
    vm.globals().controls.appointed=True
    assert run("governor_promote",args)["accepted"]
    assert vm.globals().calls[1]["p"]["promotion"]==2


@pytest.mark.parametrize("state", ["visible", "known"])
def test_foreign_governor_target_checked_before_city_lookup(engine,state):
    vm, run=engine
    vm.globals().controls.appointed=True
    vm.globals().controls[state]=False
    result=run("governor_assign",{"governor":"GOVERNOR_BUILDER","owner_id":1,"city_id":55,"x":2,"y":2})
    assert not result["accepted"]
    assert vm.globals().controls.foreign_reads==0


def test_governor_assign_foreign_visible_city(engine):
    vm,run=engine
    vm.globals().controls.appointed=True
    assert run("governor_assign",{"governor":"GOVERNOR_BUILDER","owner_id":1,"city_id":55,"x":2,"y":2})["accepted"]
    assert vm.globals().calls[1]["p"]["owner"]==1


def test_policies_submit_full_typed_slot_map(engine):
    vm,run=engine
    slots=[{"slot":0,"policy":"POLICY_MILITARY"},{"slot":1,"policy":"POLICY_ECONOMIC"}]
    assert run("set_policies",{"slots":slots})["accepted"]
    p=vm.globals().calls[1]["p"]
    assert p["add"][0]==105 and p["add"][1]==106
    assert list(p["clear"].values())==[0,1]


_LATE_DARK_POLICIES = (
    "POLICY_LETTERS_OF_MARQUE", "POLICY_ROBBER_BARONS", "POLICY_ROGUE_STATE",
    "POLICY_FLOWER_POWER", "POLICY_CYBER_WARFARE", "POLICY_AUTOMATED_WORKFORCE",
)


@pytest.mark.parametrize("policy", _LATE_DARK_POLICIES)
def test_gs_rejects_unlocked_but_not_slottable_dark_policy_in_query_and_action(engine, policy):
    vm, run = engine
    # Matches live Classical-era evidence: IsPolicyUnlocked says true, while
    # the GS GovernmentScreen's CanPolicyBeSlotted is the actual menu gate.
    # The slot itself is deliberately legal, so a slot-type check cannot hide
    # the defect this regression is intended to catch.
    vm.globals().late_policy = policy
    vm.execute('''
GameInfo.Policies=defs('PolicyType',{
    {PolicyType='POLICY_MILITARY',Index=0,Hash=105,GovernmentSlotType='SLOT_MILITARY'},
    {PolicyType=late_policy,Index=1,Hash=200,GovernmentSlotType='SLOT_WILDCARD'}})
GameInfo.GovernmentSlots[1]={GovernmentSlotType='SLOT_WILDCARD',Index=1}
culture.IsPolicyUnlocked=function() return true end
culture.CanPolicyBeSlotted=function(self,hash) return hash~=200 end
Game.GetEras=forbid
''')
    result = run("government", {}, True)
    assert result["supported"] is True
    assert policy not in {row["id"] for row in result["items"].values()}
    slots = [{"slot": 0, "policy": "POLICY_MILITARY"}, {"slot": 1, "policy": policy}]
    assert not run("set_policies", {"slots": slots})["accepted"]
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("gate,answer", [
    ("IsPolicyBanned", "true"), ("CanPolicyBeSlotted", "false"), ("IsPolicyObsolete", "true"),
    ("IsPolicyBanned", "nil"), ("CanPolicyBeSlotted", "nil"), ("IsPolicyObsolete", "nil"),
])
def test_gs_policy_menu_checks_bans_slottability_and_obsolescence(engine, gate, answer):
    vm, run = engine
    vm.execute("culture." + gate + "=function() return " + answer + " end")
    result = run("government", {}, True)
    assert not any(row["id"].startswith("POLICY_") for row in result["items"].values())
    slots = [{"slot": 0, "policy": "POLICY_MILITARY"}, {"slot": 1, "policy": "POLICY_ECONOMIC"}]
    assert not run("set_policies", {"slots": slots})["accepted"]
    assert len(vm.globals().calls) == 0


def test_gs_uses_its_menu_predicate_without_extra_legacy_unlock_gate(engine):
    vm, run = engine
    vm.execute("culture.IsPolicyUnlocked=forbid; Game.GetEras=forbid")
    result = run("government", {}, True)
    assert {row["id"] for row in result["items"].values()} >= {"POLICY_MILITARY", "POLICY_ECONOMIC"}
    slots = [{"slot": 0, "policy": "POLICY_MILITARY"}, {"slot": 1, "policy": "POLICY_ECONOMIC"}]
    assert run("set_policies", {"slots": slots})["accepted"]


@pytest.mark.parametrize("rules", ["RULESET_STANDARD", "RULESET_EXPANSION_1"])
def test_base_and_rise_fall_keep_their_original_policy_predicate(engine, rules):
    vm, run = engine
    vm.globals().controls.rules = rules
    vm.execute("culture.IsPolicyBanned=forbid; culture.CanPolicyBeSlotted=forbid")
    slots = [{"slot": 0, "policy": "POLICY_MILITARY"}, {"slot": 1, "policy": "POLICY_ECONOMIC"}]
    assert run("set_policies", {"slots": slots})["accepted"]
    vm.execute("culture.IsPolicyUnlocked=function(self,hash) return hash~=106 end")
    result = run("government", {}, True)
    assert "POLICY_ECONOMIC" not in {row["id"] for row in result["items"].values()}
    assert not run("set_policies", {"slots": slots})["accepted"]


@pytest.mark.parametrize("change", [
    "culture.IsPolicyBanned=nil", "culture.CanPolicyBeSlotted=nil", "culture.IsPolicyObsolete=nil",
    "GameConfiguration.GetValue=nil", "GameConfiguration=nil", "controls.rules='RULESET_UNKNOWN'",
])
def test_unknown_or_missing_policy_menu_capability_fails_closed(engine, change):
    vm, run = engine
    vm.execute(change)
    result = run("government", {}, True)
    assert result["supported"] is False and len(result["items"]) == 0
    slots = [{"slot": 0, "policy": "POLICY_MILITARY"}, {"slot": 1, "policy": "POLICY_ECONOMIC"}]
    assert not run("set_policies", {"slots": slots})["accepted"]
    assert len(vm.globals().calls) == 0


def test_policy_slottability_is_rechecked_at_submission(engine):
    vm, run = engine
    assert "POLICY_ECONOMIC" in {row["id"] for row in run("government", {}, True)["items"].values()}
    vm.execute("culture.CanPolicyBeSlotted=function(self,hash) return hash~=106 end")
    slots = [{"slot": 0, "policy": "POLICY_MILITARY"}, {"slot": 1, "policy": "POLICY_ECONOMIC"}]
    assert not run("set_policies", {"slots": slots})["accepted"]
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("slots", [[], [{"slot":0,"policy":"POLICY_MILITARY"}],
    [{"slot":0,"policy":"POLICY_MILITARY"},{"slot":0,"policy":"POLICY_ECONOMIC"}],
    [{"slot":1,"policy":"POLICY_MILITARY"},{"slot":0,"policy":"POLICY_ECONOMIC"}]])
def test_invalid_policy_assignments_do_not_submit(engine,slots):
    vm,run=engine
    assert not run("set_policies",{"slots":slots})["accepted"]
    assert len(vm.globals().calls)==0


def test_policy_unlock_and_dedication_batches(engine):
    vm,run=engine
    vm.globals().controls.policy_cost=100
    assert run("unlock_policies",{})["accepted"]
    assert not run("choose_dedications",{"dedications":["COMMEMORATION_SCIENCE"]})["accepted"]
    assert run("choose_dedications",{"dedications":["COMMEMORATION_SCIENCE","COMMEMORATION_CULTURE"]})["accepted"]
    assert len(vm.globals().calls)==3
    assert vm.globals().calls[2]["p"]["commemoration"]==0
    assert vm.globals().calls[3]["p"]["commemoration"]==1


def test_found_religion_preserves_unicode_name_and_belief_requests(engine):
    vm,run=engine
    vm.globals().controls.has_prophet=False  # The prophet was already activated/consumed.
    assert run("found_religion",{"religion":"RELIGION_CUSTOM","name":"测试宗教","beliefs":["BELIEF_FEED","BELIEF_TITHE"]})["accepted"]
    assert len(vm.globals().calls)==3
    assert vm.globals().calls[1]["p"]["name"]=="测试宗教"
    assert vm.globals().calls[2]["p"]["belief"]==110


def test_found_religion_requires_follower_first_before_any_request(engine):
    vm,run=engine
    assert not run('found_religion',{'religion':'RELIGION_CUSTOM','name':'宗教',
        'beliefs':['BELIEF_TITHE','BELIEF_FEED']})['accepted']
    assert len(vm.globals().calls)==0


def test_interrupted_religion_founding_only_offers_and_accepts_first_follower(engine):
    vm,run=engine
    vm.globals().controls.founded=1
    vm.globals().controls.can=False  # No unrelated pantheon selection.
    rows={row['id']:row for row in run('religion',{},True)['items'].values()}
    assert rows['first_belief_class']['value']=='BELIEF_CLASS_FOLLOWER'
    assert 'BELIEF_FEED' in rows and 'BELIEF_TITHE' not in rows
    assert not run('add_belief',{'belief':'BELIEF_TITHE'})['accepted']
    assert len(vm.globals().calls)==0
    assert run('add_belief',{'belief':'BELIEF_FEED'})['accepted']
    vm.globals().controls.equipped=1
    assert run('add_belief',{'belief':'BELIEF_TITHE'})['accepted']


def test_taken_belief_and_wrong_class_rejected(engine):
    vm,run=engine
    assert not run("found_pantheon",{"belief":"BELIEF_FEED"})["accepted"]
    vm.globals().controls.belief_taken=True
    assert not run("found_pantheon",{"belief":"BELIEF_PANTHEON"})["accepted"]


def test_city_build_and_purchase_keep_formation_parameters_distinct(engine):
    vm,run=engine
    assert run("city_build",{"city_id":42,"item":"UNIT_WARRIOR","formation":"CORPS","append":True})["accepted"]
    assert vm.globals().calls[1]["p"]["formation"]==1
    assert vm.globals().calls[1]["p"]["insert"]==2
    assert run("city_purchase",{"city_id":42,"item":"UNIT_WARRIOR","formation":"ARMY","yield":"GOLD"})["accepted"]
    assert vm.globals().calls[2]["p"]["formation"]==2
    assert vm.globals().calls[2]["p"]["yield"]==2


def test_unplaced_district_requires_target(engine):
    _,run=engine
    args={"city_id":42,"item":"DISTRICT_CAMPUS","formation":"STANDARD","append":False}
    assert not run("city_build",args)["accepted"]
    assert run("city_build_at",{**args,"x":2,"y":2})["accepted"]


@pytest.mark.parametrize("kind,extra",[
    ("city_build_at",{"item":"BUILDING_WONDER","formation":"STANDARD","append":False}),
    ("city_purchase_at",{"item":"DISTRICT_CAMPUS","formation":"STANDARD","yield":"GOLD"}),
    ("city_purchase_plot",{}),("city_manage_citizen",{}),("city_swap_tile",{})])
def test_city_targets_need_current_visibility(engine,kind,extra):
    vm,run=engine
    vm.globals().controls.visible=False
    assert not run(kind,{"city_id":42,"x":2,"y":2,**extra})["accepted"]
    assert vm.globals().controls.plot_reads==0
    assert len(vm.globals().calls)==0


def test_city_ownership_gate_precedes_id_and_payload(engine):
    vm,run=engine
    vm.globals().controls.owner=1
    assert not run("city_queue_remove",{"city_id":42,"index":0})["accepted"]
    assert vm.globals().controls.city_reads==0


def test_focus_is_explicit_and_queue_bounds_checked(engine):
    vm,run=engine
    assert run("city_set_focus",{"city_id":42,"yield":"YIELD_GOLD","focus":"disfavored"})["accepted"]
    assert vm.globals().calls[1]["p"]["value"]==0
    assert vm.globals().calls[2]["p"]["value"]==1
    assert not run("city_queue_remove",{"city_id":42,"index":2})["accepted"]
    assert run("city_queue_move",{"city_id":42,"index":1,"destination":0})["accepted"]
    assert vm.globals().calls[3]["p"]["source"]==1


@pytest.mark.parametrize("kind,args",[("governors",{}),("great_people",{}),("government",{}),
    ("religion",{}),("dedications",{}),("city_production",{"city_id":42}),
    ("city_placement",{"city_id":42,"item":"DISTRICT_CAMPUS"}),
    ("city_tiles",{"city_id":42}),("city_queue",{"city_id":42}),("loyalty_choices",{})])
def test_all_discovery_queries_return_valid_action_payloads(engine,kind,args):
    _,run=engine
    result=run(kind,args,True)
    assert result["supported"]
    assert len(result["items"])>0
    for row in result["items"].values():
        assert row["scope"]=="self" and row["owner_id"]==0
        if row["action"]:
            action=dict(row["action"].items())
            action_type=action.pop("type")
            validate(action,ACTIONS[action_type].fields)


def test_tile_discovery_excludes_fog_counts_and_targets(engine):
    vm,run=engine
    result=run("city_tiles",{"city_id":42},True)
    rows=list(result["items"].values())
    assert not any(':9:2' in r['id'] for r in rows)
    assert not any(r['value'] in (77,88,99) for r in rows)


def test_placement_checks_visibility_before_ownership_or_legality(engine):
    vm,run=engine
    result=run("city_placement",{"city_id":42,"item":"DISTRICT_CAMPUS"},True)
    assert len([r for r in result['items'].values() if r['action']])==3
    assert vm.globals().controls.plot_reads==1


def test_missing_governor_api_is_explicitly_unsupported(engine):
    vm,run=engine
    vm.execute('player.GetGovernors=nil')
    result=run('governors',{},True)
    assert result['supported'] is False and len(result['items'])==0


@pytest.mark.parametrize("kind,args",[
    ("city_build",{"city_id":42,"item":"PROJECT_REPAIR","formation":"CORPS","append":False}),
    ("city_purchase",{"city_id":42,"item":"BUILDING_MONUMENT","formation":"ARMY","yield":"GOLD"})])
def test_nonunit_formation_rejects_without_lua_syntax_error(engine,kind,args):
    _,run=engine
    assert not run(kind,args)['accepted']


@pytest.mark.parametrize('state,value',[('civic_completed',False),('government_changed',True)])
def test_government_respects_ui_change_window(engine,state,value):
    vm,run=engine
    vm.globals().controls[state]=value
    assert not run('change_government',{'government':'GOVERNMENT_CHIEFDOM'})['accepted']
    result=run('government',{},True)
    assert not any(r['action'] and r['action']['type']=='change_government' for r in result['items'].values())


def test_ordinary_government_and_governor_considered_actions(engine):
    vm,run=engine
    assert run('government_keep',{})['accepted']
    assert run('governor_defer',{})['accepted']
    assert vm.globals().calls[1]['p']['value'] is True
    assert vm.globals().calls[2]['p']['value'] is True


def test_unlock_requires_own_funds(engine):
    vm,run=engine
    vm.globals().controls.policy_cost=2000
    assert not run('unlock_policies',{})['accepted']
    assert len(vm.globals().calls)==0


def test_only_pending_loyalty_city_can_be_rejected(engine):
    vm,run=engine
    vm.globals().controls.rebelled=False
    assert not run('city_loyalty_choice',{'city_id':42,'choice':'reject'})['accepted']
    vm.globals().controls.rebelled=True
    assert run('city_loyalty_choice',{'city_id':42,'choice':'reject'})['accepted']
    assert vm.globals().calls[1]['op']==25
    assert vm.globals().calls[1]['p']['flags']==2


def test_add_earned_belief_to_own_religion(engine):
    vm,run=engine
    vm.globals().controls.founded=1
    assert run('add_belief',{'belief':'BELIEF_FEED'})['accepted']
    assert vm.globals().calls[1]['p']['belief']==110


def test_fully_equipped_religion_hides_unavailable_selection_pool(engine):
    vm,run=engine
    vm.globals().controls.founded=1
    vm.globals().controls.equipped=2
    vm.globals().controls.can=False
    assert not run('add_belief',{'belief':'BELIEF_FEED'})['accepted']
    result=run('religion',{},True)
    assert not any(r['id'].startswith('BELIEF_') for r in result['items'].values())


def test_purchased_only_building_can_be_repaired_by_production(engine):
    vm,run=engine
    vm.execute("GameInfo.Buildings.BUILDING_MONUMENT.MustPurchase=true")
    args={'city_id':42,'item':'BUILDING_MONUMENT','formation':'STANDARD','append':False}
    assert not run('city_build',args)['accepted']
    vm.globals().controls.pillaged=True
    assert run('city_build',args)['accepted']
    result=run('city_production',{'city_id':42},True)
    assert any(r['id']=='BUILDING_MONUMENT:build' for r in result['items'].values())


def test_existing_wonder_can_be_repaired_without_replacement(engine):
    vm,run=engine
    vm.globals().controls.built=True
    assert run('city_build',{'city_id':42,'item':'BUILDING_WONDER','formation':'STANDARD','append':False})['accepted']


def test_city_rename_is_ordinary_own_request(engine):
    vm,run=engine
    assert run('city_rename',{'city_id':42,'name':'新城名'})['accepted']
    assert vm.globals().calls[1]['op']==26
    assert vm.globals().calls[1]['p']['name']=='新城名'
