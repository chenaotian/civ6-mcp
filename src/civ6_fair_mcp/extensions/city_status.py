"""Own city growth/status shown by the stock CitySupport and city overview UI.

Sources: Base/GS CitySupport.lua:474-490,526-581; RF CityPanelCulture.lua:88-98;
RF ReportScreen_Expansion1.lua:29-39. No identity-pressure source breakdowns.
GS CityPanelPower.lua:36-59 supplies the optional own-city power status.
"""
from .base import QuerySpec, lua, own_city


_GROWTH = (
    ("food_stored", "GetFood", "粮食库存"),
    ("growth_threshold", "GetGrowthThreshold", "下一人口所需粮食总量"),
    ("food_surplus", "GetFoodSurplus", "每回合粮食结余（增长修正前）"),
    ("overall_growth_multiplier", "GetOverallGrowthModifier", "总增长倍率（1 表示 100%）"),
    ("housing", "GetHousing", "住房"),
    ("housing_growth_multiplier", "GetHousingGrowthModifier", "住房增长倍率（1 表示 100%）"),
    ("amenities", "GetAmenities", "宜居度供给"),
    ("amenities_needed", "GetAmenitiesNeeded", "宜居度需求"),
    ("amenities_war_weariness", "GetAmenitiesLostFromWarWeariness", "厌战损失宜居度"),
    ("amenities_bankruptcy", "GetAmenitiesLostFromBankruptcy", "破产损失宜居度"),
)

_HELPERS = r'''
local function read(object,key)
    if type(object)~="table" and type(object)~="userdata" then return nil end
    local ok,value=pcall(function()
        local getter=object[key]
        if type(getter)=="function" then return getter(object) end
    end)
    if ok then return value end
    return nil
end
local function finite(value)
    return type(value)=="number" and value==value and math.abs(value)<1e12
end
local values={}
local function add(id,name,value)
    if value==nil then return end
    values[id]=value
    add_item({id=id,name=name,value=value,scope="self",owner_id=me})
end
local function number(id,object,key,name)
    local value=read(object,key)
    if finite(value) then add(id,name,value) end
end
local function text(id,rows,index)
    if not finite(index) or index%1~=0 or not rows then return end
    local ok,value=pcall(function()
        local row=rows[index]
        if not row or type(row.Name)~="string" then return nil end
        return Locale and type(Locale.Lookup)=="function" and Locale.Lookup(row.Name) or row.Name
    end)
    if ok and type(value)=="string" and #value<=1024 then add(id,nil,value) end
end
local function turns(id,object,key)
    local value=read(object,key)
    if finite(value) and value%1==0 and value>=-1 then
        add(id.."_active",nil,value~=-1)
        if value>=0 then add(id,nil,value) end
    end
end
'''


_POWER = '''
-- GS only: do not probe expansion components under unknown/base rules.
local gs=false
if GameConfiguration and type(GameConfiguration.GetValue)=="function" then
    local ok,rules=pcall(GameConfiguration.GetValue,"RULESET")
    gs=ok and rules=="RULESET_EXPANSION_2"
end
if gs then
    local power=read(city,"GetPower")
    local function power_number(key,method,label)
        local value=read(power,method)
        if finite(value) and value>=0 then
            -- Match the normal power panel's Round(value,1) display.
            add(key,label,math.floor(value*10+0.5)/10)
            return value
        end
    end
    local free=power_number("power_free","GetFreePower",''' + lua("本地可再生来源供电（电力点）") + ''')
    local temporary=power_number("power_temporary","GetTemporaryPower",''' + lua("本回合消耗资源提供的电力（电力点）") + ''')
    local required=power_number("power_required","GetRequiredPower",''' + lua("城市电力需求（电力点）") + ''')
    local fully=read(power,"IsFullyPowered")
    if type(fully)=="boolean" then add("power_fully_powered",''' + lua("城市是否完全供电") + ''',fully) end
    local project=nil
    -- The stock banner only asks this while fully powered. Missing is unknown.
    if fully==true then
        project=read(power,"IsFullyPoweredByActiveProject")
        if type(project)=="boolean" then add("power_from_active_project",''' + lua("是否由当前城市项目完全供电") + ''',project) end
    end
    local status,usable=nil,nil
    if required~=nil then
        if required==0 then
            status="not_required"
            if free~=nil and temporary~=nil then usable=free+temporary end
        elseif fully==false then
            status="underpowered"
            if free~=nil and temporary~=nil then usable=free+temporary end
        elseif fully==true then
            status="fully_powered"
            if project==true then usable=required
            elseif project==false and free~=nil and temporary~=nil then usable=free+temporary end
        end
    end
    if status then add("power_status",''' + lua("原版供电状态：not_required 无需求；fully_powered 完全供电；underpowered 供电不足") + ''',status) end
    if finite(usable) then add("power_usable",''' + lua("原版电力面板的可用电力（电力点；含项目供电分支）") + ''',math.floor(usable*10+0.5)/10) end
end
'''


