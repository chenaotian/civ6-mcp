"""Normal diplomacy, negotiated deals, congress and culture UI operations.

Source contracts are recorded in docs/DIPLOMACY_ACTIONS.md.  No API in this
module accepts a free-form operation, SQL statement, Lua expression or player
perspective.  All counterpart access starts with the local HasMet gate.
"""
from __future__ import annotations

from .base import ActionSpec, QuerySpec, lua, own_city
from .city_state_details import CITY_STATE_DETAILS
from .city_state_envoys import ENVOY_DEFER_HELPERS, defer_envoys


_STATEMENTS = {
    "surprise_war": ("DECLARE_SURPRISE_WAR", "DIPLOACTION_DECLARE_SURPRISE_WAR"),
    "formal_war": ("DECLARE_FORMAL_WAR", "DIPLOACTION_DECLARE_FORMAL_WAR"),
    "holy_war": ("DECLARE_HOLY_WAR", "DIPLOACTION_DECLARE_HOLY_WAR"),
    "liberation_war": ("DECLARE_LIBERATION_WAR", "DIPLOACTION_DECLARE_LIBERATION_WAR"),
    "reconquest_war": ("DECLARE_RECONQUEST_WAR", "DIPLOACTION_DECLARE_RECONQUEST_WAR"),
    "protectorate_war": ("DECLARE_PROTECTORATE_WAR", "DIPLOACTION_DECLARE_PROTECTORATE_WAR"),
    "colonial_war": ("DECLARE_COLONIAL_WAR", "DIPLOACTION_DECLARE_COLONIAL_WAR"),
    "territorial_war": ("DECLARE_TERRITORIAL_WAR", "DIPLOACTION_DECLARE_TERRITORIAL_WAR"),
    "golden_age_war": ("DECLARE_GOLDEN_WAR", "DIPLOACTION_DECLARE_GOLDEN_AGE_WAR"),
    "retribution_war": ("DECLARE_WAR_OF_RETRIBUTION", "DIPLOACTION_DECLARE_WAR_OF_RETRIBUTION"),
    "ideological_war": ("DECLARE_IDEOLOGICAL_WAR", "DIPLOACTION_DECLARE_IDEOLOGICAL_WAR"),
    "delegation": ("DIPLOMATIC_DELEGATION", "DIPLOACTION_DIPLOMATIC_DELEGATION"),
    "embassy": ("RESIDENT_EMBASSY", "DIPLOACTION_RESIDENT_EMBASSY"),
    "friendship": ("DECLARE_FRIEND", "DIPLOACTION_DECLARE_FRIENDSHIP"),
    "denounce": ("DENOUNCE", "DIPLOACTION_DENOUNCE"),
    "open_borders": ("OPEN_BORDERS", "DIPLOACTION_OPEN_BORDERS"),
    "stop_spying": ("WARNING_STOP_SPYING_ON_ME", "DIPLOACTION_KEEP_PROMISE_DONT_SPY"),
    "stop_settling": ("WARNING_DONT_SETTLE_NEAR_ME", "DIPLOACTION_KEEP_PROMISE_DONT_SETTLE_TOO_NEAR"),
    "stop_converting": ("WARNING_STOP_CONVERTING_MY_CITIES", "DIPLOACTION_KEEP_PROMISE_DONT_CONVERT"),
    "stop_digging": ("WARNING_STOP_DIGGING_UP_ARTIFACTS", "DIPLOACTION_KEEP_PROMISE_DONT_DIG_ARTIFACTS"),
    "trade": ("MAKE_DEAL", "DIPLOACTION_PROPOSE_TRADE"),
    "peace": ("MAKE_DEAL", "DIPLOACTION_PROPOSE_PEACE_DEAL"),
}
_AGREEMENTS = ("OPEN_BORDERS", "MAKE_PEACE", "ALLIANCE", "DEFENSIVE_PACT", "RESEARCH_AGREEMENT")
_TRADE_KINDS = {"gold": "GOLD", "favor": "FAVOR", "resource": "RESOURCES",
                "agreement": "AGREEMENTS", "city": "CITIES", "great_work": "GREATWORK", "captive": "CAPTIVE"}

DIPLOMACY_HOOK = r'''
-- Cache only statements actually delivered to the local participant. Never
-- scrape other sessions, save state, AI plans, reason IDs or a complete variant.
if state.diplomacy_session~=session then
    state.diplomacy_statements={}
    state.deal_actions={}
    state.diplomacy_session=session
end
if not state.diplomacy_hooks and Events and Events.DiplomacyStatement
    and type(Events.DiplomacyStatement.Add)=="function" then
    Events.DiplomacyStatement.Add(function(from,to,variant)
        pcall(function()
            local current=Game.GetLocalPlayer()
            if current<0 or Game.GetLocalObserver()~=current
                or (from~=current and to~=current) or type(variant)~="table" then return end
            local p=Players[current]
            if not p or p:IsHuman()~=true or p:IsAlive()~=true
                or state.player_id~=current or state.session==nil then return end
            local other=from==current and to or from
            if type(other)~="number" or other<0 or other==current
                or p:GetDiplomacy():HasMet(other)~=true then return end
            local sid=variant.SessionID
            if type(sid)~="number" or sid<0 or sid%1~=0 then return end
            local copy={from=from,to=to,other=other,session=state.session}
            for _,key in ipairs({"StatementType","StatementSubType","FromPlayerMood","FromMood","Initiator"}) do
                local value=variant[key]
                if value~=nil and (type(value)~="number" or value%1~=0) then return end
                copy[key]=value
            end
            if copy.Initiator~=nil and copy.Initiator~=current and copy.Initiator~=other then return end
            state.diplomacy_counter=(state.diplomacy_counter or 0)+1
            copy.signature="STATEMENT_"..state.diplomacy_counter
            state.diplomacy_statements=state.diplomacy_statements or {}
            state.diplomacy_statements[sid]=copy
        end)
    end)
    state.diplomacy_hooks=true
end
if not state.deal_hooks and Events and Events.DiplomacyIncomingDeal
    and type(Events.DiplomacyIncomingDeal.Add)=="function" then
    Events.DiplomacyIncomingDeal.Add(function(from,to,action)
        pcall(function()
            local current=Game.GetLocalPlayer()
            if current<0 or to~=current or from==current or Game.GetLocalObserver()~=current then return end
            local p=Players[current]
            if not p or p:IsHuman()~=true or state.player_id~=current or state.session==nil
                or p:GetDiplomacy():HasMet(from)~=true or type(action)~="number" then return end
            state.deal_actions=state.deal_actions or {}
            state.deal_actions[from]={session=state.session,action=action}
        end)
    end)
    state.deal_hooks=true
end
-- v2 is deliberately independent of already-installed v1 closures. Working
-- INCOMING objects and the old per-opponent action cache are not offer proof.
-- These are the same public events consumed by DiplomacyDealView; no dialog
-- text, AI evaluation reason, or private UI variable is read.
if state.deal_role_session_v2~=session then
    state.deal_roles_v2={}
    state.deal_role_hidden_v2=false
    state.deal_role_session_v2=session
end
if not state.deal_role_hooks_v2 then
    local function identity(other)
        local current=Game.GetLocalPlayer()
        if type(current)~="number" or current<0 or Game.GetLocalObserver()~=current
            or state.player_id~=current or state.session==nil
            or type(other)~="number" or other%1~=0 or other<0 or other==current then return end
        local p=Players[current]
        if not p or p:IsHuman()~=true or p:IsAlive()~=true
            or p:GetDiplomacy():HasMet(other)~=true or not DiplomacyManager
            or type(DiplomacyManager.FindOpenSessionID)~="function"
            or type(DiplomacyManager.GetSessionInfo)~="function"
            or type(DiplomacyManager.IsSessionIDOpen)~="function" then return end
        local sid=DiplomacyManager.FindOpenSessionID(current,other)
        if type(sid)~="number" or sid<0 or sid%1~=0 or DiplomacyManager.IsSessionIDOpen(sid)~=true then return end
        local info=DiplomacyManager.GetSessionInfo(sid)
        if not info or not ((info.FromPlayer==current and info.ToPlayer==other)
            or (info.FromPlayer==other and info.ToPlayer==current)) then return end
        return current,sid,info.FromPlayer
    end
    local function save(other,action,show,demand,require_open)
        local current,sid,initiator=identity(other)
        if not current then return end
        local roles=state.deal_roles_v2 or {}
        local old=roles[sid]
        if require_open and (not old or old.session~=state.session or old.sid~=sid
            or old.player~=current or old.other~=other or old.initiator~=initiator
            or old.observed~=true or old.active~=true) then return end
        if show then
            -- OnShow's native listener can synchronously trigger INSPECT. If
            -- its response was already observed, do not overwrite it when our
            -- listener receives the original Show event later in the list.
            if old and old.session==state.session and old.other==other
                and old.initiator==initiator and old.active==true and old.updated==true then return end
            action=initiator==other and DealProposalAction.PROPOSED or DealProposalAction.PENDING
        elseif old and old.session==state.session and old.active==false then return end
        if type(action)~="number" or action%1~=0 then return end
        roles[sid]={session=state.session,sid=sid,player=current,other=other,
            initiator=initiator,action=action,active=true,observed=true,updated=not show,
            demand=demand==true or (not show and old and old.demand==true)}
        state.deal_roles_v2=roles
        state.deal_role_hidden_v2=false
    end
    local function listen(event,fn)
        if event and type(event.Add)=="function" then
            event.Add(function(...) pcall(fn,...) end)
        end
    end
    if LuaEvents then
        listen(LuaEvents.DiploPopup_ShowMakeDeal,function(other) save(other,nil,true,false) end)
        listen(LuaEvents.DiploPopup_ShowMakeDemand,function(other) save(other,nil,true,true) end)
        listen(LuaEvents.DiploPopup_DealUpdated,function(other,action) save(other,action,false,false) end)
        listen(LuaEvents.DiploPopup_HideDeal,function()
            for _,v in pairs(state.deal_roles_v2 or {}) do v.active=false end
            state.deal_role_hidden_v2=true
        end)
    end
    if Events then
        listen(Events.DiplomacyIncomingDeal,function(from,to,action)
            if to==Game.GetLocalPlayer() then save(from,action,false,false,true) end
        end)
        listen(Events.DiplomacySessionClosed,function(sid)
            local role=state.deal_roles_v2 and state.deal_roles_v2[sid]
            if role and role.session==state.session then role.active=false end
        end)
    end
    state.deal_role_hooks_v2=true
end
'''

