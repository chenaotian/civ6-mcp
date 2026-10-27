"""Optional, own-player information shown by the stock research/civic chooser.

Source: Base/Assets/UI/TechAndCivicSupport.lua:GetResearchData (536-575),
GetCivicData (653-692), and Screens/TechTree.lua:1098-1114 /
Screens/CivicsTree.lua:1274-1289 for the current item's turns-left override.
Description is the database's optional public text, not a fabricated summary of
all unlocks. Every optional getter is isolated so old runtimes keep their list.
"""

RESEARCH_OPTION_HELPERS = r'''
local function option_text(value,limit,multiline)
    if type(value)~="string" or #value>limit then return nil end
    if multiline then
        if value:find("[%z\1-\8\11\12\14-\31]") then return nil end
    elseif value:find("[%z\1-\31]") then return nil end
    return value
end
local function option_lookup(key,limit,multiline)
    if type(key)~="string" or key=="" or not Locale or type(Locale.Lookup)~="function" then return nil end
    local ok,value=pcall(Locale.Lookup,key)
    if ok then return option_text(value,limit,multiline) end
end
local function option_read(object,method,...)
    if not object or type(object[method])~="function" then return nil end
    local ok,value=pcall(object[method],object,...)
    if ok then return value end
end
local function option_number(value,integer)
    if type(value)~="number" or value~=value or value<0 or value>=1e15 then return nil end
    if integer then
        if value%1~=0 or value>2147483647 then return nil end
        return math.floor(value)
    end
    return value
end
local option_boosts=nil
local function option_boost_description(id)
    if option_boosts==nil then
        option_boosts={}
        if GameInfo.Boosts~=nil then
            local ok,result=pcall(function()
                local result={}
                local count=0
                for row in GameInfo.Boosts() do
                    count=count+1
                    if count>8192 then return nil end
                    local key=row.TechnologyType or row.CivicType
                    if type(key)=="string" and result[key]==nil then
                        result[key]=option_lookup(row.TriggerDescription,8192,true)
                    end
                end
                return result
            end)
            if ok and type(result)=="table" then option_boosts=result end
        end
    end
    return option_boosts[id]
end
local function enrich_research_option(item,row,progress,kind)
    -- Called only AFTER the own player's ordinary CanResearch/CanProgress gate.
    item.name=option_lookup(row.Name,1024,false)
    item.description=option_lookup(row.Description,8192,true)
    item.boost_description=option_boost_description(item.id)
    local technology=kind=="research"
    local cost_method=technology and "GetResearchCost" or "GetCultureCost"
    local progress_method=technology and "GetResearchProgress" or "GetCulturalProgress"
    local turns_method=technology and "GetTurnsToResearch" or "GetTurnsToProgressCivic"
    local current_method=technology and "GetResearchingTech" or "GetProgressingCivic"
    item.cost=option_number(option_read(progress,cost_method,row.Index),false)
    item.progress=option_number(option_read(progress,progress_method,row.Index),false)
    item.turns=option_number(option_read(progress,turns_method,row.Index),true)
    local current=option_read(progress,current_method)
    if type(current)=="number" and current==row.Index then
        item.turns=option_number(option_read(progress,"GetTurnsLeft"),true) or item.turns
    end
    local boosted=option_read(progress,"HasBoostBeenTriggered",row.Index)
    if type(boosted)=="boolean" then item.boosted=boosted end
end
'''