_DEFENSE = r'''
-- CitySupport:GetCityData uses the player's main-district object, not a
-- guessed district type or a scan of units near the city.
local function district_read(district,method,argument)
    local ok,result=pcall(function()
        if type(district[method])~="function" then return nil end
        return district[method](district,argument)
    end)
    if ok then return result end
end
local center_id=read(city,"GetDistrictID")
if finite(center_id) and center_id%1==0 and center_id>=0 then
    local districts=read(player,"GetDistricts")
    local ok,center=pcall(function()
        if not districts or type(districts.FindID)~="function" then return nil end
        local candidate=districts:FindID(center_id)
        if candidate and candidate:GetOwner()==me and candidate:GetID()==center_id then return candidate end
    end)
    if ok and center then
        local strength=read(center,"GetDefenseStrength")
        if finite(strength) and strength>=0 then add("defense_strength","城市防御强度",math.floor(strength+0.5)) end
        for _,kind in ipairs({"GARRISON","OUTER"}) do
            local defense=DefenseTypes and DefenseTypes["DISTRICT_"..kind]
            if type(defense)=="number" then
                local maximum=district_read(center,"GetMaxDamage",defense)
                local damage=district_read(center,"GetDamage",defense)
                local prefix=kind=="GARRISON" and "garrison" or "walls"
                if finite(maximum) and maximum>=0 then
                    add(prefix.."_hp_maximum",nil,maximum)
                    if finite(damage) and damage>=0 and damage<=maximum then
                        add(prefix.."_hp",nil,maximum-damage)
                    end
                end
            end
        end
    end
end
-- A conversion estimate can mean gaining full loyalty OR rebellion. Keep
-- the stock outcome label; never call every positive estimate a rebellion.
local outcome=read(identity,"GetConversionOutcome")
if finite(outcome) and IdentityConversionOutcome then
    local direction
    if type(IdentityConversionOutcome.LOSING_LOYALTY)=="number"
        and outcome==IdentityConversionOutcome.LOSING_LOYALTY then direction="losing"
    elseif type(IdentityConversionOutcome.GAINING_LOYALTY)=="number"
        and outcome==IdentityConversionOutcome.GAINING_LOYALTY then direction="gaining" end
    if direction then
        add("loyalty_direction",nil,direction)
        local estimate=read(identity,"GetTurnsToConversion")
        if finite(estimate) and estimate%1==0 and estimate>=0 then
            add("loyalty_turns_to_outcome",nil,math.floor(estimate))
        end
    end
end
'''


def city_status(a):
    body = "out.supported=false\n" + own_city(a["city_id"]) + _HELPERS + '''
out.supported=true
number("population",city,"GetPopulation","人口")
local occupied=read(city,"IsOccupied")
if type(occupied)=="boolean" then add("occupied",nil,occupied) end
local growth=read(city,"GetGrowth")
'''
    for key, getter, label in _GROWTH:
        body += f"number({lua(key)},growth,{lua(getter)},{lua(label)})\n"
    return body + '''
if values.housing~=nil and values.population~=nil then
    add("housing_spare","住房减人口",values.housing-values.population)
end
if values.amenities~=nil and values.amenities_needed~=nil then
    add("amenities_net","宜居度供给减需求",values.amenities-values.amenities_needed)
end
turns("turns_until_growth",growth,"GetTurnsUntilGrowth")
turns("turns_until_starvation",growth,"GetTurnsUntilStarvation")
text("happiness",GameInfo.Happinesses,read(growth,"GetHappiness"))
local identity=read(city,"GetCulturalIdentity")
number("loyalty",identity,"GetLoyalty","忠诚度")
number("loyalty_maximum",identity,"GetMaxLoyalty","忠诚度上限")
number("loyalty_per_turn",identity,"GetLoyaltyPerTurn","每回合忠诚度变化")
text("loyalty_level",GameInfo.LoyaltyLevels,read(identity,"GetLoyaltyLevel"))
''' + _POWER + _DEFENSE


ACTIONS = {}
QUERIES = {
    "city_status": QuerySpec({"city_id": "id"}, city_status,
        "Own city housing, amenities, food, growth/starvation, loyalty direction/countdown, main-district defense/HP and GS power status. "
        "Power fields use the stock panel's one-decimal display and active-project branch. "
        "Missing fields are unknown; *_active=false is an engine -1 estimate, not zero turns. "
        "No foreign pressure sources or city details."),
}
