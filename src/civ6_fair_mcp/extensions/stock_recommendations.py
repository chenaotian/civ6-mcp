"""The exact local-unit recommendations rendered by WorldViewIconsManager.

No map scan, raw AI score, foreign city list or free-form settling reasons.
"""
from .base import QuerySpec, own_unit

CATEGORY = "unit_recommendations"
FIELDS = {"unit_id": "id"}
MAX_RECOMMENDATIONS = 512


def recommendations(a: dict) -> str:
    return "out.supported=false\n" + own_unit(a["unit_id"]) + f'''
local function integer(v,low,high)
    return type(v)=="number" and v==v and v%1==0 and v>=low and v<=high
end
local function collect()
    if not UI or type(UI.IsGameCoreBusy)~="function" or UI.IsGameCoreBusy()~=false
        or not GameInfo or not GameInfo.Units or type(unit.GetUnitType)~="function"
        or type(unit.GetBuildCharges)~="function" or not Map
        or type(Map.GetGridSize)~="function" or type(Map.GetPlotByIndex)~="function"
        or not vis or type(vis.IsRevealed)~="function" or type(vis.IsVisible)~="function" then return nil end
    local unit_type=unit:GetUnitType()
    local charges=unit:GetBuildCharges()
    if not integer(unit_type,0,2147483647) or not integer(charges,0,2147483647) then return nil end
    local row=GameInfo.Units[unit_type]
    if not row then return nil end
    local kind
    if charges>0 then kind="builder"
    elseif row.FoundCity==true then kind="settler"
    else return {{}},nil end
    local width,height=Map.GetGridSize()
    if not integer(width,1,4096) or not integer(height,1,4096) then return nil end
    local records,city,ux,uy
    if kind=="builder" then
        -- WorldViewIconsManager.lua:787-792: current purchase city only.
        if type(unit.GetX)~="function" or type(unit.GetY)~="function"
            or type(unit.GetComponentID)~="function" or type(Map.GetPlotIndex)~="function"
            or not Cities or type(Cities.GetPlotPurchaseCity)~="function" then return nil end
        ux,uy=unit:GetX(),unit:GetY()
        if not integer(ux,0,width-1) or not integer(uy,0,height-1) then return nil end
        if vis:IsRevealed(ux,uy)~=true or vis:IsVisible(ux,uy)~=true then return {{}},kind end
        local index=Map.GetPlotIndex(ux,uy)
        if not integer(index,0,width*height-1) then return nil end
        city=Cities.GetPlotPurchaseCity(index)
        if not city then return {{}},kind end
        if type(city.GetOwner)~="function" then return nil end
        if city:GetOwner()~=me then return {{}},kind end
        if type(city.GetCityAI)~="function" then return nil end
        local advisor=city:GetCityAI()
        if not advisor or type(advisor.GetImprovementRecommendationsForBuilder)~="function" then return nil end
        -- Only this public UI method; never ratings or arbitrary AI methods.
        records=advisor:GetImprovementRecommendationsForBuilder(unit:GetComponentID())
    else
        -- WorldViewIconsManager.lua:703-710 requests exactly five locations.
        if type(player.GetGrandStrategicAI)~="function" then return nil end
        local advisor=player:GetGrandStrategicAI()
        if not advisor or type(advisor.GetSettlementRecommendations)~="function" then return nil end
        records=advisor:GetSettlementRecommendations(5)
    end
    if type(records)~="table" then return nil end
    local result,seen={{}},{{}}
    local examined=0
    for _,recommendation in pairs(records) do
        examined=examined+1
        if examined>{MAX_RECOMMENDATIONS} or (kind=="settler" and examined>5)
            or type(recommendation)~="table" then return nil end
        local index
        if kind=="builder" then index=recommendation.ImprovementLocation
        else index=recommendation.SettlingLocation end
        if not integer(index,0,width*height-1) then return nil end
        -- Hidden recommendations are discarded before hash, text or geometry.
        if vis:IsRevealed(index)==true and vis:IsVisible(index)==true then
            local plot=Map.GetPlotByIndex(index)
            if not plot or type(plot.GetX)~="function" or type(plot.GetY)~="function" then return nil end
            local x,y=plot:GetX(),plot:GetY()
            if not integer(x,0,width-1) or not integer(y,0,height-1) then return nil end
            local item={{x=math.floor(x),y=math.floor(y),visible=true,revealed=true,recommended=true}}
            local key=tostring(index)
            if kind=="builder" then
                local hash=recommendation.ImprovementHash
                if not integer(hash,-2147483648,4294967295) or not GameInfo.Improvements then return nil end
                local definition=GameInfo.Improvements[hash]
                local identifier=definition and definition.ImprovementType
                if type(identifier)~="string" or #identifier>128
                    or not identifier:match("^IMPROVEMENT_[A-Z0-9_]+$") then return nil end
                item.improvement=identifier
                key=key..":"..identifier
                if type(definition.Name)=="string" and Locale and type(Locale.Lookup)=="function" then
                    local ok,name=pcall(Locale.Lookup,definition.Name)
                    if ok and type(name)=="string" and #name<=1024 and not name:find("%z") then item.name=name end
                end
            end
            if not seen[key] then seen[key]=true;result[#result+1]=item end
        end
    end
    if UI.IsGameCoreBusy()~=false or unit:GetOwner()~=me or unit:GetID()~={a['unit_id']}
        or unit:GetUnitType()~=unit_type then return nil end
    local current_charges=unit:GetBuildCharges()
    if not integer(current_charges,0,2147483647) then return nil end
    if kind=="builder" and (current_charges<=0 or city:GetOwner()~=me
        or unit:GetX()~=ux or unit:GetY()~=uy) then return nil end
    if kind=="settler" and current_charges~=0 then return nil end
    for _,item in ipairs(result) do
        if vis:IsRevealed(item.x,item.y)~=true or vis:IsVisible(item.x,item.y)~=true then return nil end
    end
    table.sort(result,function(a,b)
        if a.y~=b.y then return a.y<b.y end
        if a.x~=b.x then return a.x<b.x end
        return (a.improvement or "")<(b.improvement or "")
    end)
    return result,kind
end
local ok,records,kind=pcall(collect)
if not ok or type(records)~="table" then return end
out.supported=true
if kind then
    out.unit_recommendations={{source="stock_world_view_icons",owner_id=me,
        unit_id={a['unit_id']},kind=kind}}
    for _,record in ipairs(records) do add_item(record) end
end
'''


ACTIONS = {}
QUERIES = {CATEGORY: QuerySpec(FIELDS, recommendations,
    "Own unit's stock recommendations: builder improvements in its current own purchase city, "
    "or the stock five settler recommendations. Only currently visible coordinates; no "
    "scores, hidden sites, settling reasons, tile contents or actions. A recommendation "
    "does not guarantee reachability, current operation legality or the best strategic choice.")}