_HELPERS = r'''
out.supported=false
local function int(v) return type(v)=="number" and v==math.floor(v) end
local function label(v)
    if type(v)~="string" then return "" end
    if Locale and type(Locale.Lookup)=="function" then return Locale.Lookup(v) end
    return v
end
local function add(id,name,value,action)
    if #out.items>=2048 then error("unavailable") end
    local item={id=tostring(id),name=name,scope="self",owner_id=me}
    if value~=nil then item.value=value end
    if action~=nil then item.action=action end
    table.insert(out.items,item)
end
local function counterpart(id)
    if id==me or not known_player(id) then return nil end
    return Players[id]
end
local function session_for(id)
    if not counterpart(id) or not DiplomacyManager
        or type(DiplomacyManager.FindOpenSessionID)~="function"
        or type(DiplomacyManager.GetSessionInfo)~="function"
        or type(DiplomacyManager.IsSessionIDOpen)~="function" then return nil end
    local sid=DiplomacyManager.FindOpenSessionID(me,id)
    if not int(sid) or sid<0 or DiplomacyManager.IsSessionIDOpen(sid)~=true then return nil end
    local info=DiplomacyManager.GetSessionInfo(sid)
    if not info or not ((info.FromPlayer==me and info.ToPlayer==id)
        or (info.FromPlayer==id and info.ToPlayer==me)) then return nil end
    return sid
end
local function diplomatic_valid(action,id)
    local diplo=player:GetDiplomacy()
    return GameInfo.DiplomaticActions[action]~=nil
        and type(diplo.IsDiplomaticActionValid)=="function"
        and diplo:IsDiplomaticActionValid(action,id,true)==true
end
local function current_statement(id,sid)
    local state=_CIV6FAIR_V1
    local v=state and state.diplomacy_statements and state.diplomacy_statements[sid]
    if not v or v.session~=session or v.other~=id or session_for(id)~=sid then return nil end
    if not DB or type(DB.Query)~="function" or not DiplomacyManager.GetKeyName then return nil end
    local statementType=DiplomacyManager.GetKeyName(v.StatementType)
    local subtype=DiplomacyManager.GetKeyName(v.StatementSubType)
    -- Trade panels have dedicated offered terms and response tools.
    if not statementType or statementType=="MAKE_DEAL" or statementType=="MAKE_DEMAND" then return nil end
    local from=v.from
    if from~=me and not known_player(from) then return nil end
    local leader=PlayerConfigurations[from]:GetLeaderTypeName() or "ANY"
    local moodValue=v.FromPlayerMood
    if DiplomacyMoodTypes and moodValue==DiplomacyMoodTypes.UNDEFINED then
        local other=from==me and id or me
        local index=Players[from]:GetDiplomaticAI():GetDiplomaticStateIndex(other)
        local row=GameInfo.DiplomaticStates[index]
        if not row or not DiplomaticStates then return nil end
        if row.Hash==DiplomaticStates.ALLIED or row.Hash==DiplomaticStates.DECLARED_FRIEND then moodValue=DiplomacyMoodTypes.HAPPY
        elseif row.Hash==DiplomaticStates.DENOUNCED or row.Hash==DiplomaticStates.WAR then moodValue=DiplomacyMoodTypes.UNHAPPY
        else moodValue=DiplomacyMoodTypes.NEUTRAL end
    end
    local mood=moodValue and DiplomacyManager.GetKeyName(moodValue) or "ANY"
    local initiator="HUMAN"
    if v.Initiator~=nil then
        if v.Initiator~=me and not known_player(v.Initiator) then return nil end
        initiator=PlayerConfigurations[v.Initiator]:IsHuman() and "HUMAN" or "AI"
    end
    local rows={}
    local combinations={{leader,mood},{leader,"ANY"},{"ANY",mood},{"ANY","ANY"}}
    for _,c in ipairs(combinations) do
        rows=DB.Query("SELECT StatementText, Selections FROM DiplomacyStatements WHERE Type = ? AND SubType = ? AND Initiator = ? AND Leader = ? AND Mood = ?",
            statementType,subtype or "NONE",initiator,c[1],c[2]) or {}
        if #rows>0 then break end
    end
    if #rows~=1 then return nil end
    local choices={}
    for _,c in ipairs(combinations) do
        choices=DB.Query("SELECT Text, Tooltip, Key, Sort, DiplomaticActionType FROM DiplomacySelections WHERE Type = ? AND Leader = ? AND Mood = ?",
            rows[1].Selections,c[1],c[2]) or {}
        if #choices>0 then break end
    end
    local permitted={}
    for _,choice in ipairs(choices) do
        if type(choice.Key)=="string" and choice.Key:match("^CHOICE_[A-Z0-9_]+$")
            and (not choice.DiplomaticActionType or diplomatic_valid(choice.DiplomaticActionType,id)) then
            if choice.Key~="CHOICE_STOP_ASKING" or Players[id]:IsHuman()~=true then
                table.insert(permitted,{key=choice.Key,text=label(choice.Text)})
            end
        end
    end
    local text=statementType
    if rows[1].StatementText and DiplomacyManager.FindTextKey then
        text=label(DiplomacyManager.FindTextKey(rows[1].StatementText,from,v.FromMood,v.to))
    end
    return {signature=v.signature,choices=permitted,text=text}
end
local function add_conversation(id,sid)
    out.decision_mode="diplomacy"
    add("session_"..id,"Open diplomacy session with player "..id,sid)
    local statement=current_statement(id,sid)
    if not statement then
        add("prompt_unavailable_"..id,"No captured current prompt; inspect deal_state or reopen this conversation after the bridge is attached.")
        return
    end
    add("prompt_"..id,statement.text)
    for _,choice in ipairs(statement.choices) do
        local action={type="diplomacy_respond",target_player=id,session_id=sid,
            signature=statement.signature,response=choice.key}
        if choice.key=="CHOICE_EXIT" then action.type="diplomacy_close";action.response=nil end
        add("response_"..id.."_"..choice.key,choice.text,nil,action)
    end
end
'''


def _target(target: int) -> str:
    return _HELPERS + f"\nlocal target={target}\nlocal other=counterpart(target)\nif not other then return end\n"


def _statement(a: dict) -> str:
    statement, rule = _STATEMENTS[a["statement"]]
    body = _target(a["target_player"]) + f'''
if other:IsMajor()~=true or other:IsAlive()~=true then return end
if not diplomatic_valid({lua(rule)},target) then return end
if not DiplomacyManager or type(DiplomacyManager.RequestSession)~="function" then return end
'''
    if a["statement"] == "peace":
        body += '''
if not DealManager or DealManager.HasPendingDeal(me,target)==true then return end
attempt(function()
    DealManager.ClearWorkingDeal(DealDirection.OUTGOING,me,target)
    local deal=DealManager.GetWorkingDeal(DealDirection.OUTGOING,me,target)
    if not deal then return end
    local item=deal:AddItemOfType(DealItemTypes.AGREEMENTS,me)
    if not item then return end
    item:SetSubType(DealAgreementTypes.MAKE_PEACE)
    item:SetLocked(true)
    deal:Validate()
    DiplomacyManager.RequestSession(me,target,"MAKE_DEAL")
end)
'''
    else:
        body += f'attempt(DiplomacyManager.RequestSession,me,target,{lua(statement)})\n'
    return body


def _session_action(a: dict) -> str:
    body = _target(a["target_player"]) + f'''
local sid=session_for(target)
if sid~={a['session_id']} then return end
local statement=current_statement(target,sid)
if not statement or statement.signature~={lua(a['signature'])} then return end
local requested={lua('CHOICE_EXIT' if a['type']=='diplomacy_close' else a['response'])}
local allowed=false
for _,choice in ipairs(statement.choices) do if choice.key==requested then allowed=true;break end end
if not allowed then return end
'''
    if a["type"] == "diplomacy_close":
        return body + 'if type(DiplomacyManager.CloseSession)~="function" then return end\n_CIV6FAIR_V1.diplomacy_statements[sid]=nil\nattempt(DiplomacyManager.CloseSession,sid)'
    return body + f'''
if type(DiplomacyManager.AddResponse)~="function" then return end
local statements={{CHOICE_DECLARE_SURPRISE_WAR="DECLARE_SURPRISE_WAR",CHOICE_DECLARE_FORMAL_WAR="DECLARE_FORMAL_WAR",
    CHOICE_DECLARE_HOLY_WAR="DECLARE_HOLY_WAR",CHOICE_DECLARE_LIBERATION_WAR="DECLARE_LIBERATION_WAR",
    CHOICE_DECLARE_RECONQUEST_WAR="DECLARE_RECONQUEST_WAR",CHOICE_DECLARE_PROTECTORATE_WAR="DECLARE_PROTECTORATE_WAR",
    CHOICE_DECLARE_COLONIAL_WAR="DECLARE_COLONIAL_WAR",CHOICE_DECLARE_TERRITORIAL_WAR="DECLARE_TERRITORIAL_WAR",
    CHOICE_DECLARE_GOLDEN_AGE_WAR="DECLARE_GOLDEN_WAR",CHOICE_DECLARE_WAR_OF_RETRIBUTION="DECLARE_WAR_OF_RETRIBUTION",
    CHOICE_DECLARE_IDEOLOGICAL_WAR="DECLARE_IDEOLOGICAL_WAR",CHOICE_MAKE_PEACE="MAKE_PEACE",
    CHOICE_MAKE_DEAL="MAKE_DEAL",CHOICE_MAKE_DEMAND="MAKE_DEMAND"}}
local responses={{CHOICE_POSITIVE="POSITIVE",CHOICE_NEGATIVE="NEGATIVE",CHOICE_IGNORE="RESPONSE_IGNORE",CHOICE_STOP_ASKING="REJECTED_PERMANENT"}}
_CIV6FAIR_V1.diplomacy_statements[sid]=nil
if statements[requested] then attempt(DiplomacyManager.AddStatement,sid,me,statements[requested])
elseif requested=="CHOICE_EXIT" then attempt(DiplomacyManager.CloseSession,sid)
else attempt(DiplomacyManager.AddResponse,sid,me,responses[requested] or requested) end
'''


