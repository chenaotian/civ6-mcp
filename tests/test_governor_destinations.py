"""Stock governor menu gates in Lua, with fog/unknown-city getter traps."""
import pytest
from lupa import LuaRuntime, lua_type

from civ6_fair_mcp.extensions.base import validate
from civ6_fair_mcp.extensions.governor_destinations import ACTIONS, QUERIES
from civ6_fair_mcp.inspection_policy import public_inspection


GOVERNOR = "GOVERNOR_THE_AMBASSADOR"
CATEGORY = "governor_city_state_destinations"
ACTION = "governor_assign_city_state"
BOOT = r'''
calls={};reads={names=0,cities=0,can_assign=0}
state={appointed=true,citystate=true,met=true,receiver=true,allowed=true,
    strategic=true,neutralized=0,congress=false,current=false}
function forbidden() error('hidden data read') end
function members(values)
    local i=0;return function() i=i+1;if values[i] then return i,values[i] end end
end
row={GovernorType='GOVERNOR_THE_AMBASSADOR',Hash=-1234,Index=2}
setmetatable(row,{__index=function(_,key)
    if key=='Name' or key=='Description' then error('governor identity not needed') end
end})
GameInfo={Governors={GOVERNOR_THE_AMBASSADOR=row}}
governor={IsGovernCityState=function() return state.citystate end,
    GetID=function() return 27 end,GetNeutralizedTurns=function() return state.neutralized end,
    GetTurnsToEstablish=function() return 5 end}
city={GetOwner=function() return 6 end,GetID=function() return 196610 end,
    GetName=function() reads.names=reads.names+1;return 'LOC_NALANDA' end,
    GetX=forbidden,GetY=forbidden,GetCulturalIdentity=forbidden,
    GetPopulation=forbidden,GetAssignedGovernor=forbidden}
governors={HasGovernor=function(self,hash) assert(hash==-1234);return state.appointed end,
    GetGovernor=function(self,hash) assert(state.appointed and hash==-1234);return governor end,
    GetAssignedGovernor=function(self,c) assert(c==city);if state.current then return governor end end,
    CanAssignGovernor=function(self,hash,c,results)
        assert(hash==-1234 and c==city and results==true)
        reads.can_assign=reads.can_assign+1
        return state.allowed,{failure_reasons=setmetatable({},{__index=forbidden})}
    end}
dip={HasMet=function(self,id) return id==4 or (id==6 and state.met) end}
player={GetGovernors=function() return governors end,GetDiplomacy=function() return dip end,
    GetCities=forbidden}
other={GetInfluence=function() assert(state.met);return {
    CanReceiveInfluence=function() return state.receiver end} end,
    GetCities=function() assert(state.met and state.receiver);reads.cities=reads.cities+1
        return {Members=function() return members({city}) end} end,
    GetName=forbidden,GetConfig=forbidden,IsMajor=forbidden}
nonreceiver={GetInfluence=function() return {CanReceiveInfluence=function() return false end} end,
    GetCities=forbidden}
Players=setmetatable({[0]=player,[4]=nonreceiver,[6]=other},{__index=forbidden})
PlayerManager={GetAliveMinorIDs=function() return {3,4,6} end,
    GetAliveMajors=forbidden,GetAliveMajorIDs=forbidden}
Game={IsAllowStrategicCommands=function(id) assert(id==0);return state.strategic end,
    GetWorldCongress=function() return {IsInSession=function() return state.congress end} end}
Locale={Lookup=function(key) if key=='LOC_NALANDA' then return '那烂陀' end;error('unexpected text') end}
UI={RequestPlayerOperation=function(id,op,p)
    assert(id==0 and op==47);calls[#calls+1]=p
end}
PlayerOperations={ASSIGN_GOVERNOR=47,PARAM_GOVERNOR_TYPE='governor',
    PARAM_PLAYER_ONE='owner',PARAM_CITY_DEST='city'}
Map=setmetatable({},{__index=forbidden})
vis=setmetatable({},{__index=forbidden})
'''


