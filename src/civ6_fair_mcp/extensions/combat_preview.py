"""Fixed stock UnitPanel preview against one explicitly detected enemy unit.

The simulation is never allowed to choose a defender by plot. Only the two
normal strength labels and the normal modifier text lists cross the boundary.
"""
from __future__ import annotations

from .base import QuerySpec, lua


FIELDS = {
    "attacker_kind": "enum:unit_melee|unit_ranged|city|district",
    "attacker_id": "id", "target_owner_id": "id", "target_unit_id": "id",
    "x": "coord", "y": "coord",
}

_PREVIEW = r'''
local request=__REQUEST__
out.supported=false
out.items=array({})
local function integer(v,maximum)
    return type(v)=='number' and v==v and v%1==0 and v>=0 and v<=maximum
end
local function finite(v)
    return type(v)=='number' and v==v and v>=-1000000 and v<=1000000
end
local function need(value)
    if not value then error('unavailable') end
    return value
end
local function method(object,name,...)
    need(object and type(object[name])=='function')
    return object[name](object,...)
end
local function owned(collection,id)
    local list=method(player,'Get'..collection)
    need(list and type(list.Members)=='function')
    local count=0
    for _,entity in list:Members() do
        count=count+1; need(count<=4096)
        -- No other property is touched on a foreign object in an own list.
        if method(entity,'GetOwner')==me and method(entity,'GetID')==id then return entity end
    end
end
local function component(entity,owner,id,kind)
    need(type(kind)=='number')
    local value=method(entity,'GetComponentID')
    need(type(value)=='table' and value.player==owner and value.id==id and value.type==kind)
    return value
end
local function same_component(a,b)
    return type(a)=='table' and a.type==b.type and a.player==b.player and a.id==b.id
end
local function operation(name)
    need(GameInfo and GameInfo.UnitOperations)
    local row=GameInfo.UnitOperations[name]
    need(row and row.VisibleInUI==true and type(row.Hash)=='number'
        and row.Hash%1==0 and row.Hash>=-2147483648 and row.Hash<=4294967295)
    return row.Hash
end
local function normal_text(value)
    return type(value)=='string' and #value>0 and #value<=8192 and not value:find('[%z\1-\31\127]')
end
local function inspect()
    if out.active_turn~=true or request.target_owner_id>63 or request.target_owner_id==me then return end
    need(UI and type(UI.IsGameCoreBusy)=='function' and type(UI.IsProcessingMessages)=='function')
    if UI.IsGameCoreBusy()~=false or UI.IsProcessingMessages()~=false then return end
    need(Game and type(Game.IsAllowTacticalCommands)=='function')
    if Game.IsAllowTacticalCommands(me)~=true then return end

    local kind=request.attacker_kind
    local is_unit=kind=='unit_melee' or kind=='unit_ranged'
    local actor=owned(is_unit and 'Units' or (kind=='city' and 'Cities' or 'Districts'),request.attacker_id)
    if not actor then return end
    need(ComponentType and CombatTypes and CombatResultParameters)
    local source=actor
    local source_id=request.attacker_id
    local source_type=ComponentType.UNIT
    local combat_type
    local combat_name
    local operation_hash
    if is_unit then
        if method(actor,'IsDelayedDeath')~=false then return end
        local definition=GameInfo and GameInfo.Units and GameInfo.Units[method(actor,'GetUnitType')]
        need(definition)
        if definition.Domain~='DOMAIN_LAND' and definition.Domain~='DOMAIN_SEA' then return end
        local moves=method(actor,'GetMovesRemaining')
        local combat=method(actor,'GetCombat')
        local ranged=method(actor,'GetRangedCombat')
        local bombard=method(actor,'GetBombardCombat')
        need(finite(moves) and finite(combat) and finite(ranged) and finite(bombard))
        if moves<=0 or combat<=0 then return end
        if kind=='unit_melee' then
            if ranged>combat or bombard>combat then return end
            combat_type,combat_name=CombatTypes.MELEE,'melee'
            operation_hash=operation('UNITOPERATION_MOVE_TO')
        else
            if ranged<=0 and bombard<=0 then return end
            if bombard>ranged then combat_type,combat_name=CombatTypes.BOMBARD,'bombard'
            else combat_type,combat_name=CombatTypes.RANGED,'ranged' end
            operation_hash=operation('UNITOPERATION_RANGE_ATTACK')
        end
    else
        source_type=ComponentType.DISTRICT
        need(type(CombatTypes.RANGED)=='number' and CombatTypes.RANGED%1==0
            and type(CombatTypes.BOMBARD)=='number' and CombatTypes.BOMBARD%1==0)
        if kind=='city' then
            source_id=method(actor,'GetDistrictID')
            need(integer(source_id,2147483647))
            source=owned('Districts',source_id)
            if not source then return end
        else
            local definition=GameInfo and GameInfo.Districts and GameInfo.Districts[method(actor,'GetType')]
            need(definition and type(definition.DistrictType)=='string')
            -- The city-center shot already has the canonical city entry.
            if definition.DistrictType=='DISTRICT_CITY_CENTER' then return end
        end
    end
    if is_unit then need(type(combat_type)=='number') end

    -- These guards precede obtaining any target plot or unit container.
    local x,y=request.x,request.y
    need(Map and type(Map.GetGridSize)=='function' and type(Map.GetPlot)=='function')
    local width,height=Map.GetGridSize()
    need(integer(width,4096) and integer(height,4096))
    if x>=width or y>=height or vis:IsRevealed(x,y)~=true or vis:IsVisible(x,y)~=true then return end
    local plot=Map.GetPlot(x,y)
    if not plot then return end
    need(type(vis.IsUnitVisible)=='function' and Units and type(Units.GetUnitsInPlotLayerID)=='function'
        and MapLayers and MapLayers.ANY~=nil)
    local candidates=Units.GetUnitsInPlotLayerID(x,y,MapLayers.ANY)
    need(type(candidates)=='table')
    local target
    for _,candidate in pairs(candidates) do
        -- Detection is the very first interaction with a candidate, including
        -- spies/submarines. Never resolve a caller ID through a foreign player.
        local ok,detected=pcall(vis.IsUnitVisible,vis,candidate)
        if ok and detected==true then
            if method(candidate,'GetOwner')==request.target_owner_id
                and method(candidate,'GetID')==request.target_unit_id
                and method(candidate,'GetX')==x and method(candidate,'GetY')==y
                and method(candidate,'IsDelayedDeath')==false then
                if target and target~=candidate then return end
                target=candidate
            end
        end
    end
    if not target then return end
    local attacker_component=component(source,me,source_id,source_type)
    local target_component=component(target,request.target_owner_id,request.target_unit_id,ComponentType.UNIT)
    need(CombatManager and type(CombatManager.CanAttackTarget)=='function'
        and type(CombatManager.SimulateAttackVersus)=='function')
    local diplomacy
    if is_unit then
        need(type(CombatManager.IsAttackChangeWarState)=='function')
        local war_changes=CombatManager.IsAttackChangeWarState(attacker_component,x,y)
        if war_changes~=nil and (type(war_changes)~='table' or next(war_changes)~=nil) then return end
    else
        -- Ordinary city/district strike does not use the CITY WMD war-change
        -- API (WorldInput 2553-56/2624-27). Require this already detected
        -- target's owner to be at war through the local player's public state.
        diplomacy=method(player,'GetDiplomacy')
        if method(diplomacy,'IsAtWarWith',request.target_owner_id)~=true then return end
    end
    need(UnitOperationTypes and UnitOperationTypes.PARAM_X~=nil and UnitOperationTypes.PARAM_Y~=nil)
    local parameters={[UnitOperationTypes.PARAM_X]=x,[UnitOperationTypes.PARAM_Y]=y}
    if is_unit then
        if kind=='unit_melee' then
            local ax,ay=method(actor,'GetX'),method(actor,'GetY')
            need(integer(ax,4095) and integer(ay,4095) and type(Map.GetPlotDistance)=='function')
            if Map.GetPlotDistance(ax,ay,x,y)~=1 then return end
            need(UnitOperationMoveModifiers and type(UnitOperationMoveModifiers.ATTACK)=='number'
                and UnitOperationTypes.PARAM_MODIFIERS~=nil)
            parameters[UnitOperationTypes.PARAM_MODIFIERS]=UnitOperationMoveModifiers.ATTACK
        end
        need(UnitManager and type(UnitManager.CanStartOperation)=='function')
        if UnitManager.CanStartOperation(actor,operation_hash,nil,parameters,false)~=true then return end
    else
        need(CityManager and type(CityManager.CanStartCommand)=='function'
            and CityCommandTypes and type(CityCommandTypes.RANGE_ATTACK)=='number')
        if CityManager.CanStartCommand(actor,CityCommandTypes.RANGE_ATTACK,parameters)~=true then return end
    end
    -- Preserve the existing unit gate. City/district UI instead simulates
    -- with no prescribed type, then checks its actual type (UnitPanel 3382-3400,
    -- 3594-3598). The canonical actor there is the own district in both calls.
    if is_unit and CombatManager.CanAttackTarget(attacker_component,target_component,combat_type)~=true then return end
    local result
    if is_unit then
        -- Stock melee flag preview omits the type; range mode specifies it.
        result=CombatManager.SimulateAttackVersus(attacker_component,target_component,
            kind=='unit_ranged' and combat_type or nil)
    else
        result=CombatManager.SimulateAttackVersus(attacker_component,target_component)
    end
    if UI.IsGameCoreBusy()~=false or UI.IsProcessingMessages()~=false
        or vis:IsRevealed(x,y)~=true or vis:IsVisible(x,y)~=true
        or vis:IsUnitVisible(target)~=true then return end
    need(type(result)=='table')
    local keys=CombatResultParameters
    for _,name in ipairs({'ATTACKER','DEFENDER','ID','COMBAT_TYPE','COMBAT_STRENGTH','STRENGTH_MODIFIER'}) do
        need(keys[name]~=nil)
    end
    local attack,defend=result[keys.ATTACKER],result[keys.DEFENDER]
    need(type(attack)=='table' and type(defend)=='table')
    local actual_type=result[keys.COMBAT_TYPE]
    need(type(actual_type)=='number' and actual_type%1==0)
    if is_unit then
        if actual_type~=combat_type then return end
    elseif actual_type==CombatTypes.RANGED then
        combat_type,combat_name=actual_type,'ranged'
    elseif actual_type==CombatTypes.BOMBARD then
        combat_type,combat_name=actual_type,'bombard'
    else
        return
    end
    if not same_component(attack[keys.ID],attacker_component)
        or not same_component(defend[keys.ID],target_component) then return end
    if CombatManager.CanAttackTarget(attacker_component,target_component,actual_type)~=true then return end

    local items=array({})
    for _,side in ipairs({{'attacker',attack},{'defender',defend}}) do
        local base,modifier=side[2][keys.COMBAT_STRENGTH],side[2][keys.STRENGTH_MODIFIER]
        need(finite(base) and finite(modifier))
        local strength=math.max(0,base+modifier)
        need(finite(strength))
        items[#items+1]={id=side[1]..'_strength',value=strength}
        local index=0
        -- UnitPanel.GetCombatModifierList's ground-combat display whitelist.
        -- No interceptor/AA lookup, hidden participant IDs, detailed bonus
        -- structures, random rolls or damage/HP fields are ever read.
        for _,name in ipairs({'HEALTH','TERRAIN','OPPONENT','MODIFIER','ASSIST','PROMOTION','DEFENSES','RESOURCES'}) do
            local key=keys['PREVIEW_TEXT_'..name]
            need(key~=nil)
            local texts=side[2][key]
            if texts~=nil then
                need(type(texts)=='table')
                local count=0
                for entry,value in pairs(texts) do
                    count=count+1
                    need(integer(entry,64) and entry>0 and normal_text(value))
                end
                need(count<=64 and count==#texts)
                for entry=1,count do
                    need(normal_text(texts[entry]) and Locale and type(Locale.Lookup)=='function')
                    local text=Locale.Lookup(texts[entry])
                    need(normal_text(text))
                    index=index+1;need(index<=256)
                    items[#items+1]={id=side[1]..'_modifier:'..index,value=text}
                end
            end
        end
    end
    items[#items+1]={id='combat_type',value=combat_name}
    -- Recheck current proof after the engine simulation, before publication.
    if UI.IsGameCoreBusy()~=false or UI.IsProcessingMessages()~=false
        or Game.IsAllowTacticalCommands(me)~=true or vis:IsRevealed(x,y)~=true
        or vis:IsVisible(x,y)~=true or vis:IsUnitVisible(target)~=true
        or method(actor,'GetOwner')~=me or method(actor,'GetID')~=request.attacker_id
        or method(source,'GetOwner')~=me or method(source,'GetID')~=source_id
        or method(target,'GetOwner')~=request.target_owner_id or method(target,'GetID')~=request.target_unit_id
        or method(target,'GetX')~=x or method(target,'GetY')~=y
        or method(target,'IsDelayedDeath')~=false then return end
    if not is_unit and method(diplomacy,'IsAtWarWith',request.target_owner_id)~=true then return end
    local proof={attacker_kind=kind,attacker_id=request.attacker_id,attacker_owner_id=math.floor(me),
        target_owner_id=request.target_owner_id,target_unit_id=request.target_unit_id,x=x,y=y,
        revealed=true,visible=true,detected=true,legal_action=true,can_attack_target=true,
        attacker_matches=true,defender_matches=true,source='stock_unit_panel'}
    return items,proof
end
local ok,items,proof=pcall(inspect)
if ok then
    out.supported=true
    if items and proof then out.items=items;out.combat_preview=proof end
end
'''


def preview(params: dict) -> str:
    return _PREVIEW.replace("__REQUEST__", lua(params))


ACTIONS = {}
QUERIES = {"combat_preview": QuerySpec(FIELDS, preview,
    "Stock combat strength and modifier text for a legal own ground/naval unit or city/district attack against one currently visible, detected enemy unit. No exact damage or automatic defender selection.")}