# Base/Assets/UI/PartialScreens/CityStates.lua:1440-1467 includes only alive
# minors whose influence component CanReceiveInfluence(). The expansion UIs
# inherit that list. Do not assume GetAliveMinors excludes Free Cities.
_CITY_STATE_HELPERS = r'''
local function city_state(id)
    if not int(id) or id<0 or id>63 or id==me or not known_player(id) then return nil end
    local other=Players[id]
    if not other or type(other.IsMajor)~="function" or other:IsMajor()~=false
        or type(other.IsAlive)~="function" or other:IsAlive()~=true
        or type(other.IsBarbarian)~="function" or other:IsBarbarian()~=false then return nil end
    -- IsFreeCities is absent in the base game; influence eligibility remains
    -- mandatory in every ruleset, before identity text or action checks.
    if type(other.IsFreeCities)=="function" and other:IsFreeCities()~=false then return nil end
    if type(other.GetInfluence)~="function" then return nil end
    local influence=other:GetInfluence()
    if not influence or type(influence.CanReceiveInfluence)~="function"
        or influence:CanReceiveInfluence()~=true then return nil end
    return other
end
local function city_state_military_allowed()
    return GameCapabilities and type(GameCapabilities.HasCapability)=="function"
        and GameCapabilities.HasCapability("CAPABILITY_MILITARY")==true
end
-- CityStates.lua:1119-1165 first chooses war OR peace from IsAtWarWith;
-- the corresponding Can... method controls that button's enabled state.
local function city_state_war_peace(id,war)
    if not city_state_military_allowed() or type(player.GetDiplomacy)~="function" then return false end
    local diplo=player:GetDiplomacy()
    if not diplo or type(diplo.IsAtWarWith)~="function" then return false end
    local at_war=diplo:IsAtWarWith(id)
    if war then
        return at_war==false and type(diplo.CanDeclareWarOn)=="function" and diplo:CanDeclareWarOn(id)==true
    end
    return at_war==true and type(diplo.CanMakePeaceWith)=="function" and diplo:CanMakePeaceWith(id)==true
end
'''


def _city_state(a: dict) -> str:
    kind = a["type"]
    body = _HELPERS + _CITY_STATE_HELPERS + f'''
local target={lua(a['target_player'])}
if not city_state(target) then return end
local params={{}}
'''
    if kind == "city_state_envoy":
        body += '''local influence=player:GetInfluence()
if influence:CanGiveInfluence()~=true or influence:GetTokensToGive()<1
    or influence:CanGiveTokensToPlayer(target)~=true then return end
params[PlayerOperations.PARAM_PLAYER_ONE]=target
'''
        op = "GIVE_INFLUENCE_TOKEN"
    elif kind == "city_state_levy":
        body += '''if not city_state_military_allowed() or player:GetInfluence():CanLevyMilitary(target)~=true then return end
params[PlayerOperations.PARAM_PLAYER_ONE]=target
'''
        op = "LEVY_MILITARY"
    else:
        war = kind == "city_state_war"
        op = "DIPLOMACY_DECLARE_WAR" if war else "DIPLOMACY_MAKE_PEACE"
        body += f'''if not city_state_war_peace(target,{lua(war)}) then return end
params[PlayerOperations.PARAM_PLAYER_ONE]=me
params[PlayerOperations.PARAM_PLAYER_TWO]=target
'''
    return body + f'''if type(PlayerOperations.{op})~="number" or type(UI.RequestPlayerOperation)~="function" then return end
attempt(UI.RequestPlayerOperation,me,PlayerOperations.{op},params)
'''


_DEAL_HELPERS = r'''
local function working(target,direction)
    if not counterpart(target) or not DealManager or not DealDirection
        or type(DealManager.GetWorkingDeal)~="function" then return nil end
    return DealManager.GetWorkingDeal(direction,me,target)
end
local function proposal_is(action,name)
    local value=DealProposalAction and DealProposalAction[name]
    return int(action) and int(value) and action==value
end
local function deal_phase(target,sid)
    if not sid or session_for(target)~=sid then return nil end
    local info=DiplomacyManager.GetSessionInfo(sid)
    local state=_CIV6FAIR_V1
    local v=state and state.deal_roles_v2 and state.deal_roles_v2[sid]
    if v and v.session==session and v.sid==sid and v.player==me
        and v.other==target and v.initiator==info.FromPlayer and v.observed==true then return v end
    -- OnShow's initial role is valid only inside the real deal panel. A generic
    -- foreign-initiated greeting/denunciation may retain an old INCOMING copy.
    -- Late attachment therefore stays unknown until a normal public deal event.
    return nil
end
local function phase_offers(v)
    -- A normal draft edit resets the stock UI to PENDING before its optional
    -- INSPECT reply. Keep the old cache alive for event delivery, but never
    -- accept its previous INCOMING copy during that asynchronous interval.
    local state=_CIV6FAIR_V1
    local waiting=state and state.deal_edited_wait_v1
    if v and waiting and waiting.session==session and waiting.player==me
        and waiting.sid==v.sid and waiting.other==v.other and waiting.phase==v then return false end
    return v and v.active==true and (proposal_is(v.action,"ACCEPTED")
        or proposal_is(v.action,"PROPOSED") or proposal_is(v.action,"ADJUSTED"))
end
local function can_edit_deal(target,v)
    if not v or v.active~=true or v.demand==true or proposal_is(v.action,"DEMANDED")
        or type(DealManager.HasPendingDeal)~="function" or DealManager.HasPendingDeal(me,target)~=false then return false end
    if phase_offers(v) then
        local incoming=working(target,DealDirection.INCOMING)
        if incoming and incoming:GetItemCount()>0 then
            return type(incoming.IsGift)=="function" and incoming:IsGift()==false
        end
    end
    return true
end
local function consume_deal_phase(v)
    -- Prevent a second response before the normal event/session transition.
    if v then v.active=false end
end
local function trade_resource(index)
    local row=GameInfo.Resources[index]
    if not row or type(player.GetResources)~="function" then return nil end
    if player:GetResources():IsResourceVisible(row.Hash)~=true then return nil end
    return row
end
local function offered_entries(target,side,kind,deal)
    local from=side=="give" and me or target
    local to=side=="give" and target or me
    if type(DealManager.GetPossibleDealItems)~="function" or type(kind)~="number" then return {} end
    return DealManager.GetPossibleDealItems(from,to,kind,deal) or {}
end
local function terms_signature(deal)
    if not deal or not DB or type(DB.MakeHash)~="function" then return nil end
    local entries={}
    for item in deal:Items() do
        if #entries>=128 then return nil end
        local war="NONE"
        if item:GetType()==DealItemTypes.AGREEMENTS and (item:GetSubType()==DealAgreementTypes.JOINT_WAR
            or item:GetSubType()==DealAgreementTypes.THIRD_PARTY_WAR) then war=tostring(item:GetParameterValue("WarType")) end
        table.insert(entries,table.concat({tostring(item:GetID()),tostring(item:GetType()),
            tostring(item:GetFromPlayerID()),tostring(item:GetSubType()),
            tostring(item:GetValueType()),tostring(item:GetAmount()),tostring(item:GetDuration()),war},":"))
    end
    table.sort(entries)
    local s=table.concat(entries,";")
    return "DEAL_"..string.format("%.0f",math.abs(DB.MakeHash("A:"..s)))
        .."_"..string.format("%.0f",math.abs(DB.MakeHash("B:"..s)))
end
local function safe_deal_item(item,target)
    local from=item:GetFromPlayerID()
    if from~=me and from~=target then return false end
    local kind=item:GetType()
    if kind==DealItemTypes.RESOURCES then return trade_resource(item:GetValueType())~=nil end
    if kind==DealItemTypes.AGREEMENTS then
        local subtype=item:GetSubType()
        if subtype==DealAgreementTypes.JOINT_WAR or subtype==DealAgreementTypes.THIRD_PARTY_WAR then
            return known_player(item:GetValueType()) and item:GetValueType()~=me
        end
        return subtype==DealAgreementTypes.OPEN_BORDERS or subtype==DealAgreementTypes.MAKE_PEACE
            or subtype==DealAgreementTypes.ALLIANCE or subtype==DealAgreementTypes.DEFENSIVE_PACT
            or subtype==DealAgreementTypes.RESEARCH_AGREEMENT
    end
    return kind==DealItemTypes.GOLD or kind==DealItemTypes.FAVOR or kind==DealItemTypes.CITIES
        or kind==DealItemTypes.GREATWORK or kind==DealItemTypes.CAPTIVE
end
'''

