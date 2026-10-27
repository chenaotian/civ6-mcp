"""The local governor's stock city-state assignment menu, including fogged cities.

Source: Expansion2/UI/Additions/GovernorAssignmentChooser.lua:166-195,
228-243, 298-314, 397-405. This menu grant never authorizes map/city details.
The own assignment caption follows GovernorSupport.lua:12-24, 79-86.
"""
from .base import ActionSpec, QuerySpec, lua


_MENU = r'''
local function integer(value, low, high)
    return type(value)=='number' and value==value and value>=low and value<=high
        and value==math.floor(value)
end
local function methods(object, names)
    if object==nil or object==false then return false end
    for _,name in ipairs(names) do
        if type(object[name])~='function' then return false end
    end
    return true
end
local function city_state_menu(governor_type, target_owner, target_city, include_current)
    if not GameInfo or not GameInfo.Governors or not PlayerManager
        or type(PlayerManager.GetAliveMinorIDs)~='function'
        or not methods(player, {'GetGovernors','GetDiplomacy'}) then return nil end
    local row=GameInfo.Governors[governor_type]
    if not row or row.GovernorType~=governor_type or not integer(row.Index,0,2147483647)
        or not integer(row.Hash,-2147483648,4294967295) then return nil end
    local governors=player:GetGovernors()
    if not methods(governors, {'HasGovernor','GetGovernor','GetAssignedGovernor','CanAssignGovernor'}) then return nil end
    -- No identity, promotion or city reads for an unappointed/unknown society.
    if governors:HasGovernor(row.Hash)~=true then return {} end
    local governor=governors:GetGovernor(row.Hash)
    if not methods(governor, {'IsGovernCityState','GetID','GetNeutralizedTurns'}) then return nil end
    if governor:IsGovernCityState()~=true then return {} end
    if GameInfo.GovernorsCannotAssign then
        for restriction in GameInfo.GovernorsCannotAssign() do
            if restriction.GovernorType==governor_type and restriction.CannotAssign then return {} end
        end
    end
    local governor_id=governor:GetID()
    if not integer(governor_id,0,2147483647) then return nil end
    local dip=player:GetDiplomacy()
    if not methods(dip, {'HasMet'}) then return nil end
    local ids=PlayerManager.GetAliveMinorIDs()
    if type(ids)~='table' or #ids>64 then return nil end
    -- The normal panel disables assignment while neutralized/in Congress.
    local can_request=false
    if Game and type(Game.IsAllowStrategicCommands)=='function'
        and Game.IsAllowStrategicCommands(me)==true and governor:GetNeutralizedTurns()==0
        and type(Game.GetWorldCongress)=='function' then
        local congress=Game.GetWorldCongress()
        can_request=methods(congress, {'IsInSession'}) and congress:IsInSession()==false
    end
    local turns
    if type(governor.GetTurnsToEstablish)=='function' then
        local ok,value=pcall(governor.GetTurnsToEstablish,governor)
        if ok and integer(value,0,1000000) then turns=value end
    end
    local entries,seen={},{}
    local scanned,current_count=0,0
    for _,owner in ipairs(ids) do
        if not integer(owner,0,63) then return nil end
        if owner~=me and not seen[owner] and (target_owner==nil or owner==target_owner)
            and dip:HasMet(owner)==true then
            seen[owner]=true
            -- HasMet precedes all access to this player's components/cities.
            local other=Players[owner]
            if not methods(other, {'GetInfluence','GetCities'}) then return nil end
            local influence=other:GetInfluence()
            if not methods(influence, {'CanReceiveInfluence'}) then return nil end
            if influence:CanReceiveInfluence()==true then
                local cities=other:GetCities()
                if not methods(cities, {'Members'}) then return nil end
                for _,city in cities:Members() do
                    scanned=scanned+1
                    if scanned>4096 then return nil end
                    if not methods(city, {'GetOwner','GetID'}) then return nil end
                    local city_owner,city_id=city:GetOwner(),city:GetID()
                    if city_owner~=owner or not integer(city_id,0,2147483647) then return nil end
                    if target_city==nil or city_id==target_city then
                        local current=governors:GetAssignedGovernor(city)
                        if current and not methods(current, {'GetID'}) then return nil end
                        local is_current=current and current:GetID()==governor_id
                        -- Stock omits this destination button, while the own GovernorPanel
                        -- caption still names the assignment. Return only its readonly summary.
                        if is_current and include_current then
                            current_count=current_count+1
                            if current_count>1 then return nil end
                            entries[#entries+1]={city=city,owner=owner,id=city_id,current=true}
                        elseif not is_current then
                            local allowed=governors:CanAssignGovernor(row.Hash,city,true)
                            if type(allowed)~='boolean' then return nil end
                            entries[#entries+1]={city=city,owner=owner,id=city_id,
                                enabled=allowed and can_request,turns=turns,index=row.Index}
                        end
                        -- At most two output records per menu entry. Never truncate silently.
                        if #entries>1024 then return nil end
                    end
                end
            end
        end
    end
    return entries
end
'''


