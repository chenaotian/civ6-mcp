"""Public bilateral relationship information from the stock diplomacy panels.

See docs/REFERENCE_PARITY_DIPLOMACY.md for source paths and disclosure rules.
No third-party relationship scan, AI deal evaluation, or foreign entity access.
"""

RELATIONSHIP_HELPERS = r'''
local function public_relationship(other, id, configuration)
    -- Defense in depth: this helper must never be used for an unknown, dead,
    -- or self target even if its caller is later moved.
    if id==me or player:GetDiplomacy():HasMet(id)~=true or other:IsAlive()~=true then return nil end
    local result={observer_id=me,target_id=id,public_ui=true}
    local function read(object,method,...)
        if not object or type(object[method])~='function' then return nil end
        local ok,value=pcall(object[method],object,...)
        if ok then return value end
    end
    local function put(key,value,kind)
        if kind=='bool' and type(value)=='boolean' then result[key]=value
        elseif kind=='count' and finite(value) and value>=0 and value%1==0 and value<2147483648 then result[key]=math.floor(value)
        elseif kind=='number' and finite(value) then result[key]=value
        elseif kind=='identifier' and identifier(value) then result[key]=value
        elseif kind=='text' and type(value)=='string' and #value<=1024 and not value:match('[%z\1-\31]') then result[key]=value end
    end
    local function name(key,value)
        if type(value)~='string' then return end
        local ok,text=pcall(Locale.Lookup,value)
        if ok then put(key,text,'text') end
    end
    local dip=player:GetDiplomacy()
    local access=read(dip,'GetVisibilityOn',id)
    if finite(access) and access>=0 and access%1==0 and access<2147483648 then
        put('access_level',access,'count')
        local row=GameInfo.Visibilities and GameInfo.Visibilities[access]
        if row then name('access_name',row.Name) end
    end
    put('grievances',read(dip,'GetGrievancesAgainst',id),'number')
    for key,method in pairs({delegation_sent='HasDelegationAt',embassy_sent='HasEmbassyAt',
        defensive_pact='HasDefensivePact',open_borders_received='HasOpenBordersFrom',
        joint_war='IsFightingAnyJointWarWith'}) do
        put(key,read(dip,method,id),'bool')
    end
    local foreign_dip=read(other,'GetDiplomacy')
    put('open_borders_given',read(foreign_dip,'HasOpenBordersFrom',me),'bool')
    local agreement=read(dip,'GetResearchAgreementTech',id)
    if finite(agreement) and agreement%1==0 and agreement>=-1 then
        put('research_agreement',agreement~=-1,'bool')
    end
    -- Human calculated feelings are explicitly hidden by the stock UI.
    if read(configuration,'IsHuman')==false then
        result.ai_panel=true
        local ai=read(other,'GetDiplomaticAI')
        local index=read(ai,'GetDiplomaticStateIndex',me)
        if finite(index) and index>=0 and index%1==0 then
            local definition=GameInfo.DiplomaticStates and GameInfo.DiplomaticStates[index]
            if definition and identifier(definition.StateType) and definition.StateType:match('^DIPLO_STATE_') then
                put('state',definition.StateType,'identifier')
                name('state_name',definition.Name)
            end
        end
        local modifiers=read(ai,'GetDiplomaticModifiers',me)
        if type(modifiers)=='table' and #modifiers<=128 then
            local values=array({})
            local valid=true
            for _,entry in ipairs(modifiers) do
                if type(entry)~='table' or not finite(entry.Score) then valid=false;break end
                -- The UI hides zero-score rows; don't read their text at all.
                if entry.Score~=0 then
                    local ok,text=pcall(function() return Locale.Lookup(entry.Text) end)
                    if not ok or type(text)~='string' or #text>1024 or text:match('[%z\1-\31]') then valid=false;break end
                    values[#values+1]={score=rounded(entry.Score,2),text=text}
                end
            end
            if valid then
                table.sort(values,function(a,b) if a.score==b.score then return a.text<b.text end return a.score>b.score end)
                result.modifiers=values
            end
        end
    end
    local alliance_index=read(dip,'GetAllianceType',id)
    if alliance_index==-1 then result.allied=false
    elseif finite(alliance_index) and alliance_index>=0 and alliance_index%1==0 then
        local definition=GameInfo.Alliances and GameInfo.Alliances[alliance_index]
        if definition and identifier(definition.AllianceType) and definition.AllianceType:match('^ALLIANCE_') then
            result.allied=true
            put('alliance',definition.AllianceType,'identifier')
            name('alliance_name',definition.Name)
            local level=read(dip,'GetAllianceLevel',id)
            put('alliance_level',level,'count')
            put('alliance_turns_remaining',read(dip,'GetAllianceTurnsUntilExpiration',id),'count')
            -- The max-level panel hides points: no fabricated zeroes or reads.
            local multiplier=GlobalParameters and GlobalParameters.ALLIANCE_POINTS_MULTIPLIER
            if finite(level) and level>=1 and level<3 and finite(multiplier) and multiplier>0 then
                for key,method in pairs({alliance_points='GetAllianceTurnsThisLevel',
                    alliance_points_required='GetAllianceTurnsToNextLevel',alliance_points_per_turn='GetAlliancePointsPerTurn'}) do
                    local value=read(dip,method,id)
                    if finite(value) and value>=0 then put(key,value/multiplier,'number') end
                end
            end
        end
    end
    return result
end
'''


def project_relationship(raw, player_id: int, target_id: int) -> dict | None:
    """Require bilateral menu proof before validating or copying any details."""
    from .policy import PolicyError, _project

    if (type(raw) is not dict or raw.get("public_ui") is not True
            or type(raw.get("observer_id")) is not int or raw["observer_id"] != player_id
            or type(raw.get("target_id")) is not int or raw["target_id"] != target_id
            or target_id == player_id):
        return None
    fields = {
        "access_level": "int",
        "access_name": "ui_text", "grievances": "number",
        **{key: "bool" for key in ("delegation_sent", "embassy_sent", "defensive_pact",
            "open_borders_received", "open_borders_given", "research_agreement", "joint_war", "allied")},
    }
    if raw.get("ai_panel") is True:
        fields.update({"state": "identifier", "state_name": "ui_text"})
    if raw.get("allied") is True:
        fields.update({"alliance": "identifier", "alliance_name": "ui_text",
                       "alliance_level": "int", "alliance_turns_remaining": "int"})
        if type(raw.get("alliance_level")) is int and 1 <= raw["alliance_level"] < 3:
            fields.update({key: "number" for key in (
                "alliance_points", "alliance_points_required", "alliance_points_per_turn")})
    result = _project(raw, fields)
    for key, prefix in (("state", "DIPLO_STATE_"), ("alliance", "ALLIANCE_")):
        if key in result and not result[key].startswith(prefix):
            raise PolicyError("invalid_response")
    if raw.get("ai_panel") is True and "modifiers" in raw:
        entries = raw["modifiers"]
        if type(entries) is not list or len(entries) > 128:
            raise PolicyError("invalid_response")
        result["modifiers"] = []
        for entry in entries:
            if type(entry) is not dict:
                raise PolicyError("invalid_response")
            projected = _project(entry, {"score": "number"})
            if "score" not in projected:
                raise PolicyError("invalid_response")
            if projected["score"] == 0:
                continue
            projected.update(_project(entry, {"text": "ui_text"}))
            if "text" not in projected:
                raise PolicyError("invalid_response")
            result["modifiers"].append(projected)
    return result