# GS DiplomacyDealView.lua:2290-2310 resolves resources through GameInfo;
# 2380-2395 resolves agreement subtype captions and alliance parameter names.
# Only call these display helpers AFTER safe_deal_item has authorized the term.
_DEAL_DISPLAY_HELPERS = r'''
local function rule_name(rows,value)
    local row=rows and rows[value]
    if row and type(row.Name)=="string" and row.Name~="" then return label(row.Name) end
    return nil
end
local function deal_item_display(item,fallback)
    local kind=item:GetType()
    if kind==DealItemTypes.GOLD then
        return label(item:GetDuration()>0 and "LOC_DIPLOMACY_DEAL_GOLD_PER_TURN" or "LOC_YIELD_GOLD_NAME")
    elseif kind==DealItemTypes.FAVOR then
        return label("LOC_DIPLOMATIC_FAVOR_NAME")
    elseif kind==DealItemTypes.RESOURCES then
        -- Recheck the reveal gate before reading a resource's display name.
        local row=trade_resource(item:GetValueType())
        return row and (rule_name(GameInfo.Resources,item:GetValueType()) or row.ResourceType) or fallback
    elseif kind==DealItemTypes.GREATWORK then
        -- GS DiplomacyDealView:2505-2510 displays the offered instance's
        -- caption. Its subtype lookup at 2495 supplies the icon, not title.
        -- Do not guess a title from a missing/default subtype or enumerate
        -- foreign buildings to resolve the runtime work index.
        if type(item.GetValueTypeNameID)=="function" then
            local ok,text=pcall(item.GetValueTypeNameID,item)
            if ok and type(text)=="string" and text~="" then return label(text) end
        end
        return fallback
    elseif kind==DealItemTypes.CITIES then
        return label("LOC_DIPLOMACY_DEAL_CITIES")
    elseif kind==DealItemTypes.CAPTIVE then
        return label("LOC_DIPLOMACY_DEAL_CAPTIVES")
    elseif kind==DealItemTypes.AGREEMENTS then
        local subtype=item:GetSubType()
        local name=nil
        if type(item.GetSubTypeNameID)=="function" then
            local ok,text=pcall(item.GetSubTypeNameID,item)
            if ok and type(text)=="string" and text~="" then name=label(text) end
        end
        name=name or rule_name(GameInfo.DiplomaticActions,subtype)
        if not name then
            for _,key in ipairs({"OPEN_BORDERS","MAKE_PEACE","ALLIANCE","DEFENSIVE_PACT","RESEARCH_AGREEMENT","JOINT_WAR","THIRD_PARTY_WAR"}) do
                if subtype==DealAgreementTypes[key] then name=key;break end
            end
        end
        local parameter=nil
        if subtype==DealAgreementTypes.ALLIANCE then
            parameter=rule_name(GameInfo.Alliances,item:GetValueType())
        elseif subtype==DealAgreementTypes.RESEARCH_AGREEMENT then
            parameter=rule_name(GameInfo.Technologies,item:GetValueType())
        elseif subtype==DealAgreementTypes.JOINT_WAR or subtype==DealAgreementTypes.THIRD_PARTY_WAR then
            local id=item:GetValueType()
            -- Repeat HasMet before the only new non-rule lookup in this helper.
            if known_player(id) and id~=me then
                local config=PlayerConfigurations[id]
                if config and type(config.GetCivilizationShortDescription)=="function" then
                    parameter=label(config:GetCivilizationShortDescription())
                end
            end
        end
        return (name or fallback)..(parameter and " / "..parameter or "")
    end
    return fallback
end
'''


def _deal(a: dict) -> str:
    body = _target(a["target_player"]) + _DEAL_HELPERS + '''
if other:IsMajor()~=true or other:IsAlive()~=true then return end
local activeSession=session_for(target)
if not activeSession then return end
local phase=deal_phase(target,activeSession)
local deal=working(target,DealDirection.OUTGOING)
if not deal then return end
'''
    kind = a["type"]
    if kind != "deal_respond":
        body += '''
if not can_edit_deal(target,phase) then return end
'''
    if kind == "deal_clear":
        return body + '''
if DealManager.HasPendingDeal(me,target)==true then return end
attempt(DealManager.ClearWorkingDeal,DealDirection.OUTGOING,me,target)
'''
    if kind == "deal_remove_item":
        return body + f'''
if DealManager.HasPendingDeal(me,target)==true then return end
for item in deal:Items() do
    if item:GetID()=={a['item_id']} and safe_deal_item(item,target) and item:IsLocked()~=true then
        attempt(deal.RemoveItemByID,deal,{a['item_id']})
        return
    end
end
'''
    if kind == "deal_send":
        return body + '''
if DealManager.HasPendingDeal(me,target)==true or deal:GetItemCount()<1 or deal:IsValid()~=true then return end
for item in deal:Items() do if not safe_deal_item(item,target) then return end end
if type(deal.HasUnacceptableItems)=="function" and deal:HasUnacceptableItems()==true then return end
local operation=DealProposalAction.PROPOSED
if phase_offers(phase) then operation=DealProposalAction.ADJUSTED
elseif not (proposal_is(phase.action,"PENDING") or proposal_is(phase.action,"REJECTED")
    or proposal_is(phase.action,"EQUALIZE_FAILED")) then return end
if not int(operation) then return end
attempt(DealManager.SendWorkingDeal,operation,me,target)
'''
    if kind == "deal_respond":
        response = "ACCEPTED" if a["accept"] else "REJECTED"
        body += f'''
local sid=session_for(target)
if sid~={a['session_id']} then return end
if not phase_offers(phase) or type(DealManager.HasPendingDeal)~="function"
    or DealManager.HasPendingDeal(me,target)~=false then return end
local incoming=working(target,DealDirection.INCOMING)
if not incoming then return end
for item in incoming:Items() do if not safe_deal_item(item,target) then return end end
if terms_signature(incoming)~={lua(a['signature'])} then return end
'''
        if a["accept"]:
            body += '''
if incoming:IsValid()~=true or incoming:GetItemCount()<1 then return end
if type(incoming.HasUnacceptableItems)=="function" and incoming:HasUnacceptableItems()==true then return end
for item in incoming:Items() do if not safe_deal_item(item,target) then return end end
-- Stock UI copies the incoming offer before accepting. No AI equalization oracle.
if type(DealManager.CopyIncomingToOutgoingWorkingDeal)~="function" then return end
DealManager.CopyIncomingToOutgoingWorkingDeal(me,target)
if DealManager.AreWorkingDealsEqual(me,target)~=true then return end
if deal_phase(target,sid)~=phase or not phase_offers(phase) or DealManager.HasPendingDeal(me,target)~=false
    or not int(DealProposalAction.ACCEPTED) then return end
for item in incoming:Items() do if not safe_deal_item(item,target) then return end end
'''
            body += f'if terms_signature(incoming)~={lua(a["signature"])} then return end\n'
        if not a["accept"]:
            # Single-player AI refusal follows the regular OnRefuseDeal path,
            # not the force-close REJECTED transport operation.
            return body + '''
if phase.initiator==target then
    -- GS OnRefuseDeal has a distinct normal refusal for a locally offered
    -- unacceptable item; this is not the force-close REJECTED operation.
    if type(deal.HasUnacceptableItems)=="function" and deal:HasUnacceptableItems()==true then
        for item in deal:Items() do
            if not safe_deal_item(item,target) then return end
            if item:GetFromPlayerID()==me then
                if type(item.IsUnacceptable)~="function" then return end
                if item:IsUnacceptable()==true then
                    if not int(DealProposalAction.REJECTED_PERMANENT) then return end
                    consume_deal_phase(phase)
                    attempt(DealManager.SendWorkingDeal,DealProposalAction.REJECTED_PERMANENT,me,target)
                    return
                end
            end
        end
    end
    if type(DiplomacyManager.AddResponse)~="function" then return end
    consume_deal_phase(phase)
    attempt(DiplomacyManager.AddResponse,sid,me,"NEGATIVE")
else
    if type(DiplomacyManager.CloseSession)~="function" then return end
    consume_deal_phase(phase)
    attempt(DiplomacyManager.CloseSession,sid)
end
'''
        return body + f'consume_deal_phase(phase)\nattempt(DealManager.SendWorkingDeal,DealProposalAction.{response},me,target)\n'
    # Adding an authored item edits only the user's outgoing negotiating draft.
    dtype = _TRADE_KINDS[a["kind"]]
    body += f'''
if DealManager.HasPendingDeal(me,target)==true then return end
local side={lua(a['side'])}
local from=side=="give" and me or target
local itemType=DealItemTypes.{dtype}
if type(itemType)~="number" then return end
local entries=offered_entries(target,side,itemType,deal)
local chosen=nil
for _,entry in ipairs(entries) do
    if '''
    if a["kind"] in {"gold", "favor"}:
        body += f'entry.Duration=={a["duration"]}'
    elif a["kind"] == "agreement":
        body += f'entry.SubType==DealAgreementTypes.{a["agreement"]} and entry.Duration=={a["duration"]}'
    else:
        body += f'entry.ForType=={a["value"]}'
    body += ''' then
        if entry.IsValid==true or (DealValidationResult and entry.ValidationResult==DealValidationResult.MISSING_DEPENDENCY) then
            chosen=entry; break
        end
    end
end
if not chosen then return end
'''
    if a["kind"] == "resource":
        body += f'''local resource=trade_resource({a['value']})
if not resource or {a['amount']}<1 or {a['amount']}>chosen.MaxAmount then return end
local duration=resource.ResourceClassType=="RESOURCECLASS_STRATEGIC" and 0 or 30
if {a['duration']}~=duration then return end
'''
    if a["kind"] in {"gold", "favor"}:
        body += f'if {a["amount"]}<1 then return end\n'
    if a["kind"] == "agreement" and a["agreement"] in {"ALLIANCE", "RESEARCH_AGREEMENT"}:
        table = "Alliances" if a["agreement"] == "ALLIANCE" else "Technologies"
        body += f'''
local agreementRow=GameInfo.{table}[{a['value']}]
if not agreementRow then return end
local choices=DealManager.GetPossibleDealItems(from,side=="give" and target or me,
    itemType,DealAgreementTypes.{a['agreement']},deal) or {{}}
local permitted=false
local agreementValue=nil
for _,entry in ipairs(choices) do
    local row=GameInfo.{table}[entry.ForType]
    if row and row.Index==agreementRow.Index and entry.IsValid~=false then
        permitted=true;agreementValue=entry.ForType;break
    end
end
if not permitted then return end
'''
    if a["kind"] == "city":
        body += f'local item=deal:AddItemOfType(itemType,from,side=="give" and target or me,chosen.SubType,{a["value"]})\n'
    else:
        body += 'local item=deal:AddItemOfType(itemType,from)\n'
    body += f'''
if not item then return end
item:SetDuration({a['duration']})
'''
    if a["kind"] == "agreement":
        body += f'item:SetSubType(DealAgreementTypes.{a["agreement"]})\n'
        if a["agreement"] in {"ALLIANCE", "RESEARCH_AGREEMENT"}:
            body += 'item:SetValueType(agreementValue)\n'
    elif a["kind"] not in {"gold", "favor"}:
        body += f'item:SetValueType({a["value"]})\n'
        if a["kind"] == "city":
            body += 'if chosen.SubType~=nil then item:SetSubType(chosen.SubType) end\n'
        elif a["kind"] == "great_work":
            body += 'item:SetSubType(chosen.ForTypeDescriptionID)\n'
    if a["kind"] in {"gold", "favor", "resource"}:
        body += f'''if {a['amount']}>item:GetMaxAmount() then deal:RemoveItemByID(item:GetID()); return end
item:SetAmount({a['amount']})
'''
    return body + '''
deal:Validate()
-- A draft may need its reciprocal term; validation still governs submission.
out.accepted=true
'''


