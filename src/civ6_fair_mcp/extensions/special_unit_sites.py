"""Stock specialist lens candidates, with revealed coordinates only.

GS SelectedUnit_Expansion2.lua:47-64 supplies these exact lists to Great_People.
Overlay.artdef:19028-19038 hides that border on unexplored tiles and shows it
on revealed/visible tiles. No current plot contents or potential sites are scanned.
"""
from .base import QuerySpec, own_unit


CATEGORY = "special_unit_sites"
FIELDS = {"unit_id": "id"}
MAX_SITES = 512


def special_unit_sites(a: dict) -> str:
    return "out.supported=false\n" + own_unit(a["unit_id"]) + f'''
local function integer(v,low,high)
    return type(v)=="number" and v==v and v%1==0 and v>=low and v<=high
end
local function collect_sites()
    if not UI or type(UI.IsGameCoreBusy)~="function" or UI.IsGameCoreBusy()~=false
        or not GameInfo or not GameInfo.Units
        or not UnitManager
        or type(unit.GetUnitType)~="function" then return nil end
    local unit_type=unit:GetUnitType()
    if not integer(unit_type,0,2147483647) then return nil end
    local row=GameInfo.Units[unit_type]
    if not row then return nil end
    local purpose,operation,source,command_mode,individual_id
    if type(row.GreatPersonClass)=="string" and row.GreatPersonClass~="" then
        if type(unit.GetGreatPerson)~="function" then return nil end
        source=unit:GetGreatPerson()
        if not source or type(source.IsGreatPerson)~="function" or source:IsGreatPerson()~=true
            or type(source.GetIndividual)~="function" or not GameInfo.GreatPersonIndividuals then return nil end
        local individual=source:GetIndividual()
        if not integer(individual,0,2147483647) then return nil end
        individual_id=individual
        local definition=GameInfo.GreatPersonIndividuals[individual]
        if not definition then return nil end
        -- The stock lens only asks for activation tiles when this precise
        -- individual enables them; passive area highlights are a different list.
        if definition.ActionEffectTileHighlighting~=true then return {{}},nil end
        if type(source.GetActionCharges)~="function" then return nil end
        local charges=source:GetActionCharges()
        if not integer(charges,0,2147483647) then return nil end
        if charges==0 then return {{}},nil end
        if type(source.GetActivationHighlightPlots)~="function" then return nil end
        purpose="great_person"
        if row.GreatPersonClass=="GREAT_PERSON_CLASS_PROPHET" then
            operation=GameInfo.UnitOperations and GameInfo.UnitOperations["UNITOPERATION_FOUND_RELIGION"]
        else
            command_mode=true
            operation=GameInfo.UnitCommands and GameInfo.UnitCommands["UNITCOMMAND_ACTIVATE_GREAT_PERSON"]
        end
    elseif row.ExtractsArtifacts==true then
        purpose="excavate"
        operation=GameInfo.UnitOperations and GameInfo.UnitOperations["UNITOPERATION_EXCAVATE"]
    elseif integer(row.ParkCharges,1,2147483647) then
        purpose="national_park"
        operation=GameInfo.UnitOperations and GameInfo.UnitOperations["UNITOPERATION_DESIGNATE_PARK"]
    elseif row.UnitType=="UNIT_ROCK_BAND" then
        purpose="rock_concert"
        operation=GameInfo.UnitOperations and GameInfo.UnitOperations["UNITOPERATION_TOURISM_BOMB"]
    else
        return {{}},nil
    end
    if not operation or operation.VisibleInUI~=true
        or not integer(operation.Hash,-2147483648,4294967295) then return nil end
    -- UnitPanel's loose UI test: do not require standing on a candidate yet.
    -- Archaeologists have no stock numeric excavation-charge display; native
    -- EXCAVATE capability and their own lens decide whether sites are offered.
    local function eligible_now()
        if command_mode then
            if type(UnitManager.CanStartCommand)~="function" then return nil end
            return UnitManager.CanStartCommand(unit,operation.Hash,true)
        end
        if type(UnitManager.CanStartOperation)~="function" then return nil end
        return UnitManager.CanStartOperation(unit,operation.Hash,nil,true)
    end
    local eligible=eligible_now()
    if type(eligible)~="boolean" then return nil end
    if not eligible then return {{}},nil end
    if purpose=="national_park" then
        if type(unit.GetParkCharges)~="function" then return nil end
        local charges=unit:GetParkCharges()
        if not integer(charges,0,2147483647) then return nil end
        if charges==0 then return {{}},nil end
        if not Game or type(Game.GetNationalParks)~="function" then return nil end
        source=Game.GetNationalParks()
        if not source or type(source.GetPossibleParkTiles)~="function" then return nil end
    elseif purpose=="excavate" then
        if type(unit.GetArchaeology)~="function" then return nil end
        source=unit:GetArchaeology()
        if not source or type(source.GetActivationHighlightPlots)~="function" then return nil end
    elseif purpose=="rock_concert" then
        if type(unit.GetRockBand)~="function" then return nil end
        source=unit:GetRockBand()
        if not source or type(source.GetActivationHighlightPlots)~="function" then return nil end
    end
    if not Map or type(Map.GetGridSize)~="function" or type(Map.GetPlotByIndex)~="function"
        or not vis or type(vis.IsRevealed)~="function" then return nil end
    local width,height=Map.GetGridSize()
    if not integer(width,1,4096) or not integer(height,1,4096) then return nil end
    local candidates
    if purpose=="national_park" then candidates=source:GetPossibleParkTiles(me)
    else candidates=source:GetActivationHighlightPlots() end
    if type(candidates)~="table" then return nil end
    local result,seen={{}},{{}}
    local examined=0
    -- Like the stock lens, consume only its returned list. Native iterator
    -- keys are immaterial; never use them as a public ordinal or map index.
    for _,index in ipairs(candidates) do
        examined=examined+1
        if examined>65536 or not integer(index,0,width*height-1) then return nil end
        if not seen[index] then
            seen[index]=true
            local plot=Map.GetPlotByIndex(index)
            if not plot or type(plot.GetX)~="function" or type(plot.GetY)~="function" then return nil end
            -- Geometry only, including for rejected unexplored candidates.
            -- No GetResourceType/owner/unit/yield/appeal/feature reads here.
            local x,y=plot:GetX(),plot:GetY()
            if not integer(x,0,width-1) or not integer(y,0,height-1) then return nil end
            if vis:IsRevealed(x,y)==true then
                if #result>={MAX_SITES} then return nil end
                result[#result+1]={{x=math.floor(x),y=math.floor(y),revealed=true,highlighted=true}}
            end
        end
    end
    if UI.IsGameCoreBusy()~=false or unit:GetOwner()~=me or unit:GetID()~={a['unit_id']}
        or unit:GetUnitType()~=unit_type then return nil end
    if purpose=="national_park" then
        local charges=unit:GetParkCharges()
        if not integer(charges,1,2147483647) then return nil end
    elseif purpose=="great_person" then
        if source:IsGreatPerson()~=true or source:GetIndividual()~=individual_id
            or not integer(source:GetActionCharges(),1,2147483647) then return nil end
    end
    if eligible_now()~=true then return nil end
    -- Recheck perception immediately before publishing, with no tile reads.
    for _,site in ipairs(result) do
        if vis:IsRevealed(site.x,site.y)~=true then return nil end
    end
    table.sort(result,function(a,b) return a.y<b.y or (a.y==b.y and a.x<b.x) end)
    return result,purpose
end
local ok,items,purpose=pcall(collect_sites)
if not ok or type(items)~="table" then return end
out.supported=true
if purpose then
    out.special_unit_sites={{source="stock_selected_unit_lens",owner_id=me,
        unit_id={a['unit_id']},purpose=purpose,eligible=true}}
    for _,item in ipairs(items) do add_item(item) end
end
'''


ACTIONS = {}
QUERIES = {
    CATEGORY: QuerySpec(FIELDS, special_unit_sites,
        "Own archaeologist, park-capable unit, great person or rock band's stock highlighted sites. Revealed coordinates "
        "include fog, but never current tile contents or unexplored locations. Each site N "
        "has site:N:x, site:N:y, site:N:purpose scalar items; no actions, park footprints, "
        "reachability or permission to activate now. At most 512 sites; missing APIs fail closed."),
}
