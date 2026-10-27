"""Public city religion and own science milestones, from stock UI readers.

CitySupport:499-510; GS CityBannerManager:1902-2090 (religion lens).
Base WorldRankings:183-192,1234-1267; GS replacement:290-375,587-589.
No world-player lists, historical city scans or rival project inventories.
"""
from .base import QuerySpec, lua, own_city


HELPERS = r'''
local function integer(v,lo,hi)
    return type(v)=="number" and v==v and v%1==0 and v>=lo and v<=hi
end
local function finite(v) return type(v)=="number" and v==v and math.abs(v)<1e12 end
local function read(object,method,...)
    if type(object)~="table" and type(object)~="userdata" then return nil end
    local ok,fn=pcall(function() return object[method] end)
    if not ok or type(fn)~="function" then return nil end
    local called,value=pcall(fn,object,...)
    if called then return value end
end
local function label(key)
    if type(key)~="string" or #key>1024 or key:find("%z") then return nil end
    if Locale and type(Locale.Lookup)=="function" then
        local ok,value=pcall(Locale.Lookup,key)
        if ok and type(value)=="string" and #value<=1024 and not value:find("%z") then return value end
    end
    return key
end
'''


def city_religion(a: dict) -> str:
    if "city_id" in a:
        identity = own_city(a["city_id"]) + 'local scope="self"\n'
    else:
        identity = f'''
if not visible_plot({a['x']},{a['y']}) or not CityManager or type(CityManager.GetCityAt)~="function" then return end
local city=CityManager.GetCityAt({a['x']},{a['y']})
if not city then return end
local owner=city:GetOwner()
if not known_player(owner) or city:GetX()~={a['x']} or city:GetY()~={a['y']} then return end
local scope="visible"
'''
    return "out.supported=false\n" + identity + HELPERS + r'''
local function collect_religion()
    local owner,id=city:GetOwner(),city:GetID()
    if not integer(owner,0,63) or not integer(id,0,2147483647) then return nil end
    local x,y
    if scope=="visible" then
        x,y=city:GetX(),city:GetY()
        if not integer(x,0,4095) or not integer(y,0,4095) then return nil end
        x,y=math.floor(x),math.floor(y)
    end
    local religion=read(city,"GetReligion")
    local majority=read(religion,"GetMajorityReligion")
    local present=read(religion,"GetReligionsInCity")
    if not integer(majority,-1,2147483647) or type(present)~="table" or not GameInfo or not GameInfo.Religions then return nil end
    local game_religion
    if Game and type(Game.GetReligion)=="function" then
        local ok,value=pcall(Game.GetReligion);if ok then game_religion=value end
    end
    local function definition(index)
        local row=GameInfo.Religions[index]
        if not row or type(row.ReligionType)~="string" or not row.ReligionType:match("^RELIGION_[A-Z0-9_]+$")
            or #row.ReligionType>128 then return nil end
        return row
    end
    local function name(index,row)
        local value=read(game_religion,"GetName",index)
        if type(value)=="string" and #value<=1024 and not value:find("%z") then return value end
        return label(row.Name)
    end
    local records={}
    local function put(key,value,name)
        records[#records+1]={id=key,value=value,name=name,scope=scope,owner_id=math.floor(owner),
            x=x,y=y,visible=scope=="visible" and true or nil}
    end
    if majority==-1 then put("majority_religion","NONE")
    else
        local row=definition(majority);if not row then return nil end
        put("majority_religion",row.ReligionType,name(majority,row))
    end
    local seen,count={},0
    for _,entry in pairs(present) do
        count=count+1;if count>128 or type(entry)~="table" then return nil end
        local index=entry.Religion
        if not integer(index,-1,2147483647) then return nil end
        if index>=0 then
            if seen[index] or not integer(entry.Followers,0,1000000000) then return nil end
            seen[index]=true
            local row=definition(index);if not row then return nil end
            put("religion:"..row.ReligionType..":followers",math.floor(entry.Followers),name(index,row))
        end
    end
    -- Optional normal lens conversion forecast, not raw pressure sources.
    local next_religion=read(religion,"GetNextReligion")
    local next_turns=read(religion,"GetTurnsToNextReligion")
    if integer(next_religion,0,2147483647) and integer(next_turns,1,2147483647) then
        local row=definition(next_religion)
        if row then
            put("next_religion",row.ReligionType,name(next_religion,row))
            put("turns_to_next_religion",math.floor(next_turns))
        end
    end
    if city:GetOwner()~=owner or city:GetID()~=id then return nil end
    if scope=="visible" and (not known_player(owner) or vis:IsRevealed(x,y)~=true
        or vis:IsVisible(x,y)~=true or city:GetX()~=x or city:GetY()~=y) then return nil end
    return records
end
local ok,records=pcall(collect_religion)
if not ok or type(records)~="table" then return end
out.supported=true
for _,record in ipairs(records) do add_item(record) end
'''