def _war_deal(a: dict, *, query: bool = False) -> str:
    body = _target(a["target_player"]) + _DEAL_HELPERS + f'''
if not session_for(target) or other:IsMajor()~=true then return end
local deal=working(target,DealDirection.OUTGOING)
if not deal then return end
local side={lua(a['side'])}
local from=side=="give" and me or target
local to=side=="give" and target or me
local agreement=DealAgreementTypes.{a['agreement']}
if not agreement then return end
local entries=DealManager.GetPossibleDealItems(from,to,DealItemTypes.AGREEMENTS,agreement,deal) or {{}}
'''
    if query:
        return body + f'''
out.supported=true
out.decision_mode="diplomacy"
for index,entry in ipairs(entries) do
    local enemy=entry.ForType
    if known_player(enemy) and enemy~=me and enemy~=target and entry.IsValid~=false then
        local war=entry.Parameters and GameInfo.Wars[entry.Parameters.WarType]
        if war then
            local name=label(PlayerConfigurations[enemy]:GetCivilizationShortDescription())..": "..label(war.Name)
            add("war_"..index,name,nil,{{type="deal_add_war",target_player=target,side=side,
                agreement={lua(a['agreement'])},enemy=enemy,war=war.WarType,duration=entry.Duration or 30}})
        end
    end
end
'''
    return body + f'''
if not known_player({a['enemy']}) or {a['enemy']}==me or {a['enemy']}==target then return end
if DealManager.HasPendingDeal(me,target)==true then return end
if not can_edit_deal(target,deal_phase(target,session_for(target))) then return end
local selected=nil
for _,entry in ipairs(entries) do
    if entry.ForType=={a['enemy']} and entry.IsValid~=false then
        local row=entry.Parameters and GameInfo.Wars[entry.Parameters.WarType]
        if row and row.WarType=={lua(a['war'])} and (entry.Duration or 30)=={a['duration']} then selected=entry;break end
    end
end
if not selected then return end
attempt(function()
    local item=deal:AddItemOfType(DealItemTypes.AGREEMENTS,from)
    if not item then return end
    item:SetSubType(agreement)
    item:SetValueType({a['enemy']})
    item:SetDuration({a['duration']})
    item:SetParameterValue("WarType",selected.Parameters.WarType)
    deal:Validate()
end)
'''


_WORK_HELPERS = r'''
local function full(bldgs,building)
    local n=bldgs:GetNumGreatWorkSlots(building)
    if not int(n) or n<1 or n>64 then return false end
    for i=0,n-1 do if bldgs:GetGreatWorkInSlot(building,i)<0 then return false end end
    return true
end
local function work_at(bldgs,building,slot)
    local n=bldgs:GetNumGreatWorkSlots(building)
    if not int(n) or n>64 or slot<0 or slot>=n then return nil end
    local id=bldgs:GetGreatWorkInSlot(building,slot)
    if not int(id) or id<0 then return nil end
    local row=GameInfo.GreatWorks[bldgs:GetGreatWorkTypeFromIndex(id)]
    if not row then return nil end
    return id,row
end
local function movable(bldgs,building,slot)
    local id,row=work_at(bldgs,building,slot)
    if not id then return false end
    local object=row.GreatWorkObjectType
    if object=="GREATWORKOBJECT_ARTIFACT" and not full(bldgs,building) then return false end
    if object=="GREATWORKOBJECT_SCULPTURE" or object=="GREATWORKOBJECT_LANDSCAPE"
        or object=="GREATWORKOBJECT_PORTRAIT" or object=="GREATWORKOBJECT_RELIGIOUS" then
        local lock=GlobalParameters.GREATWORK_ART_LOCK_TIME or 10
        if bldgs:GetTurnFromIndex(id)+lock>turn then return false end
    end
    return true
end
local function compatible(bldgs,building,slot,object)
    local kind=GameInfo.GreatWorkSlotTypes[bldgs:GetGreatWorkSlotType(building,slot)]
    if not kind then return false end
    for row in GameInfo.GreatWork_ValidSubTypes() do
        if row.GreatWorkSlotType==kind.GreatWorkSlotType and row.GreatWorkObjectType==object then return true end
    end
    return false
end
'''


def _move_work(a: dict) -> str:
    return _HELPERS + _WORK_HELPERS + f'''
local src=find_owned("Cities",{a['source_city']})
local dst=find_owned("Cities",{a['destination_city']})
if not src or not dst then return end
local sb,db=src:GetBuildings(),dst:GetBuildings()
local srcBuilding,dstBuilding=GameInfo.Buildings[{lua(a['source_building'])}],GameInfo.Buildings[{lua(a['destination_building'])}]
if not srcBuilding or not dstBuilding or sb:HasBuilding(srcBuilding.Index)~=true
    or db:HasBuilding(dstBuilding.Index)~=true then return end
local si,di=srcBuilding.Index,dstBuilding.Index
local ss,ds={a['source_slot']},{a['destination_slot']}
if src:GetID()==dst:GetID() and si==di and ss==ds then return end
local work,row=work_at(sb,si,ss)
if not work or not movable(sb,si,ss) then return end
local n=db:GetNumGreatWorkSlots(di)
if not int(n) or n>64 or ds>=n then return end
if not compatible(db,di,ds,row.GreatWorkObjectType) then return end
local other,otherRow=work_at(db,di,ds)
if row.GreatWorkObjectType=="GREATWORKOBJECT_ARTIFACT" and not full(db,di) then return end
if other and (not movable(db,di,ds) or not compatible(sb,si,ss,otherRow.GreatWorkObjectType)) then return end
local p={{}}
p[PlayerOperations.PARAM_PLAYER_ONE]=me
p[PlayerOperations.PARAM_CITY_SRC]=src:GetID()
p[PlayerOperations.PARAM_CITY_DEST]=dst:GetID()
p[PlayerOperations.PARAM_BUILDING_SRC]=si
p[PlayerOperations.PARAM_BUILDING_DEST]=di
p[PlayerOperations.PARAM_GREAT_WORK_INDEX]=work
p[PlayerOperations.PARAM_SLOT]=ds
attempt(UI.RequestPlayerOperation,me,PlayerOperations.MOVE_GREAT_WORK,p)
'''


def _artifact(a: dict) -> str:
    return _HELPERS + f'''
local unit=player:GetUnits():GetNextExtractingArchaeologist()
if not unit or unit:GetOwner()~=me or unit:GetID()~={a['unit_id']} then return end
local artifact=Game.GetArtifactByIndex(unit:GetArchaeology():GetArtifactIndex())
if not artifact then return end
local choice={a['choice']}
if choice~=1 and choice~=2 then return end
if choice==2 and (artifact.Type==1 or artifact.Type==2 or artifact.Type==5) then return end
local id=choice==1 and artifact.ActingPlayerID or artifact.TargetPlayerID
if not int(id) then return end
local p={{}}
p[PlayerOperations.PARAM_PLAYER_ONE]=id
attempt(UI.RequestPlayerOperation,me,PlayerOperations.CHOOSE_ARTIFACT_PLAYER,p)
'''


_CONGRESS_HELPERS = r'''
local function congress_stage()
    if not Game.GetWorldCongress or not Game.GetCurrentTurnSegment or not DB or not DB.MakeHash
        or player:IsMajor()~=true or GameConfiguration.IsPaused()~=false then return nil end
    local segment=Game.GetCurrentTurnSegment()
    if segment==DB.MakeHash("TURNSEG_WORLDCONGRESS_1") then return 1 end
    if segment==DB.MakeHash("TURNSEG_WORLDCONGRESS_2") then return 2 end
    return nil
end
local function proposals(wc,available)
    local result={}
    local data=available and wc:GetEmergencies(me) or wc:GetProposals(me)
    if type(data)~="table" or type(data.Proposals)~="table" then return result end
    for _,category in pairs(data.Proposals) do
        for _,p in pairs(category.ProposalsOfType or {}) do
            if #result>=128 then error("unavailable") end
            table.insert(result,{Type=p.Type,Target=p.Target,Sender=p.Sender,
                Name=p.Name,Disabled=p.Disabled,VotingRestriction=p.VotingRestriction,
                ProposalBlockerType=p.ProposalBlockerType,TypeName=p.TypeName,
                EmergencyType=p.EmergencyType,favor_cost=category.FavorCost})
        end
    end
    table.sort(result,function(a,b)
        local ak=table.concat({tostring(a.Type),tostring(a.Target),tostring(a.Sender)},":")
        local bk=table.concat({tostring(b.Type),tostring(b.Target),tostring(b.Sender)},":")
        return ak<bk
    end)
    return result
end
local function can_vote(p,direction)
    if p.Disabled then return false end
    local blocker=p.VotingRestriction and GameInfo.VotingBlockers[p.VotingRestriction]
    return not blocker or (direction==1 and not blocker.NoUpvote) or (direction==-1 and not blocker.NoDownvote)
end
'''