def execute(mutation="", *, action=False, args=None):
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute(BOOT + "\n" + mutation)
    spec = ACTIONS[ACTION] if action else QUERIES[CATEGORY]
    args = args or ({"governor": GOVERNOR, "owner_id": 6, "city_id": 196610}
                    if action else {"governor": GOVERNOR})
    validate(args, spec.fields)
    body = spec.body(args)
    code = "local me=0;local player=Players[me];local out={items={},accepted=false,supported=false}\n"
    code += "local function array(x) return x end\n"
    code += "local function attempt(fn,...) fn(...);out.accepted=true end\n"
    code += "local function run()\n" + body + "\nend\nrun()\nreturn out"
    return vm, vm.execute(code)


def python_value(value):
    if lua_type(value) != "table":
        return value
    return {key: python_value(item) for key, item in value.items()}


def records(out):
    return [python_value(row) for row in out["items"].values()]


def test_fogged_met_city_state_menu_has_name_duration_and_exact_action_without_map_reads():
    vm, out = execute()
    assert out["supported"] is True
    items = records(out)
    assert len(items) == 2
    assert items[0]["name"] == "那烂陀"
    assert items[0]["value"] is True
    assert items[0]["action"] == {"type": ACTION, "governor": GOVERNOR, "owner_id": 6, "city_id": 196610}
    assert items[1]["id"].endswith(":establish_turns") and items[1]["value"] == 5
    assert vm.globals().reads.names == 1 and len(vm.globals().calls) == 0
    raw = {"ok": True, "session": "governor-menu-session-1234567890", "player_id": 0,
           "turn": 70, "active_turn": True, "category": CATEGORY, "supported": True, "items": items}
    public = public_inspection(raw, CATEGORY)["items"]
    assert set(public[0]) == {"id", "name", "value", "action"}
    assert set(public[1]) == {"id", "value"}


def test_action_uses_stock_index_owner_city_parameters_without_reading_name_or_coordinates():
    vm, out = execute(action=True)
    assert out["accepted"] is True
    assert python_value(vm.globals().calls[1]) == {"governor": 2, "owner": 6, "city": 196610}
    assert vm.globals().reads.names == 0


@pytest.mark.parametrize("mutation", [
    "state.appointed=false", "state.citystate=false", "state.met=false",
    "state.receiver=false", "PlayerManager.GetAliveMinorIDs=function() return {3,4} end",
])
def test_excluded_targets_are_not_read_or_offered_and_actions_reject(mutation):
    vm, out = execute(mutation)
    assert out["supported"] is True and records(out) == []
    assert vm.globals().reads.names == 0
    vm, out = execute(mutation, action=True)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


def test_unknown_secret_governor_does_not_read_identity_or_destinations():
    mutation = """
GameInfo.Governors.GOVERNOR_SECRET=setmetatable({GovernorType='GOVERNOR_SECRET',Hash=-1234,Index=9},
    {__index=forbidden})
state.appointed=false
PlayerManager.GetAliveMinorIDs=forbidden
"""
    vm, out = execute(mutation, args={"governor": "GOVERNOR_SECRET"})
    assert out["supported"] is True and records(out) == []
    assert vm.globals().reads.names == 0 and vm.globals().reads.cities == 0


@pytest.mark.parametrize("mutation", [
    "state.allowed=false", "state.strategic=false", "state.neutralized=2", "state.congress=true",
    "Game.IsAllowStrategicCommands=nil", "Game.GetWorldCongress=nil",
    "Game.GetWorldCongress=function() return nil end",
])
def test_disabled_normal_menu_keeps_public_name_without_executable_action(mutation):
    _, out = execute(mutation)
    items = records(out)
    assert out["supported"] is True and items[0]["name"] == "那烂陀"
    assert items[0]["value"] is False and "action" not in items[0]
    vm, out = execute(mutation, action=True)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize("mutation", [
    "PlayerManager.GetAliveMinorIDs=nil", "PlayerManager.GetAliveMinorIDs=function() return false end",
    "governors.CanAssignGovernor=nil", "governors.GetAssignedGovernor=nil",
    "governor.IsGovernCityState=nil", "dip.HasMet=nil", "other.GetInfluence=nil",
    "other.GetCities=nil", "other.GetCities=function() error('unavailable') end",
    "governors.CanAssignGovernor=function() return nil end",
    "governors.CanAssignGovernor=function() error('unavailable') end",
])
def test_missing_menu_proof_never_claims_complete_or_submits(mutation):
    vm, out = execute(mutation)
    assert out["supported"] is False and records(out) == []
    assert vm.globals().reads.names == 0
    vm, out = execute(mutation, action=True)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize("mutation", [
    "governor.GetTurnsToEstablish=nil",
    "governor.GetTurnsToEstablish=function() error('missing duration') end",
    "governor.GetTurnsToEstablish=function() return -1 end",
    "governor.GetTurnsToEstablish=function() return '5' end",
])
def test_missing_optional_duration_does_not_invent_zero_or_drop_usable_menu(mutation):
    _, out = execute(mutation)
    assert out["supported"] is True
    items = records(out)
    assert len(items) == 1 and items[0]["action"]["type"] == ACTION


