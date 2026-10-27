"""Exercise authored Lua, including hidden counterpart getter traps and ballots."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.diplomacy_actions import ACTIONS, QUERIES, DIPLOMACY_HOOK


ENGINE = r'''
me=0; turn=20; session='test'
out={items={},supported=false,accepted=false}
calls={}; known={[0]=true,[1]=true}; reads=0
local function array(v) return v end
local function record(...) table.insert(calls,{...}) end
local function attempt(fn,...) fn(...);out.accepted=true end
Locale={Lookup=function(s) return s end}
GameConfiguration={IsPaused=function() return false end}
local diplo={HasMet=function(_,id) return known[id]==true end,
    IsDiplomaticActionValid=function() return true end,
    CanDeclareWarOn=function() return true end,CanMakePeaceWith=function() return true end}
local influence={CanGiveInfluence=function() return true end,GetTokensToGive=function() return 2 end,
    CanGiveTokensToPlayer=function() return true end,CanLevyMilitary=function() return true end,
    GetLevyMilitaryCost=function() return 40 end}
local function empty_members() return ipairs({}) end
local units={Members=empty_members}
local cities={Members=empty_members}
local resources={IsResourceVisible=function(_,hash) return hash~=999 end}
player={GetDiplomacy=function() return diplo end,GetInfluence=function() return influence end,
    IsMajor=function() return true end,GetFavor=function() return favor end,
    GetUnits=function() return units end,GetCities=function() return cities end,
    GetResources=function() return resources end}
local other={IsMajor=function() return true end,IsAlive=function() return true end,IsBarbarian=function() return false end}
Players=setmetatable({[0]=player,[1]=other},{__index=function() reads=reads+1;error('HIDDEN PLAYER') end})
PlayerConfigurations=setmetatable({[0]={GetCivilizationShortDescription=function() return 'self' end},
    [1]={GetCivilizationShortDescription=function() return 'known' end}},{__index=function() reads=reads+1;error('HIDDEN IDENTITY') end})
DiplomacyManager={RequestSession=record,FindOpenSessionID=function() return 5 end,
    IsSessionIDOpen=function() return true end,GetSessionInfo=function() return {FromPlayer=1,ToPlayer=0} end,
    AddResponse=record,AddStatement=record,CloseSession=record}
UI={RequestPlayerOperation=record,RequestAction=record}
PlayerOperations=setmetatable({},{__index=function(t,k) local value=1;for _ in pairs(t) do value=value+1 end;rawset(t,k,value);return value end})
ActionTypes={ACTION_ENDTURN=9}
GameInfo={DiplomaticActions=setmetatable({},{__index=function(_,k) return {Name=k} end}),
    Resources={[1]={Hash=100,ResourceType='RESOURCE_IRON',ResourceClassType='RESOURCECLASS_STRATEGIC',Name='Iron'},
        [2]={Hash=999,ResourceType='RESOURCE_URANIUM',ResourceClassType='RESOURCECLASS_STRATEGIC',Name='SECRET URANIUM'}},
    Alliances={},Technologies={},VotingBlockers={},EmergencyAlliances={[7]={Name='Emergency'}}}
DB={MakeHash=function(s) if s=='TURNSEG_WORLDCONGRESS_1' then return 10 elseif s=='TURNSEG_WORLDCONGRESS_2' then return 11 end
    local h=0;for i=1,#s do h=(h*31+s:byte(i))%2147483647 end;return h end}
segment=10; favor=100
resolutions={{Type='WC_RES_TEST',TargetType='PlayerType',PossibleTargets={'0','1','9'}}}
proposed={Proposals={}}
costs={[0]=0,[1]=10,[2]=30,[3]=60}
local wc={GetResolutions=function(_,id) assert(id==0);return resolutions end,
    GetProposals=function(_,id) assert(id==0);return proposed end,
    GetEmergencies=function(_,id) assert(id==0);return proposed end,
    GetVotesandFavorCost=function(_,id) assert(id==0);return costs end}
Game={GetCurrentTurnSegment=function() return segment end,GetWorldCongress=function() return wc end}
GameInfo.Resolutions={WC_RES_TEST={ResolutionType='WC_RES_TEST',Index=0,Hash=123,Name='Resolution',
    Effect1Description='Buff',Effect2Description='Nerf'}}
DealDirection={OUTGOING=0,INCOMING=1}
DealItemTypes={GOLD=1,FAVOR=2,RESOURCES=3,AGREEMENTS=4,CITIES=5,GREATWORK=6,CAPTIVE=7}
DealAgreementTypes={OPEN_BORDERS=1,MAKE_PEACE=2,ALLIANCE=3,DEFENSIVE_PACT=4,RESEARCH_AGREEMENT=5}
DealProposalAction={ACCEPTED=1,REJECTED=2,PROPOSED=3}
_CIV6FAIR_V1={deal_roles_v2={[5]={session='test',sid=5,player=0,other=1,initiator=1,
    action=3,active=true,observed=true}}}
possible={{ForType=1,MaxAmount=10,Duration=0,IsValid=true},{ForType=2,MaxAmount=9000,Duration=0,IsValid=true}}
local function item(id,kind,value,amount)
    return {GetID=function() return id end,GetType=function() return kind end,
        GetFromPlayerID=function() return 1 end,GetValueType=function() return value end,
        GetSubType=function() return 0 end,GetAmount=function() return amount end,
        GetDuration=function() return 0 end,IsLocked=function() return false end}
end
dealItems={item(4,1,0,25)}
function make_item(id,kind,value,amount) return item(id,kind,value,amount) end
local function iteritems()
    local i=0;return function() i=i+1;return dealItems[i] end
end
draft={Items=function() return iteritems() end,GetItemCount=function() return #dealItems end,
    IsValid=function() return true end,IsGift=function() return false end,RemoveItemByID=record,Validate=function() end}
DealManager={GetWorkingDeal=function() return draft end,HasPendingDeal=function() return false end,
    GetPossibleDealItems=function() return possible end,SendWorkingDeal=record,ClearWorkingDeal=record,
    CopyIncomingToOutgoingWorkingDeal=record,AreWorkingDealsEqual=function() return true end}
'''

CAPTURED_STATEMENT = '''
_CIV6FAIR_V1={diplomacy_statements={[5]={from=1,to=0,other=1,session='test',signature='STATEMENT_1',
    StatementType=100,StatementSubType=0}}}
PlayerConfigurations[1].GetLeaderTypeName=function() return 'LEADER_TEST' end
DiplomacyManager.GetKeyName=function(id) return id==100 and 'DECLARE_FRIEND' or 'NONE' end
DiplomacyManager.FindTextKey=function() return 'Public friendship request' end
choices={{Key='CHOICE_POSITIVE',Text='Accept'},{Key='CHOICE_EXIT',Text='Exit'}}
DB.Query=function(sql,...)
    if sql:find('FROM DiplomacyStatements') then return {{StatementText='LOC_REQUEST',Selections='CHOICES'}} end
    return choices
end
'''


def execute(name, params=None, *, query=False, setup=""):
    vm = LuaRuntime(unpack_returned_tuples=True)
    spec = (QUERIES if query else ACTIONS)[name]
    params = params or {}
    validate(params, spec.fields)
    payload = dict(params)
    if not query:
        payload["type"] = name
    code = ENGINE + "\n" + LUA_HELPERS + "\n" + setup + "\nlocal function run()\n" + spec.body(payload) + "\nend\nrun()\nreturn out"
    return vm, vm.execute(code)


def sample(schema):
    if isinstance(schema, dict):
        return {k: sample(v) for k, v in schema.items()}
    if isinstance(schema, list):
        return []
    if schema.startswith("enum:"):
        return schema[5:].split("|")[0]
    if schema.startswith("identifier:"):
        return schema[11:].split("|")[0]+"TEST"
    if schema == "bool":
        return True
    if schema in {"text_identifier", "text"}:
        return "TEST"
    return 1


@pytest.mark.parametrize("name,spec", list(ACTIONS.items())+list(QUERIES.items()))
def test_every_generated_template_compiles_as_lua(name, spec):
    values = sample(spec.fields)
    values["type"] = name
    code = "return function()\n"+LUA_HELPERS+spec.body(values)+"\nend"
    LuaRuntime().execute(code)


@pytest.mark.parametrize("kind", ["diplomacy_actions", "deal_state"])
def test_unknown_counterpart_is_filtered_before_player_getter(kind):
    vm, out = execute(kind, {"target_player": 9}, query=True)
    assert vm.globals().reads == 0
    assert len(out["items"]) == 0
    assert out["supported"] is False


def test_diplomatic_action_rechecks_validity_and_met_gate():
    _, out = execute("diplomacy_statement", {"target_player": 1, "statement": "delegation"})
    assert out["accepted"] is True
    vm, out = execute("diplomacy_statement", {"target_player": 9, "statement": "surprise_war"})
    assert out["accepted"] is False and len(vm.globals().calls) == 0
    assert vm.globals().reads == 0


CITY_STATE_SETUP = '''
citystate_flags={major=false,alive=true,barbarian=false,free=false,receives=true,
    at_war=false,can_war=true,can_peace=true,military=true}
citystate_reads={identity=0,influence=0,war=0,peace=0}
local minor=Players[1]
minor.GetID=function() return 1 end
minor.IsMajor=function() return citystate_flags.major end
minor.IsAlive=function() return citystate_flags.alive end
minor.IsBarbarian=function() return citystate_flags.barbarian end
minor.IsFreeCities=function() return citystate_flags.free end
minor.IsMinor=function() error('Stock city-state menu does not require IsMinor') end
minor.GetInfluence=function()
    citystate_reads.influence=citystate_reads.influence+1
    return {CanReceiveInfluence=function() return citystate_flags.receives end}
end
PlayerConfigurations[1].GetCivilizationShortDescription=function()
    citystate_reads.identity=citystate_reads.identity+1
    assert(not citystate_flags.free and not citystate_flags.major and citystate_flags.receives)
    return 'Known city-state'
end
PlayerManager={GetAliveMinors=function() return {minor} end}
GameCapabilities={HasCapability=function(cap)
    assert(cap=='CAPABILITY_MILITARY');return citystate_flags.military
end}
local diplomacy=player:GetDiplomacy()
diplomacy.IsAtWarWith=function(self,id) assert(id==1);return citystate_flags.at_war end
diplomacy.CanDeclareWarOn=function(self,id)
    assert(id==1);citystate_reads.war=citystate_reads.war+1;return citystate_flags.can_war
end
diplomacy.CanMakePeaceWith=function(self,id)
    assert(id==1);citystate_reads.peace=citystate_reads.peace+1;return citystate_flags.can_peace
end
'''


def city_state_actions(out):
    return {item["action"]["type"] for item in out["items"].values() if item["action"]}


@pytest.mark.parametrize("at_war,offered,unqueried", [
    ("false", "city_state_war", "peace"), ("true", "city_state_peace", "war"),
])
def test_city_state_war_and_peace_are_mutually_exclusive_even_when_both_apis_allow(at_war, offered, unqueried):
    setup = CITY_STATE_SETUP + f"citystate_flags.at_war={at_war}"
    vm, out = execute("city_states", query=True, setup=setup)
    assert city_state_actions(out) == {"city_state_envoy", "city_state_levy", offered}
    assert vm.globals().citystate_reads[unqueried] == 0
    assert len(vm.globals().calls) == 0
    for action in ("city_state_war", "city_state_peace"):
        vm, out = execute(action, {"target_player": 1}, setup=setup)
        assert out["accepted"] is (action == offered)
        assert len(vm.globals().calls) == int(action == offered)
        if action == offered:
            operation = "DIPLOMACY_DECLARE_WAR" if action.endswith("war") else "DIPLOMACY_MAKE_PEACE"
            request = vm.globals().calls[1]
            assert request[1] == 0
            assert request[2] == vm.globals().PlayerOperations[operation]
            assert request[3][vm.globals().PlayerOperations.PARAM_PLAYER_ONE] == 0
            assert request[3][vm.globals().PlayerOperations.PARAM_PLAYER_TWO] == 1


@pytest.mark.parametrize("state,blocked", [("false", "can_war"), ("true", "can_peace")])
def test_city_state_correct_war_state_still_requires_normal_permission(state, blocked):
    setup = CITY_STATE_SETUP + f"citystate_flags.at_war={state};citystate_flags.{blocked}=false"
    vm, out = execute("city_states", query=True, setup=setup)
    assert city_state_actions(out) == {"city_state_envoy", "city_state_levy"}
    for action in ("city_state_war", "city_state_peace"):
        vm, out = execute(action, {"target_player": 1}, setup=setup)
        assert out["accepted"] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize("mutation", [
    "citystate_flags.free=true", "citystate_flags.major=true",
    "citystate_flags.barbarian=true", "citystate_flags.alive=false",
    "citystate_flags.receives=false", "Players[1].GetInfluence=function() return nil end",
    "Players[1].GetInfluence=function() return {} end",
])
def test_non_city_states_are_removed_before_names_and_all_operations(mutation):
    setup = CITY_STATE_SETUP + mutation
    vm, out = execute("city_states", query=True, setup=setup)
    assert len(out["items"]) == 1 and out["items"][1]["id"] == "envoys"
    assert vm.globals().citystate_reads.identity == 0
    assert vm.globals().citystate_reads.war == vm.globals().citystate_reads.peace == 0
    for action in ("city_state_envoy", "city_state_levy", "city_state_war", "city_state_peace"):
        vm, out = execute(action, {"target_player": 1}, setup=setup)
        assert out["accepted"] is False and len(vm.globals().calls) == 0


def test_free_city_player_62_never_appears_as_city_state_peace_or_envoy():
    setup = CITY_STATE_SETUP + '''
known[62]=true
Players[62]={IsMajor=function() return false end,IsAlive=function() return true end,
    IsBarbarian=function() return false end,IsFreeCities=function() return true end,
    GetID=function() return 62 end,GetInfluence=function() error('FREE CITY INFLUENCE') end}
PlayerManager.GetAliveMinors=function() return {Players[1],Players[62]} end
'''
    vm, out = execute("city_states", query=True, setup=setup)
    assert all(item["action"] is None or item["action"]["target_player"] == 1 for item in out["items"].values())
    assert vm.globals().reads == 0
    for action in ("city_state_envoy", "city_state_levy", "city_state_war", "city_state_peace"):
        vm, out = execute(action, {"target_player": 62}, setup=setup)
        assert out["accepted"] is False and len(vm.globals().calls) == 0
        assert vm.globals().reads == 0


def test_city_state_unknown_player_never_reaches_identity_or_component_getters():
    setup = CITY_STATE_SETUP + '''
PlayerManager.GetAliveMinors=function()
    return {setmetatable({GetID=function() return 9 end},{__index=function() error('UNKNOWN COMPONENT') end})}
end
'''
    vm, out = execute("city_states", query=True, setup=setup)
    assert len(out["items"]) == 1 and vm.globals().reads == 0
    for action in ("city_state_envoy", "city_state_levy", "city_state_war", "city_state_peace"):
        vm, out = execute(action, {"target_player": 9}, setup=setup)
        assert out["accepted"] is False and len(vm.globals().calls) == 0
        assert vm.globals().reads == 0


def test_base_city_state_without_free_cities_method_still_supports_envoys_and_war():
    setup = CITY_STATE_SETUP + "Players[1].IsFreeCities=nil"
    _, out = execute("city_states", query=True, setup=setup)
    assert city_state_actions(out) == {"city_state_envoy", "city_state_levy", "city_state_war"}
    vm, out = execute("city_state_envoy", {"target_player": 1}, setup=setup)
    assert out["accepted"] is True and len(vm.globals().calls) == 1


@pytest.mark.parametrize("mutation", [
    "citystate_flags.military=false", "GameCapabilities=nil", "GameCapabilities.HasCapability=nil",
])
def test_military_capability_gates_war_peace_levy_but_preserves_envoys(mutation):
    setup = CITY_STATE_SETUP + mutation
    _, out = execute("city_states", query=True, setup=setup)
    assert city_state_actions(out) == {"city_state_envoy"}
    for action in ("city_state_envoy", "city_state_levy", "city_state_war", "city_state_peace"):
        vm, out = execute(action, {"target_player": 1}, setup=setup)
        assert out["accepted"] is (action == "city_state_envoy")
        assert len(vm.globals().calls) == int(action == "city_state_envoy")


@pytest.mark.parametrize("mutation", [
    "player:GetDiplomacy().IsAtWarWith=nil", "citystate_flags.at_war=nil", "citystate_flags.at_war=1",
    "player:GetDiplomacy().CanDeclareWarOn=nil;player:GetDiplomacy().CanMakePeaceWith=nil",
])
def test_missing_or_unknown_war_state_never_offers_or_submits_war_or_peace(mutation):
    setup = CITY_STATE_SETUP + mutation
    _, out = execute("city_states", query=True, setup=setup)
    assert city_state_actions(out) == {"city_state_envoy", "city_state_levy"}
    for action in ("city_state_war", "city_state_peace"):
        vm, out = execute(action, {"target_player": 1}, setup=setup)
        assert out["accepted"] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize("action,original,changed", [
    ("city_state_war", "false", "true"), ("city_state_peace", "true", "false"),
])
def test_city_state_action_rechecks_war_state_after_query(action, original, changed):
    vm = LuaRuntime(unpack_returned_tuples=True)
    body = (ENGINE + LUA_HELPERS + CITY_STATE_SETUP + f"citystate_flags.at_war={original}\n"
            + "local function inspect()\n" + QUERIES["city_states"].body({}) + "\nend\ninspect()\n"
            + f"citystate_flags.at_war={changed}\n"
            + "local function submit()\n" + ACTIONS[action].body({"type": action, "target_player": 1})
            + "\nend\nsubmit()\nreturn out")
    out = vm.execute(body)
    assert action in city_state_actions(out)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize("target,session", [(9,5), (1,6)])
def test_cannot_respond_to_unmet_or_wrong_session(target, session):
    vm, out = execute("diplomacy_respond", {"target_player": target,"session_id":session,"signature":"STATEMENT_1","response":"CHOICE_POSITIVE"}, setup=CAPTURED_STATEMENT)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


def test_diplomacy_own_session_receives_decision_mode():
    _, out = execute("diplomacy_actions", {"target_player":1}, query=True, setup=CAPTURED_STATEMENT)
    assert out["decision_mode"] == "diplomacy"
    assert any(i["action"] and i["action"]["type"]=="diplomacy_respond" for i in out["items"].values())


def test_diplomacy_discovery_uses_only_met_sessions_and_current_choices():
    vm, out = execute("diplomacy_sessions", query=True, setup=CAPTURED_STATEMENT)
    assert vm.globals().reads == 0
    actions=[dict(i["action"].items()) for i in out["items"].values() if i["action"]]
    assert len(actions)==2 and actions[0]["response"]=="CHOICE_POSITIVE"
    assert actions[1]["type"]=="diplomacy_close"


@pytest.mark.parametrize("response,signature", [("CHOICE_NEGATIVE","STATEMENT_1"),("CHOICE_POSITIVE","STATEMENT_2")])
def test_unoffered_or_stale_diplomacy_response_is_rejected(response, signature):
    vm, out = execute("diplomacy_respond", {"target_player":1,"session_id":5,"signature":signature,"response":response}, setup=CAPTURED_STATEMENT)
    assert out["accepted"] is False and len(vm.globals().calls)==0


def test_diplomacy_response_consumes_captured_statement():
    vm, out = execute("diplomacy_respond", {"target_player":1,"session_id":5,"signature":"STATEMENT_1","response":"CHOICE_POSITIVE"}, setup=CAPTURED_STATEMENT)
    assert out["accepted"] is True
    assert vm.globals()._CIV6FAIR_V1.diplomacy_statements[5] is None
    assert vm.globals().calls[1][3]=='POSITIVE'


def test_uncaptured_existing_session_never_invents_response_choices():
    _, out = execute("diplomacy_sessions", query=True)
    assert not any(i["action"] for i in out["items"].values())
    assert any(i["id"].startswith('prompt_unavailable') for i in out["items"].values())


def test_statement_hook_filters_events_before_reading_variants():
    vm=LuaRuntime(unpack_returned_tuples=True)
    vm.execute(ENGINE+'''
state={session='test',player_id=0};_CIV6FAIR_V1=state
Game.GetLocalPlayer=function() return 0 end;Game.GetLocalObserver=function() return 0 end
player.IsHuman=function() return true end;player.IsAlive=function() return true end
Events={DiplomacyStatement={Add=function(fn) callback=fn end}}
'''+DIPLOMACY_HOOK+'''
callback(9,8,setmetatable({},{__index=function() error('HIDDEN VARIANT') end}))
callback(9,0,setmetatable({},{__index=function() error('HIDDEN VARIANT') end}))
callback(1,0,{SessionID=5,StatementType=100,StatementSubType=0,FromPlayerMood=2,AiReason='SECRET'})
''')
    captured=dict(vm.globals().state.diplomacy_statements[5].items())
    assert 'AiReason' not in captured and captured['signature']=='STATEMENT_1'


def test_trade_options_never_return_locked_strategic_resource():
    vm, out = execute("deal_options", {"target_player":1,"side":"receive","kind":"resource"}, query=True)
    assert len(out["items"]) == 1
    assert out["items"][1]["name"] == "Iron"
    assert out["items"][1]["action"]["value"] == 1
    assert vm.globals().reads == 0


def test_hidden_trade_terms_do_not_generate_observable_signature():
    _, out = execute("deal_state", {"target_player":1}, query=True,
        setup="dealItems={make_item(4,3,2,9999)}")
    assert len(out["items"]) == 1
    assert out["items"][1]["id"] == "incoming_response_status"
    assert out["items"][1]["value"] == "filtered_terms"


def deal_terms(out):
    return {item["id"]: dict(item.items()) for item in out["items"].values()
            if item["id"].startswith(("OUTGOING_", "INCOMING_"))}


@pytest.mark.parametrize("caption", ["return 'LOC_OPEN_BORDERS'", "return nil", "error('caption unavailable')"])
def test_deal_agreement_negative_hash_has_public_name_and_original_numeric_terms(caption):
    setup = '''
DealAgreementTypes.OPEN_BORDERS=-242352742
GameInfo.DiplomaticActions={[-242352742]={Name='LOC_OPEN_BORDERS'}}
Locale.Lookup=function(key) return key=='LOC_OPEN_BORDERS' and '开放边境' or key end
local term=make_item(4,DealItemTypes.AGREEMENTS,0,1)
term.GetSubType=function() return -242352742 end
term.GetDuration=function() return 20 end
dealItems={term}
''' + f"term.GetSubTypeNameID=function() {caption} end"
    vm, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    terms = deal_terms(out)
    assert terms["INCOMING_4"]["name"] == "receive 开放边境 amount=1 turns=20"
    assert terms["INCOMING_4"]["description"] == "receive AGREEMENTS value=0 amount=1 turns=20 subtype=-242352742"
    assert "action" not in terms["INCOMING_4"]
    assert terms["OUTGOING_4"]["action"]["type"] == "deal_remove_item"
    assert {item["id"] for item in out["items"].values()} >= {"accept", "reject"}
    assert len(vm.globals().calls) == 0


def test_deal_agreement_prefers_original_ui_caption_and_falls_back_to_symbolic_type():
    common = '''
local term=make_item(4,DealItemTypes.AGREEMENTS,0,1)
term.GetSubType=function() return DealAgreementTypes.OPEN_BORDERS end
dealItems={term}
'''
    _, out = execute("deal_state", {"target_player": 1}, query=True, setup=common + '''
term.GetSubTypeNameID=function() return 'Original UI agreement caption' end
GameInfo.DiplomaticActions=setmetatable({},{__index=function() error('Unneeded fallback') end})
''')
    assert "Original UI agreement caption" in deal_terms(out)["INCOMING_4"]["name"]
    _, out = execute("deal_state", {"target_player": 1}, query=True,
                     setup=common + "GameInfo.DiplomaticActions={}")
    assert "OPEN_BORDERS" in deal_terms(out)["INCOMING_4"]["name"]


@pytest.mark.parametrize("kind,duration,expected", [
    (1, 0, "Gold"), (1, 20, "Gold per turn"), (2, 0, "Diplomatic favor"),
])
def test_deal_money_labels_distinguish_per_turn_gold_without_reading_treasuries(kind, duration, expected):
    setup = f'''
local names={{LOC_YIELD_GOLD_NAME='Gold',LOC_DIPLOMACY_DEAL_GOLD_PER_TURN='Gold per turn',LOC_DIPLOMATIC_FAVOR_NAME='Diplomatic favor'}}
Locale.Lookup=function(key) return names[key] or key end
local term=make_item(4,{kind},0,8)
term.GetFromPlayerID=function() return me end
term.GetDuration=function() return {duration} end
dealItems={{term}}
Players[1].GetTreasury=function() error('PRIVATE TREASURY') end
Players[1].GetFavor=function() error('PRIVATE FAVOR BALANCE') end
'''
    vm, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    assert deal_terms(out)["INCOMING_4"]["name"] == f"give {expected} amount=8 turns={duration}"
    assert len(vm.globals().calls) == 0


def test_deal_resource_label_is_read_only_after_reveal_gate():
    setup = '''
local revealed=false
player.GetResources=function() return {IsResourceVisible=function(self,hash)
    assert(hash==100);revealed=true;return true
end} end
GameInfo.Resources[1]=setmetatable({Hash=100,ResourceType='RESOURCE_IRON'},{__index=function(_,key)
    if key=='Name' then assert(revealed);return 'Iron' end
end})
dealItems={make_item(4,DealItemTypes.RESOURCES,1,10)}
'''
    vm, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    assert deal_terms(out)["INCOMING_4"]["name"] == "receive Iron amount=10 turns=0"
    assert "value=1" in deal_terms(out)["INCOMING_4"]["description"]
    assert len(vm.globals().calls) == 0


def test_unrevealed_resource_never_calls_name_or_term_caption_getters():
    setup = '''
GameInfo.Resources[2]=setmetatable({Hash=999},{__index=function() error('HIDDEN RESOURCE NAME') end})
local term=make_item(4,DealItemTypes.RESOURCES,2,10)
term.GetSubTypeNameID=function() error('HIDDEN RESOURCE CAPTION') end
term.GetValueTypeNameID=function() error('HIDDEN RESOURCE CAPTION') end
term.GetAmount=function() error('HIDDEN RESOURCE AMOUNT') end
dealItems={term}
'''
    vm, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    assert len(out["items"]) == 1 and vm.globals().reads == 0
    assert out["items"][1]["value"] == "filtered_terms"


@pytest.mark.parametrize("agreement,table,name", [
    ("ALLIANCE", "Alliances", "Research alliance"),
    ("RESEARCH_AGREEMENT", "Technologies", "Computers"),
])
def test_deal_agreement_parameter_uses_public_rule_name(agreement, table, name):
    setup = f'''
local term=make_item(4,DealItemTypes.AGREEMENTS,7,1)
term.GetSubType=function() return DealAgreementTypes.{agreement} end
term.GetSubTypeNameID=function() return 'Agreement' end
GameInfo.{table}[7]={{Name='{name}'}}
dealItems={{term}}
'''
    _, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    assert f"Agreement / {name}" in deal_terms(out)["INCOMING_4"]["name"]
    assert "value=7" in deal_terms(out)["INCOMING_4"]["description"]


def test_deal_unknown_war_target_filtered_before_caption_or_rule_lookup():
    setup = '''
DealAgreementTypes.JOINT_WAR=7
local term=make_item(4,DealItemTypes.AGREEMENTS,9,1)
term.GetSubType=function() return 7 end
term.GetSubTypeNameID=function() error('HIDDEN TARGET CAPTION') end
GameInfo.DiplomaticActions=setmetatable({},{__index=function() error('HIDDEN TARGET RULE') end})
dealItems={term}
'''
    vm, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    assert len(out["items"]) == 1 and vm.globals().reads == 0
    assert out["items"][1]["value"] == "filtered_terms"


def test_deal_known_war_target_name_does_not_read_other_player_world_state():
    setup = '''
DealAgreementTypes.JOINT_WAR=7
known[2]=true
PlayerConfigurations[2]={GetCivilizationShortDescription=function() return 'Known target' end}
local term=make_item(4,DealItemTypes.AGREEMENTS,2,1)
term.GetSubType=function() return 7 end
term.GetSubTypeNameID=function() return 'Joint war' end
term.GetParameterValue=function(self,key) assert(key=='WarType');return 12 end
GameInfo.Wars={[12]={WarType='WAR_FORMAL'}}
Players[1].GetCities=function() error('FOREIGN CITY STATE') end
dealItems={term}
'''
    vm, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    assert "Joint war / Known target" in deal_terms(out)["INCOMING_4"]["name"]
    assert "war=WAR_FORMAL" in deal_terms(out)["INCOMING_4"]["description"]
    assert vm.globals().reads == 0


@pytest.mark.parametrize("kind,expected", [(5, "Cities"), (6, "GREATWORK"), (7, "Captives")])
def test_deal_object_labels_never_expand_foreign_city_or_captive_identity(kind, expected):
    setup = f'''
GameInfo.GreatWorks={{[0]={{Name='Public work'}}}}
Locale.Lookup=function(key)
    local names={{LOC_DIPLOMACY_DEAL_CITIES='Cities',LOC_DIPLOMACY_DEAL_CAPTIVES='Captives'}}
    return names[key] or key
end
local term=make_item(4,{kind},123,1)
term.GetValueTypeNameID=function() error('FOREIGN ENTITY NAME') end
Players[1].GetCities=function() error('FOREIGN CITY STATE') end
Players[1].GetUnits=function() error('FOREIGN UNIT STATE') end
dealItems={{term}}
'''
    vm, out = execute("deal_state", {"target_player": 1}, query=True, setup=setup)
    assert expected in deal_terms(out)["INCOMING_4"]["name"]
    assert "value=123" in deal_terms(out)["INCOMING_4"]["description"]
    assert vm.globals().reads == 0


def test_deal_localized_labels_do_not_change_price_fingerprint_or_acceptance():
    _, original = execute("deal_state", {"target_player": 1}, query=True)
    _, localized = execute("deal_state", {"target_player": 1}, query=True,
                           setup="Locale.Lookup=function() return 'Localized label' end")
    def accept_action(out):
        return next(dict(i["action"].items()) for i in out["items"].values() if i["id"] == "accept")
    assert accept_action(original) == accept_action(localized)
    action = accept_action(localized)
    action.pop("type")
    vm, accepted = execute("deal_respond", action)
    assert accepted["accepted"] is True and len(vm.globals().calls) == 2


def test_changed_incoming_offer_cannot_be_accepted():
    _, out = execute("deal_state", {"target_player":1}, query=True)
    action = next(dict(i["action"].items()) for i in out["items"].values() if i["id"]=="accept")
    action.pop("type")
    vm, rejected = execute("deal_respond", action, setup="dealItems={make_item(4,1,0,250)}")
    assert rejected["accepted"] is False and len(vm.globals().calls) == 0
    vm, accepted = execute("deal_respond", action)
    assert accepted["accepted"] is True and len(vm.globals().calls) == 2


BALLOT = {"resolutions":[{"resolution":"WC_RES_TEST","choice":1,"selection":0,"votes":1}],"discussions":[]}


def test_complete_congress_ballot_uses_normal_requests():
    vm, out = execute("congress_ballot", BALLOT)
    assert out["accepted"] is True
    assert len(vm.globals().calls) == 3  # resolution, submit, normal stage end


@pytest.mark.parametrize("setup,ballot", [
    ("segment=99", BALLOT),
    ("favor=-1", BALLOT),
    ("", {"resolutions":[],"discussions":[]}),
    ("", {"resolutions":[{"resolution":"WC_RES_TEST","choice":1,"selection":99,"votes":1}],"discussions":[]}),
    ("", {"resolutions":[BALLOT["resolutions"][0],BALLOT["resolutions"][0]],"discussions":[]}),
    ("", {"resolutions":[{"resolution":"WC_RES_TEST","choice":1,"selection":0,"votes":1000}],"discussions":[]}),
])
def test_invalid_congress_ballot_never_partially_submits(setup, ballot):
    vm, out = execute("congress_ballot", ballot, setup=setup)
    assert out["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_unknown_congress_targets_are_ordinal_choices_not_identities():
    vm, out = execute("world_congress", query=True)
    assert out["decision_mode"] == "congress"
    items = {i["id"]: i for i in out["items"].values()}
    unknown = items["WC_RES_TEST_selection_2"]
    assert unknown["name"] == "Unknown civilization" and unknown["value"] == 2
    assert vm.globals().reads == 0


def test_congress_mode_not_returned_during_regular_turn():
    _, out = execute("world_congress", query=True, setup="segment=99")
    assert out["decision_mode"] is None


def test_congress_votes_respect_direction_restrictions():
    setup = '''proposed={Proposals={one={ProposalsOfType={{Type=7,Target=9,Sender=9,VotingRestriction='NO_DOWN'}}}}}
GameInfo.VotingBlockers.NO_DOWN={NoDownvote=true}'''
    ballot = dict(BALLOT, discussions=[{"proposal":0,"direction":-1,"votes":1}])
    vm, out = execute("congress_ballot", ballot, setup=setup)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


def test_artifact_unknown_provenance_uses_anonymous_choice():
    setup = '''local unit={GetOwner=function() return 0 end,GetID=function() return 14 end,
GetArchaeology=function() return {GetArtifactIndex=function() return 7 end} end}
player:GetUnits().GetNextExtractingArchaeologist=function() return unit end
Game.GetArtifactByIndex=function() return {Type=3,ActingPlayerID=1,TargetPlayerID=9} end'''
    vm, out = execute("archaeology", query=True, setup=setup)
    assert [i["name"] for i in out["items"].values()] == ["known","Unknown civilization"]
    assert out["items"][2]["action"]["choice"] == 2 and vm.globals().reads == 0
    vm, out = execute("choose_artifact", {"unit_id":14,"choice":2}, setup=setup)
    assert out["accepted"] is True and vm.globals().reads == 0


def test_artifact_refuses_foreign_archaeologist():
    setup = '''player:GetUnits().GetNextExtractingArchaeologist=function() return {GetOwner=function() return 9 end} end
Game.GetArtifactByIndex=function() error('MUST NOT READ') end'''
    _, out = execute("choose_artifact", {"unit_id":14,"choice":1}, setup=setup)
    assert out["accepted"] is False


def test_schemas_reject_unbounded_actions_and_lua_injection():
    with pytest.raises(ValueError):
        validate({"target_player":1,"statement":"DECLARE_SURPRISE_WAR);error('x')"}, ACTIONS["diplomacy_statement"].fields)
    with pytest.raises(ValueError):
        validate({"resolutions":[BALLOT["resolutions"][0]]*129,"discussions":[]}, ACTIONS["congress_ballot"].fields)
    with pytest.raises(ValueError):
        validate({"target_player":True}, ACTIONS["city_state_war"].fields)


WORK_SETUP = '''
slots={[2]={[0]=11,[1]=12},[3]={[0]=-1,[1]=-1}}
object='GREATWORKOBJECT_WRITING';created=0;compatibleSlot=true
GlobalParameters={GREATWORK_ART_LOCK_TIME=10}
GameInfo.Buildings={BUILDING_MUSEUM={Index=4}}
GameInfo.GreatWorks=setmetatable({},{__index=function() return {GreatWorkObjectType=object} end})
GameInfo.GreatWorkSlotTypes={[3]={GreatWorkSlotType='SLOT'}}
GameInfo.GreatWork_ValidSubTypes=function()
    local i=0
    return function() i=i+1;if i==1 then return {GreatWorkSlotType='SLOT',GreatWorkObjectType=compatibleSlot and object or 'OTHER'} end end
end
local function city(id)
    local b={HasBuilding=function() return true end,GetNumGreatWorkSlots=function() return 2 end,
        GetGreatWorkInSlot=function(_,_,slot) assert(slot>=0 and slot<2);return slots[id][slot] end,
        GetGreatWorkTypeFromIndex=function(_,work) return work end,GetGreatWorkSlotType=function() return 3 end,
        GetTurnFromIndex=function() return created end}
    return {GetID=function() return id end,GetBuildings=function() return b end}
end
local ownCities={[2]=city(2),[3]=city(3)}
find_owned=function(collection,id) return ownCities[id] end
'''
WORK_MOVE = {"source_city":2,"destination_city":3,"source_building":"BUILDING_MUSEUM",
    "destination_building":"BUILDING_MUSEUM","source_slot":0,"destination_slot":0}


def test_great_work_moves_only_between_compatible_own_slots():
    vm, out = execute('move_great_work', WORK_MOVE, setup=WORK_SETUP)
    assert out['accepted'] is True and len(vm.globals().calls)==1


@pytest.mark.parametrize('extra', [
    'compatibleSlot=false',
    "object='GREATWORKOBJECT_PORTRAIT';created=19",
    "object='GREATWORKOBJECT_ARTIFACT';slots[2][1]=-1",
    "object='GREATWORKOBJECT_ARTIFACT'",  # destination museum empty
])
def test_great_work_restrictions_are_enforced_before_request(extra):
    vm, out = execute('move_great_work', WORK_MOVE, setup=WORK_SETUP+extra)
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_great_work_target_out_of_range_not_read():
    vm, out = execute('move_great_work', dict(WORK_MOVE,destination_slot=500), setup=WORK_SETUP)
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_great_work_foreign_destination_rejected():
    vm, out = execute('move_great_work', dict(WORK_MOVE,destination_city=9), setup=WORK_SETUP)
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_world_congress_respects_max_votes_even_when_cost_entry_exists():
    vm, out = execute('congress_ballot', dict(BALLOT,resolutions=[dict(BALLOT['resolutions'][0],votes=2)]), setup='costs.MaxVotes=1')
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_emergency_proposal_uses_available_emergencies_and_cost():
    setup="segment=99;proposed={Proposals={one={FavorCost=30,ProposalsOfType={{Type=7,Target=9,Sender=9,Name='Aid'}}}}}"
    vm, out = execute('congress_propose', {'proposal':0}, setup=setup)
    assert out['accepted'] is True and vm.globals().reads==0
    vm, out = execute('congress_propose', {'proposal':0}, setup=setup+';favor=20')
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_draft_edits_require_live_local_conversation():
    vm, out = execute('deal_clear', {'target_player':1}, setup='DiplomacyManager.FindOpenSessionID=function() return nil end')
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_received_gift_or_demand_cannot_be_edited_into_counteroffer():
    setup="draft.IsGift=function() return true end"
    vm, out = execute('deal_clear', {'target_player':1}, setup=setup)
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_counteroffer_uses_adjusted_operation():
    setup="draft.IsGift=function() return false end;DealProposalAction.ADJUSTED=8"
    vm, out = execute('deal_send', {'target_player':1}, setup=setup)
    assert out['accepted'] is True
    assert vm.globals().calls[1][1]==8


def test_war_deal_choices_do_not_read_unknown_enemy_metadata():
    setup='''DealAgreementTypes.JOINT_WAR=8
possible={setmetatable({ForType=9},{__index=function() error('UNKNOWN ENEMY DETAIL') end})}'''
    vm, out=execute('war_deal_options',{'target_player':1,'side':'give','agreement':'JOINT_WAR'},query=True,setup=setup)
    assert out['supported'] is True and len(out['items'])==0 and vm.globals().reads==0


def test_emergency_join_only_before_begin_and_acknowledge_after():
    setup='''emergencies={{TargetID=9,EmergencyType=7,HasBegun=false}}
Game.GetEmergencyManager=function() return {GetEmergencyInfoTable=function(_,id) assert(id==0);return emergencies end} end'''
    vm,out=execute('emergencies',query=True,setup=setup)
    assert sum(bool(v['action']) for v in out['items'].values())==2 and vm.globals().reads==0
    vm,out=execute('emergency_respond',{'emergency':0,'choice':'join'},setup=setup)
    assert out['accepted'] is True and vm.globals().reads==0
    vm,out=execute('emergency_respond',{'emergency':0,'choice':'acknowledge'},setup=setup)
    assert out['accepted'] is False and len(vm.globals().calls)==0
    vm,out=execute('emergency_respond',{'emergency':0,'choice':'join'},setup=setup+';emergencies[1].HasBegun=true')
    assert out['accepted'] is False and len(vm.globals().calls)==0


def test_acknowledge_proposals_cannot_skip_a_congress_vote():
    setup='''NotificationManager={GetFirstEndTurnBlocking=function() return 7 end}
EndTurnBlockingTypes={ENDTURN_BLOCKING_WORLD_CONGRESS_LOOK=7}'''
    vm,out=execute('congress_acknowledge',setup=setup)
    assert out['accepted'] is False and len(vm.globals().calls)==0
    vm,out=execute('congress_acknowledge',setup=setup+';segment=99')
    assert out['accepted'] is True and len(vm.globals().calls)==1