def _congress_ballot(a: dict) -> str:
    return _HELPERS + _CONGRESS_HELPERS + f'''
local stage=congress_stage()
if not stage then return end
if type(UI.RequestPlayerOperation)~="function" or type(UI.RequestAction)~="function"
    or type(PlayerOperations.WORLD_CONGRESS_RESOLUTION_VOTE)~="number"
    or type(PlayerOperations.WORLD_CONGRESS_DISCUSSION_VOTE)~="number"
    or type(PlayerOperations.WORLD_CONGRESS_SUBMIT_TURN)~="number"
    or not ActionTypes or type(ActionTypes.ACTION_ENDTURN)~="number" then return end
local wc=Game.GetWorldCongress()
local offered=wc:GetResolutions(me)
local proposed=proposals(wc)
local costs=wc:GetVotesandFavorCost(me)
if type(offered)~="table" or type(costs)~="table" then return end
local votes={lua(a['resolutions'])}
local discussions={lua(a['discussions'])}
local prepared={{}}
local seen={{}}
local spent=0
for _,v in ipairs(votes) do
    if v.votes<1 or v.votes>1000 or (type(costs.MaxVotes)=="number" and v.votes>costs.MaxVotes)
        or (v.choice~=1 and v.choice~=2) or seen[v.resolution] then return end
    local row=GameInfo.Resolutions[v.resolution]
    local found=nil
    for key,res in pairs(offered) do
        if type(key)=="number" and row and (res.Type==row.ResolutionType or res.Type==row.Index or res.Type==row.Hash) then found=res;break end
    end
    if not found or type(found.PossibleTargets)~="table" or found.PossibleTargets[v.selection+1]==nil then return end
    local cost=costs[v.votes-1]
    if type(cost)~="number" or cost<0 then return end
    spent=spent+cost
    seen[v.resolution]=true
    local p={{}}
    p[PlayerOperations.PARAM_RESOLUTION_TYPE]=row.Hash
    p[PlayerOperations.PARAM_WORLD_CONGRESS_VOTES]=v.votes
    p[PlayerOperations.PARAM_RESOLUTION_OPTION]=v.choice
    p[PlayerOperations.PARAM_RESOLUTION_SELECTION]=v.selection
    table.insert(prepared,{{operation=PlayerOperations.WORLD_CONGRESS_RESOLUTION_VOTE,params=p}})
end
-- Every available resolution needs a choice, exactly as the stock popup.
for key,res in pairs(offered) do
    if type(key)=="number" then
        local row=GameInfo.Resolutions[res.Type]
        if not row or not seen[row.ResolutionType] then return end
    end
end
local discussed={{}}
for _,v in ipairs(discussions) do
    if v.votes<1 or v.votes>1000 or (type(costs.MaxVotes)=="number" and v.votes>costs.MaxVotes)
        or (v.direction~=1 and v.direction~=-1) or discussed[v.proposal] then return end
    local proposal=proposed[v.proposal+1]
    if not proposal or not can_vote(proposal,v.direction) then return end
    local cost=costs[v.votes-1]
    if type(cost)~="number" or cost<0 then return end
    spent=spent+cost
    discussed[v.proposal]=true
    local p={{}}
    p[PlayerOperations.PARAM_PLAYER_ONE]=proposal.Sender
    p[PlayerOperations.PARAM_PLAYER_TWO]=proposal.Target
    p[PlayerOperations.PARAM_WORLD_CONGRESS_VOTES]=v.votes*v.direction
    table.insert(prepared,{{operation=PlayerOperations.WORLD_CONGRESS_DISCUSSION_VOTE,params=p}})
end
for index,p in ipairs(proposed) do
    if (can_vote(p,1) or can_vote(p,-1)) and not discussed[index-1] then return end
end
if spent>player:GetFavor() then return end
if type(UI.RequestPlayerOperation)~="function" or type(UI.RequestAction)~="function"
    or type(PlayerOperations.WORLD_CONGRESS_SUBMIT_TURN)~="number" then return end
-- No mutation occurs before the entire ballot and total favor budget validate.
attempt(function()
    for _,request in ipairs(prepared) do UI.RequestPlayerOperation(me,request.operation,request.params) end
    UI.RequestPlayerOperation(me,PlayerOperations.WORLD_CONGRESS_SUBMIT_TURN,{{}})
    UI.RequestAction(ActionTypes.ACTION_ENDTURN)
end)
'''


def _congress_propose(a: dict) -> str:
    return _HELPERS + _CONGRESS_HELPERS + f'''
if not Game.GetWorldCongress or congress_stage()~=nil then return end
local wc=Game.GetWorldCongress()
local p=proposals(wc,true)[{a['proposal']}+1]
if not p or p.Disabled or type(p.favor_cost)~="number" or p.favor_cost<0
    or player:GetFavor()<p.favor_cost then return end
local params={{}}
params[PlayerOperations.PARAM_OTHER_PLAYER]=p.Target
params[PlayerOperations.PARAM_DISCUSSION_TYPE]=p.Type
attempt(UI.RequestPlayerOperation,me,PlayerOperations.WORLD_CONGRESS_DISCUSSION_SELECTION,params)
'''


def _congress_acknowledge(_: dict) -> str:
    return _HELPERS + _CONGRESS_HELPERS + '''
if congress_stage()~=nil or type(Game.GetWorldCongress)~="function" then return end
local blocker=NotificationManager.GetFirstEndTurnBlocking(me)
if blocker~=EndTurnBlockingTypes.ENDTURN_BLOCKING_WORLD_CONGRESS_LOOK then return end
-- Same operation as closing the standard Available Proposals panel.
attempt(UI.RequestPlayerOperation,me,PlayerOperations.WORLD_CONGRESS_LOOKED_AT_AVAILABLE,{})
'''


def _emergency(a: dict, *, query: bool = False) -> str:
    body = _HELPERS + '''
if type(Game.GetEmergencyManager)~="function" then return end
local manager=Game.GetEmergencyManager()
if not manager or type(manager.GetEmergencyInfoTable)~="function" then return end
local emergencies=manager:GetEmergencyInfoTable(me)
if type(emergencies)~="table" then return end
-- Both RF and GS use EmergencyAlliances. Accessing the nonexistent
-- GameInfo.Emergencies table can itself throw in the native GameInfo proxy.
local rulesOK,definitions=pcall(function() return GameInfo.EmergencyAlliances end)
if not rulesOK or not definitions then return end
local function menu_entry(entry)
    if type(entry)~="table" or not int(entry.EmergencyType)
        or not int(entry.TargetID) or entry.TargetID< -1 or entry.TargetID>63 then return nil end
    local ok,def=pcall(function() return definitions[entry.EmergencyType] end)
    if not ok or not def or type(def.Name)~="string" then return nil end
    return entry,def
end
local function each_menu_entry(callback)
    -- Stock UI ignores the native iterator key. Build public ordinals from
    -- the same validated traversal for reads and actions; never assume its
    -- keys are 1-based, contiguous, or Lua integers.
    local ordinal=0
    local examined=0
    for _,entry in ipairs(emergencies) do
        examined=examined+1
        if examined>128 then error("unavailable") end
        local candidate,def=menu_entry(entry)
        if candidate then
            if callback(ordinal,candidate,def)==false then return end
            ordinal=ordinal+1
        end
    end
end
'''
    if query:
        return body + '''
out.supported=true
each_menu_entry(function(ordinal,candidate,def)
        local name=label(def.Name)
        local id="emergency_"..ordinal
        local stage="unknown"
        if candidate.HasBegun==false then stage="decision_required"
        elseif candidate.HasBegun==true then
            stage="in_progress"
            if int(candidate.TurnsLeft) and candidate.TurnsLeft<0 then stage="completed" end
        end
        add(id,name,stage)
        if int(candidate.TurnsLeft) and candidate.TurnsLeft>=0 then
            add(id..":turns_left",name..": remaining turns",candidate.TurnsLeft)
        end
        -- WorldCrisisSupport.ProcessEmergency explicitly derives inputRequired
        -- as not HasBegun. The source is the LOCAL menu table, not a global
        -- event list or an inferred MemberIDs/invitation/score relation.
        if candidate.HasBegun==false then
            add(id.."_join",name..": join",nil,{type="emergency_respond",emergency=ordinal,choice="join"})
            add(id.."_reject",name..": decline",nil,{type="emergency_respond",emergency=ordinal,choice="reject"})
        elseif candidate.HasBegun==true then
            add(id.."_acknowledge",name..": acknowledge",nil,{type="emergency_respond",emergency=ordinal,choice="acknowledge"})
        end
end)
'''
    return body + f'''
local entry=nil
each_menu_entry(function(ordinal,candidate)
    if ordinal=={a['emergency']} then entry=candidate;return false end
end)
if not entry then return end
local choice={lua(a['choice'])}
if choice=="acknowledge" then
    if entry.HasBegun~=true then return end
elseif entry.HasBegun~=false then return end
local p={{}}
p[PlayerOperations.PARAM_OTHER_PLAYER]=entry.TargetID
p[PlayerOperations.PARAM_EMERGENCY_TYPE]=entry.EmergencyType
local operation=choice=="reject" and PlayerOperations.REJECT_EMERGENCY or PlayerOperations.ACCEPT_EMERGENCY
if not int(operation) or type(UI.RequestPlayerOperation)~="function" then return end
attempt(UI.RequestPlayerOperation,me,operation,p)
'''


def _diplo_query(a: dict) -> str:
    body = _target(a["target_player"]) + 'out.supported=true\n'
    for key, (_, rule) in _STATEMENTS.items():
        body += f'''
if other:IsMajor()==true and diplomatic_valid({lua(rule)},target) then
    local row=GameInfo.DiplomaticActions[{lua(rule)}]
    add({lua(key)},label(row.Name),nil,{{type="diplomacy_statement",target_player=target,statement={lua(key)}}})
end
'''
    return body + '''
local sid=session_for(target)
if sid then
    add_conversation(target,sid)
end
'''