_BASE_PROJECTS = ["PROJECT_LAUNCH_EARTH_SATELLITE", "PROJECT_LAUNCH_MOON_LANDING",
                  "PROJECT_LAUNCH_MARS_REACTOR", "PROJECT_LAUNCH_MARS_HABITATION", "PROJECT_LAUNCH_MARS_HYDROPONICS"]
_GS_PROJECTS = _BASE_PROJECTS[:2] + ["PROJECT_LAUNCH_MARS_BASE", "PROJECT_LAUNCH_EXOPLANET_EXPEDITION"]


def own_science_victory(_: dict) -> str:
    return "out.supported=false\n" + HELPERS + f'''
local function collect_science()
    -- The normal ranking page is absent when this victory is disabled.
    if not Game or type(Game.IsVictoryEnabled)~="function"
        or Game.IsVictoryEnabled("VICTORY_TECHNOLOGY")~=true then return nil end
    if not GameConfiguration or type(GameConfiguration.GetValue)~="function" or not GameInfo.Projects then return nil end
    local rules=GameConfiguration.GetValue("RULESET")
    if rules~="RULESET_STANDARD" and rules~="RULESET_EXPANSION_1" and rules~="RULESET_EXPANSION_2" then return nil end
    local projects=rules=="RULESET_EXPANSION_2" and {lua(_GS_PROJECTS)} or {lua(_BASE_PROJECTS)}
    local stats=read(player,"GetStats")
    local cities=read(player,"GetCities")
    if not stats or not cities or type(cities.Members)~="function" then return nil end
    local records={{}}
    local function put(key,value,name)
        if #records>=2048 then error("unavailable") end
        records[#records+1]={{id=key,value=value,name=name,scope="self",owner_id=me}}
    end
    local rows={{}}
    local expedition_complete=false
    for _,identifier in ipairs(projects) do
        local row=GameInfo.Projects[identifier]
        if not row or not integer(row.Index,0,2147483647) or not integer(row.Hash,-2147483648,4294967295) then return nil end
        local count=read(stats,"GetNumProjectsAdvanced",row.Index)
        if not integer(count,0,2147483647) then return nil end
        put(identifier..":completed",count>0,label(row.Name))
        if identifier=="PROJECT_LAUNCH_EXOPLANET_EXPEDITION" then expedition_complete=count>0 end
        rows[#rows+1]=row
    end
    local checked=0
    for _,city in cities:Members() do
        checked=checked+1;if checked>256 then return nil end
        if city:GetOwner()==me then
            local id=city:GetID();if not integer(id,0,2147483647) then return nil end
            local queue=read(city,"GetBuildQueue")
            if not queue then return nil end
            local current=read(queue,"GetCurrentProductionTypeHash")
            for index,row in ipairs(rows) do
                local stem="city:"..tostring(math.floor(id))..":"..projects[index]
                local cost=read(queue,"GetProjectCost",row.Index)
                local progress=read(queue,"GetProjectProgress",row.Index)
                if finite(cost) and cost>=0 then put(stem..":cost",cost) end
                if finite(progress) and progress>=0 then put(stem..":progress",progress) end
                if integer(current,-2147483648,4294967295) then put(stem..":producing",current==row.Hash) end
            end
        end
    end
    if rules=="RULESET_EXPANSION_2" then
        for key,method in pairs({{light_years="GetScienceVictoryPoints",light_years_required="GetScienceVictoryPointsTotalNeeded"}}) do
            local value=read(stats,method)
            if finite(value) and value>=0 then put(key,value) end
        end
        -- Stock WorldRankings_Expansion2:585-589 only shows the rate after
        -- the expedition milestone. Never probe a hidden pre-launch rate.
        if expedition_complete then
            local value=read(stats,"GetScienceVictoryPointsPerTurn")
            if finite(value) and value>=0 then put("light_years_per_turn",value) end
        end
    end
    return records
end
local ok,records=pcall(collect_science)
if not ok or type(records)~="table" then return end
out.supported=true
for _,record in ipairs(records) do add_item(record) end
'''


ACTIONS = {}
QUERIES = {
    "city_religion": QuerySpec({"city_id": "id"}, city_religion,
        "Own city majority religion, present faiths/followers and optional stock-lens conversion forecast. No founder identities or pressure sources."),
    "visible_city_religion": QuerySpec({"x": "coord", "y": "coord"}, city_religion,
        "Religion lens fields for one currently visible, revealed city of a met player. Never scans foreign city collections or reads fog contents."),
    "own_science_victory": QuerySpec({}, own_science_victory,
        "Own normal science-victory projects: completion, own-city production cost/progress/current production, and GS expedition light years. Unknown fields omitted; no rival statistics."),
}