@pytest.mark.parametrize("args", [
    {"governor": GOVERNOR, "owner_id": 0, "city_id": 196610},
    {"governor": GOVERNOR, "owner_id": 3, "city_id": 196610},
    {"governor": GOVERNOR, "owner_id": 22, "city_id": 196610},
    {"governor": GOVERNOR, "owner_id": 6, "city_id": 999},
])
def test_forged_destination_cannot_bypass_current_menu(args):
    vm, out = execute(action=True, args=args)
    assert out["accepted"] is False and len(vm.globals().calls) == 0
    assert vm.globals().reads.names == 0


def test_oversized_menu_is_unavailable_without_partial_disclosure():
    mutation = """
local values={};for i=1,1025 do values[i]=city end
other.GetCities=function() return {Members=function() return members(values) end} end
"""
    vm, out = execute(mutation)
    assert out["supported"] is False and records(out) == []
    assert vm.globals().reads.names == 0


def test_city_name_failure_does_not_return_a_partially_complete_menu():
    _, out = execute("city.GetName=function() error('missing name') end")
    assert out["supported"] is False and records(out) == []


def test_fogged_current_assignment_has_readonly_name_city_id_and_owner():
    mutation = "state.current=true;governors.CanAssignGovernor=forbidden"
    vm, out = execute(mutation)
    assert out["supported"] is True
    items = records(out)
    assert [row["id"] for row in items] == ["current_assignment:city", "current_assignment:owner_id"]
    assert items[0]["name"] == "那烂陀" and items[0]["value"] == 196610
    assert items[1]["value"] == 6
    assert all("action" not in row for row in items)
    assert vm.globals().reads.can_assign == 0 and vm.globals().reads.names == 1
    raw = {"ok": True, "session": "governor-menu-session-1234567890", "player_id": 0,
           "turn": 79, "active_turn": True, "category": CATEGORY, "supported": True, "items": items}
    assert public_inspection(raw, CATEGORY)["items"] == [
        {"id": "current_assignment:city", "name": "那烂陀", "value": 196610},
        {"id": "current_assignment:owner_id", "value": 6},
    ]
    vm, out = execute(mutation, action=True)
    assert out["accepted"] is False and len(vm.globals().calls) == 0
    assert vm.globals().reads.names == 0


@pytest.mark.parametrize("mutation", [
    "state.appointed=false", "state.citystate=false", "state.met=false", "state.receiver=false",
    "PlayerManager.GetAliveMinorIDs=function() return {3,4} end",
])
def test_current_assignment_still_requires_own_known_city_state_menu_membership(mutation):
    vm, out = execute("state.current=true;" + mutation)
    assert out["supported"] is True and records(out) == []
    assert vm.globals().reads.names == 0


@pytest.mark.parametrize("mutation", [
    "state.allowed=false", "state.neutralized=2", "state.strategic=false", "state.congress=true",
])
def test_current_assignment_summary_is_readonly_even_while_commands_disabled(mutation):
    _, out = execute("state.current=true;" + mutation)
    assert out["supported"] is True
    assert [row["id"] for row in records(out)] == ["current_assignment:city", "current_assignment:owner_id"]
    assert all("action" not in row for row in records(out))


def test_inconsistent_multiple_current_assignments_do_not_produce_ambiguous_summary():
    mutation = """
state.current=true
other.GetCities=function() return {Members=function() return members({city,city}) end} end
"""
    vm, out = execute(mutation)
    assert out["supported"] is False and records(out) == []
    assert vm.globals().reads.names == 0