def _diplomacy_sessions(_: dict) -> str:
    return _HELPERS + '''
if not DiplomacyManager or not DiplomacyManager.FindOpenSessionID then return end
out.supported=true
for id=0,63 do
    if id~=me and known_player(id) then
        local sid=session_for(id)
        if sid then add_conversation(id,sid) end
    end
end
'''


def _city_states_query(_: dict) -> str:
    return _HELPERS + _CITY_STATE_HELPERS + CITY_STATE_DETAILS + ENVOY_DEFER_HELPERS + '''
if not PlayerManager or type(PlayerManager.GetAliveMinors)~="function" then return end
out.supported=true
local influence=player:GetInfluence()
add("envoys","Unassigned envoys",influence:GetTokensToGive())
if unconsidered_envoys() then
    add("defer_envoys","保留使者并确认已考虑派遣",nil,{type="city_state_defer_envoys"})
end
for _,candidate in ipairs(PlayerManager.GetAliveMinors()) do
    local id=candidate:GetID()
    -- The ID is used only for the local knowledge gate; no unseen attributes.
    local other=city_state(id)
    if other then
        local config=PlayerConfigurations[id]
        local name=label(config:GetCivilizationShortDescription())
        local function offer(kind,label)
            add(kind.."_"..id,name..": "..label,nil,{type=kind,target_player=id})
        end
        local can_envoy=influence:CanGiveInfluence()==true and influence:GetTokensToGive()>0 and influence:CanGiveTokensToPlayer(id)==true
        local can_levy=city_state_military_allowed()==true and influence:CanLevyMilitary(id)==true
        local can_war=city_state_war_peace(id,true)==true
        local can_peace=city_state_war_peace(id,false)==true
        city_state_details(id,other,name,influence,can_envoy,can_levy,can_war,can_peace)
        if can_envoy then offer("city_state_envoy","Send one envoy") end
        if can_levy then offer("city_state_levy","Levy military") end
        if can_war then offer("city_state_war","Declare war") end
        if can_peace then offer("city_state_peace","Make peace") end
    end
end
'''


def _deal_options(a: dict) -> str:
    dtype = _TRADE_KINDS[a["kind"]]
    return _target(a["target_player"]) + _DEAL_HELPERS + f'''
if other:IsMajor()~=true then return end
local deal=working(target,DealDirection.OUTGOING)
if not deal or not DealItemTypes.{dtype} then return end
out.supported=true
if session_for(target) then out.decision_mode="diplomacy" end
local side={lua(a['side'])}
local kind={lua(a['kind'])}
for index,entry in ipairs(offered_entries(target,side,DealItemTypes.{dtype},deal)) do
    local show=entry.IsValid==true or (DealValidationResult and entry.ValidationResult==DealValidationResult.MISSING_DEPENDENCY)
    local value=entry.ForType or 0
    local name=entry.ForTypeName or kind
    local amount=entry.MaxAmount
    local agreement="NONE"
    local duration=entry.Duration or 0
    if kind=="resource" then
        local row=trade_resource(value)
        show=show and row~=nil
        if row then name=row.Name;duration=row.ResourceClassType=="RESOURCECLASS_STRATEGIC" and 0 or 30 end
    elseif kind=="agreement" then
        show=false
        for _,sub in ipairs({lua(list(_AGREEMENTS))}) do
            if entry.SubType==DealAgreementTypes[sub] then agreement=sub;show=entry.IsValid==true;name=entry.SubTypeName or sub end
        end
    end
    if show then
        local action={{type="deal_add_item",target_player=target,side=side,kind=kind,
            value=math.max(0,math.floor(value)),amount=1,duration=math.max(0,math.floor(duration)),agreement=agreement}}
        if agreement=="ALLIANCE" or agreement=="RESEARCH_AGREEMENT" then
            local from=side=="give" and me or target
            local to=side=="give" and target or me
            local values=DealManager.GetPossibleDealItems(from,to,DealItemTypes.AGREEMENTS,DealAgreementTypes[agreement],deal) or {{}}
            for _,choice in ipairs(values) do
                local row=agreement=="ALLIANCE" and GameInfo.Alliances[choice.ForType] or GameInfo.Technologies[choice.ForType]
                if row and choice.IsValid~=false then
                    action.value=row.Index
                    local copy={{}};for k,v in pairs(action) do copy[k]=v end
                    add(agreement.."_"..row.Index,label(row.Name),nil,copy)
                end
            end
        else
            add("offer_"..index,label(name),kind=="resource" and amount or nil,action)
        end
    end
end
'''


def _deal_state(a: dict) -> str:
    return _target(a["target_player"]) + _DEAL_HELPERS + _DEAL_DISPLAY_HELPERS + '''
if not DealDirection or not DealItemTypes then return end
out.supported=true
local sid=session_for(target)
if sid then out.decision_mode="diplomacy" end
local phase=deal_phase(target,sid)
local mayEdit=can_edit_deal(target,phase)
local incomingSeen=false
for _,direction in ipairs({"OUTGOING","INCOMING"}) do
    local deal=nil
    -- A self-authored/inspected working copy is not a received offer. Preserve
    -- the existing safe display when session metadata is unavailable, but it
    -- cannot authorize any response.
    if direction=="OUTGOING" or not sid or phase_offers(phase) then
        deal=working(target,DealDirection[direction])
    end
    if deal then
        local allSafe=true
        for item in deal:Items() do
            if safe_deal_item(item,target) then
                local kind=item:GetType()
                local name=""
                for _,k in ipairs({"GOLD","FAVOR","RESOURCES","AGREEMENTS","CITIES","GREATWORK","CAPTIVE"}) do
                    if kind==DealItemTypes[k] then name=k end
                end
                local from=item:GetFromPlayerID()==me and "give" or "receive"
                local detail=from.." "..name.." value="..tostring(item:GetValueType()).." amount="..tostring(item:GetAmount()).." turns="..tostring(item:GetDuration()).." subtype="..tostring(item:GetSubType())
                if kind==DealItemTypes.AGREEMENTS and (item:GetSubType()==DealAgreementTypes.JOINT_WAR
                    or item:GetSubType()==DealAgreementTypes.THIRD_PARTY_WAR) then
                    local war=GameInfo.Wars[item:GetParameterValue("WarType")]
                    if war then detail=detail.." war="..war.WarType end
                end
                local action=nil
                if direction=="OUTGOING" and mayEdit and item:IsLocked()~=true then action={type="deal_remove_item",target_player=target,item_id=item:GetID()} end
                local display=deal_item_display(item,name)
                local summary=from.." "..display.." amount="..tostring(item:GetAmount()).." turns="..tostring(item:GetDuration())
                add_item({id=direction.."_"..item:GetID(),name=summary,description=detail,action=action,scope="self",owner_id=me})
            else allSafe=false end
        end
        if direction=="INCOMING" then
            incomingSeen=true
            if not allSafe then
                -- Never compute a fingerprint or disclose the category, count
                -- or values of filtered terms. A visible subset is not a full
                -- offer and must not be used to authorize acceptance.
                add("incoming_response_status","当前报价含按玩家信息权限规则过滤的条款，展示内容不完整，不能接受。可使用当前弹窗提供的正常拒绝按钮。","filtered_terms")
            elseif not sid then
                add("incoming_response_status","当前没有已验证的本方外交会话，暂不能回应报价。","session_unavailable")
            elseif type(DealManager.HasPendingDeal)~="function" or DealManager.HasPendingDeal(me,target)~=false then
                add("incoming_response_status","当前交易仍在等待原版处理，不能再次回应。","pending")
            else
                local sig=terms_signature(deal)
                if not sig then
                    add("incoming_response_status","无法绑定当前报价条款，暂不能回应。","signature_unavailable")
                else
                    add("reject","Reject current incoming offer",nil,{type="deal_respond",target_player=target,session_id=sid,signature=sig,accept=false})
                    if deal:GetItemCount()>0 and deal:IsValid()==true
                        and not (type(deal.HasUnacceptableItems)=="function" and deal:HasUnacceptableItems()==true) then
                        add("accept","Accept current incoming offer",nil,{type="deal_respond",target_player=target,session_id=sid,signature=sig,accept=true})
                        add("incoming_response_status","当前完整报价可使用本次返回的接受或拒绝动作回应。","ready")
                    else
                        add("incoming_response_status","当前报价尚未通过原版有效性检查或没有条款，可拒绝，不能接受。","invalid_offer")
                    end
                end
            end
        end
    end
end
if not incomingSeen then
    if sid and not phase then
        add("incoming_response_status","尚未观察到当前会话的原版交易面板或报价事件，请重新打开正常交易面板。","phase_unavailable")
    elseif phase and phase.active~=true then
        add("incoming_response_status","当前交易面板已退出或已回应，工作副本不能再次接受。","conversation_closed")
    elseif phase and phase.initiator==me and (phase.action==nil or proposal_is(phase.action,"PENDING")) then
        add("incoming_response_status","当前是本方发起的交易草案，尚无已确认可接受的对方报价。","outgoing_draft")
    elseif phase and not phase_offers(phase) then
        add("incoming_response_status","原版当前交易阶段没有可接受的报价；可调整草案或使用当前面板的正常退出按钮。","response_unavailable")
    else
        add("incoming_response_status","当前没有收到的报价。","no_incoming_offer")
    end
end
'''