def _query(params):
    return "out.supported=false\n" + _MENU + f'''
local governor_type={lua(params['governor'])}
local ok,entries=pcall(city_state_menu,governor_type,nil,nil,true)
if not ok or not entries then return end
local items={{}}
local function add(entry,suffix,name,value,action)
    local prefix=entry.current and 'current_assignment' or 'city_state:'..entry.owner..':'..entry.id
    items[#items+1]={{id=prefix..suffix,
        name=name,value=value,action=action,scope='menu',menu_source='governor_city_state',
        menu_owner_id=me,menu_offered=true,menu_governor=governor_type,
        menu_target_owner_id=entry.owner,menu_city_id=entry.id}}
end
for _,entry in ipairs(entries) do
    -- Only menu-proven cities reach their label; no location/yield/loyalty getter.
    if not methods(entry.city, {{'GetName'}}) then return end
    local name_ok,name=pcall(entry.city.GetName,entry.city)
    if not name_ok or type(name)~='string' then return end
    if Locale and type(Locale.Lookup)=='function' then
        local localized,value=pcall(Locale.Lookup,name)
        if localized and type(value)=='string' then name=value end
    end
    if entry.current then
        add(entry,':city',name,entry.id,nil)
        add(entry,':owner_id',nil,entry.owner,nil)
    else
        local action
        if entry.enabled then action={{type='governor_assign_city_state',governor=governor_type,
            owner_id=entry.owner,city_id=entry.id}} end
        add(entry,'',name,entry.enabled,action)
        if entry.turns~=nil then add(entry,':establish_turns',nil,entry.turns,nil) end
    end
end
out.items=array(items)
out.supported=true
'''


def _assign(params):
    return _MENU + f'''
local ok,entries=pcall(city_state_menu,{lua(params['governor'])},{params['owner_id']},{params['city_id']})
if not ok or not entries or #entries~=1 or entries[1].enabled~=true then return end
if not PlayerOperations or type(PlayerOperations.ASSIGN_GOVERNOR)~='number'
    or PlayerOperations.PARAM_GOVERNOR_TYPE==nil or PlayerOperations.PARAM_PLAYER_ONE==nil
    or PlayerOperations.PARAM_CITY_DEST==nil or not UI
    or type(UI.RequestPlayerOperation)~='function' then return end
local p={{[PlayerOperations.PARAM_GOVERNOR_TYPE]=entries[1].index,
    [PlayerOperations.PARAM_PLAYER_ONE]={params['owner_id']},
    [PlayerOperations.PARAM_CITY_DEST]={params['city_id']}}}
attempt(UI.RequestPlayerOperation,me,PlayerOperations.ASSIGN_GOVERNOR,p)
'''


_GOVERNOR = {"governor": "identifier:GOVERNOR_"}
ACTIONS = {
    "governor_assign_city_state": ActionSpec(
        {**_GOVERNOR, "owner_id": "id", "city_id": "id"}, _assign,
        "Assign an owned, appointed city-state governor to a destination in its current normal menu. "
        "Rechecks met living city-state membership and ordinary assignment eligibility; no map visibility or coordinates required."),
}
QUERIES = {
    "governor_city_state_destinations": QuerySpec(
        _GOVERNOR, _query,
        "The appointed governor's normal city-state assignment menu, including met destinations in fog. "
        "City rows have value=true only when currently assignable; disabled rows have no action. "
        "The :establish_turns suffix gives normal establishment duration. "
        "Readonly current_assignment:city gives the current eligible city-state name and city ID; "
        "current_assignment:owner_id gives its owner. Neither has an assignment action. No map or hidden city details."),
}