def _great_works(a: dict) -> str:
    return _HELPERS + _WORK_HELPERS + own_city(a["city_id"]) + '''
out.supported=true
local bldgs=city:GetBuildings()
for building in GameInfo.Buildings() do
    if bldgs:HasBuilding(building.Index)==true then
        local n=bldgs:GetNumGreatWorkSlots(building.Index)
        if not int(n) or n>64 then error("unavailable") end
        for slot=0,n-1 do
            local id,row=work_at(bldgs,building.Index,slot)
            local name=id and label(row.Name) or "Empty slot"
            local item={id=building.BuildingType..":"..slot,name=name,scope="self",owner_id=me,
                description="city="..city:GetID().." building="..building.BuildingType.." slot="..slot,
                value=id and movable(bldgs,building.Index,slot) or false}
            table.insert(out.items,item)
        end
    end
end
'''


def _archaeology(_: dict) -> str:
    return _HELPERS + '''
if type(player:GetUnits().GetNextExtractingArchaeologist)~="function" then return end
out.supported=true
local unit=player:GetUnits():GetNextExtractingArchaeologist()
if not unit or unit:GetOwner()~=me then return end
local artifact=Game.GetArtifactByIndex(unit:GetArchaeology():GetArtifactIndex())
if not artifact then return end
local function offer(choice,id)
    local name="Unknown civilization"
    if int(id) and id>=0 and known_player(id) then name=label(PlayerConfigurations[id]:GetCivilizationShortDescription()) end
    add("artifact_"..choice,name,nil,{type="choose_artifact",unit_id=unit:GetID(),choice=choice})
end
offer(1,artifact.ActingPlayerID)
if artifact.Type~=1 and artifact.Type~=2 and artifact.Type~=5 then offer(2,artifact.TargetPlayerID) end
'''


def _world_congress(_: dict) -> str:
    return _HELPERS + _CONGRESS_HELPERS + '''
if type(Game.GetWorldCongress)~="function" then return end
local wc=Game.GetWorldCongress()
if not wc then return end
out.supported=true
local stage=congress_stage()
local resolutions=wc:GetResolutions(me)
local proposed=proposals(wc,stage==nil)
if stage and type(resolutions)=="table" then
    out.decision_mode="congress"
    add("stage","Congress stage",stage)
    add("favor","Available diplomatic favor",player:GetFavor())
    for n,cost in pairs(wc:GetVotesandFavorCost(me)) do
        if int(n) and n>=0 and n<1000 and type(cost)=="number" then add("cost_"..(n+1),"Favor cost for "..(n+1).." votes",cost) end
    end
    for key,res in pairs(resolutions) do
        if type(key)=="number" then
            local row=GameInfo.Resolutions[res.Type]
            if row and type(res.PossibleTargets)=="table" then
                add(row.ResolutionType,label(row.Name),nil)
                add(row.ResolutionType.."_A",label(row.Effect1Description),1)
                add(row.ResolutionType.."_B",label(row.Effect2Description),2)
                for index,target in ipairs(res.PossibleTargets) do
                    local name=""
                    if res.TargetType=="PlayerType" then
                        local id=tonumber(target)
                        name="Unknown civilization"
                        if id and known_player(id) then name=label(PlayerConfigurations[id]:GetCivilizationShortDescription()) end
                    else name=label(target) end
                    add(row.ResolutionType.."_selection_"..(index-1),name,index-1)
                end
            end
        end
    end
end
for index,p in ipairs(proposed) do
    if not p.Disabled then
        -- Proposal order is an opaque UI choice, never a foreign player ID.
        local name=label(p.Name)
        if stage then
            add("proposal_"..(index-1),name,index-1)
            add("proposal_"..(index-1).."_up","Upvote allowed",can_vote(p,1))
            add("proposal_"..(index-1).."_down","Downvote allowed",can_vote(p,-1))
        elseif type(p.favor_cost)=="number" and p.favor_cost>=0 then
            local action=nil
            if player:GetFavor()>=p.favor_cost then action={type="congress_propose",proposal=index-1} end
            add("proposal_"..(index-1),name,index-1,action)
            add("proposal_"..(index-1).."_cost","Favor cost",p.favor_cost)
        end
    end
end
if not stage and NotificationManager and EndTurnBlockingTypes
    and NotificationManager.GetFirstEndTurnBlocking(me)==EndTurnBlockingTypes.ENDTURN_BLOCKING_WORLD_CONGRESS_LOOK then
    add("acknowledge_available","Finish reviewing available proposals",nil,{type="congress_acknowledge"})
end
'''


ACTIONS = {
    "diplomacy_statement": ActionSpec({"target_player": "id", "statement": "enum:"+"|".join(_STATEMENTS)}, _statement, "Initiate a normal diplomatic action with a met major civilization."),
    "diplomacy_respond": ActionSpec({"target_player": "id", "session_id": "id", "signature": "identifier:STATEMENT_", "response": "identifier:CHOICE_"}, _session_action, "Choose an offered response to the exact captured current local diplomacy statement.", turn_mode="diplomacy"),
    "diplomacy_close": ActionSpec({"target_player": "id", "session_id": "id", "signature": "identifier:STATEMENT_"}, _session_action, "Choose Exit on the exact captured local diplomacy conversation.", turn_mode="diplomacy"),
    **{name: ActionSpec({"target_player": "id"}, _city_state, "Normal action toward an encountered city-state.") for name in ("city_state_envoy", "city_state_levy", "city_state_war", "city_state_peace")},
    "city_state_defer_envoys": ActionSpec({}, defer_envoys, "Keep unassigned envoys and acknowledge the normal city-state reminder; spends no envoy."),
    "deal_clear": ActionSpec({"target_player": "id"}, _deal, "Clear the local outgoing negotiating draft; never an incoming or pending offer.", turn_mode="diplomacy"),
    "deal_add_item": ActionSpec({"target_player": "id", "side": "enum:give|receive", "kind": "enum:"+"|".join(_TRADE_KINDS), "value": "id", "amount": "id", "duration": "id", "agreement": "enum:NONE|"+"|".join(_AGREEMENTS)}, _deal, "Add an offered item to the outgoing draft; use deal_options for values/durations. Alliances use their GameInfo index.", turn_mode="diplomacy"),
    "deal_remove_item": ActionSpec({"target_player": "id", "item_id": "id"}, _deal, "Remove an unlocked item from the outgoing draft.", turn_mode="diplomacy"),
    "deal_send": ActionSpec({"target_player": "id"}, _deal, "Propose or counteroffer the validated outgoing draft, including peace and alliances.", turn_mode="diplomacy"),
    "deal_add_war": ActionSpec({"target_player": "id", "side": "enum:give|receive", "agreement": "enum:JOINT_WAR|THIRD_PARTY_WAR", "enemy": "id", "war": "text_identifier", "duration": "id"}, _war_deal, "Add a UI-offered joint/third-party war term against a met player. Sending/accepting this deal can declare war.", turn_mode="diplomacy"),
    "deal_respond": ActionSpec({"target_player": "id", "session_id": "id", "signature": "identifier:DEAL_", "accept": "bool"}, _deal, "Accept/reject the exact incoming terms observed; changed terms are rejected.", turn_mode="diplomacy"),
    "move_great_work": ActionSpec({"source_city": "id", "destination_city": "id", "source_building": "identifier:BUILDING_", "destination_building": "identifier:BUILDING_", "source_slot": "id", "destination_slot": "id"}, _move_work, "Move or swap own great works, respecting slot compatibility, art lock and full artifact museums."),
    "choose_artifact": ActionSpec({"unit_id": "id", "choice": "id"}, _artifact, "Choose the displayed artifact provenance: 1 or 2; never exposes an unmet identity."),
    "congress_ballot": ActionSpec({"resolutions": [{"resolution": "identifier:WC_RES_|RESOLUTION_", "choice": "id", "selection": "id", "votes": "id"}], "discussions": [{"proposal": "id", "direction": "signed_id", "votes": "id"}]}, _congress_ballot, "Submit all congress choices together: resolution choice 1/2, zero-based selection; discussion direction 1/-1. Total favor and every offered choice validated.", turn_mode="congress"),
    "congress_propose": ActionSpec({"proposal": "id"}, _congress_propose, "Propose an available emergency outside the voting segment."),
    "congress_acknowledge": ActionSpec({}, _congress_acknowledge, "Finish reviewing available congress proposals using the normal UI acknowledgement; never skips a voting session."),
    "emergency_respond": ActionSpec({"emergency": "id", "choice": "enum:join|reject|acknowledge"}, _emergency, "Join/decline a player-visible pending emergency, or acknowledge its started/completed information."),
}

QUERIES = {
    "diplomacy_sessions": QuerySpec({}, _diplomacy_sessions, "Discover met counterparts with open local sessions, captured public prompts and current response options."),
    "diplomacy_actions": QuerySpec({"target_player": "id"}, _diplo_query, "Available normal actions and verified conversation with a met counterpart."),
    "city_states": QuerySpec({}, _city_states_query, "Met city-state menu: envoys, anonymous rival contributions, suzerain, rewards, local quests, war state and legal operations."),
    "deal_options": QuerySpec({"target_player": "id", "side": "enum:give|receive", "kind": "enum:"+"|".join(_TRADE_KINDS)}, _deal_options, "Items offered by the player's standard trade UI. Unrevealed resources are filtered."),
    "war_deal_options": QuerySpec({"target_player": "id", "side": "enum:give|receive", "agreement": "enum:JOINT_WAR|THIRD_PARTY_WAR"}, lambda a: _war_deal(a, query=True), "Available joint/third-party war terms; unknown enemy IDs and identities are filtered before names."),
    "deal_state": QuerySpec({"target_player": "id"}, _deal_state, "Own outgoing/incoming negotiations and exact-offer response choices."),
    "great_works": QuerySpec({"city_id": "id"}, _great_works, "Own building slots; value indicates whether the work is currently movable."),
    "archaeology": QuerySpec({}, _archaeology, "Pending artifact provenance selection; unmet identities remain anonymous."),
    "world_congress": QuerySpec({}, _world_congress, "Player-facing resolutions, target ordinals, proposal ordinals, vote costs and favor."),
    "emergencies": QuerySpec({}, lambda a: _emergency(a, query=True), "Local-player emergency join/decline/acknowledge choices, without other participant identities or offscreen city locations."),
}
