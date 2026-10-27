"""Visible-city fields authorized by the user's P02 rule.

CITY_HELPERS is an authored Lua fragment for lua_common.wrap. The caller must
already have proved the plot revealed and visible, and this helper repeats that
proof. Only the city centered on that exact plot is inspected. No foreign player
collections, hidden district coordinates, city yields, or other cities are read.

Verified against the installed Gathering Storm UI sources:
* DLC/Expansion2/UI/CityBanners/CityBannerManager.lua:3082,3088: GetCityAt /
  GetDistrictAt(x,y); :1285-1288: center and wall damage; :1024: population;
  :1908: majority religion; :909-972: production hash and turns by type.
* DLC/Expansion2/UI/Replacements/CitySupport.lua:668: city-local
  HasDistrict(index,true) (completed); :730,747: HasBuilding(index).

Optional groups are omitted when the corresponding API is absent, throws,
returns invalid data, or exceeds a bound. Unknown production identifiers and
negative/unavailable turn estimates are omitted, not guessed. NONE denotes a
verified absent majority religion or empty production. District/building arrays
contain completed/present public type identifiers, not locations or yields.
These are the user's configured disclosure rules, not a claim that every stock
UI configuration normally displays an opponent's complete production queue.
"""

CITY_HELPERS = r'''
local function vc_integer(value, maximum)
    if type(value) ~= 'number' or value ~= value or value % 1 ~= 0
        or value < 0 or value > (maximum or 2147483647) then return nil end
    return math.floor(value)
end
local function vc_identifier(value, prefix)
    if type(value) ~= 'string' or #value > 128
        or not value:match('^[A-Z][A-Z0-9_]*$') then return nil end
    if prefix and value:sub(1, #prefix) ~= prefix then return nil end
    return value
end
local function vc_optional(fn)
    local success, value = pcall(fn)
    if success then return value end
    return nil
end

local function vc_present_types(definitions, collection, method, field, prefix, completed)
    local result = array({})
    local seen = {}
    local scanned = 0
    if collection == nil or type(collection[method]) ~= 'function' then return nil end
    for definition in definitions() do
        scanned = scanned + 1
        if scanned > 4096 then return nil end
        local identifier = vc_identifier(definition[field], prefix)
        local type_index = vc_integer(definition.Index)
        if identifier ~= nil and type_index ~= nil and not definition.InternalOnly then
            local exists
            if completed then
                exists = collection[method](collection, type_index, true)
            else
                exists = collection[method](collection, type_index)
            end
            if exists == true and not seen[identifier] then
                if #result >= 512 then return nil end
                result[#result + 1] = identifier
                seen[identifier] = true
            end
        end
    end
    table.sort(result)
    return result
end

local function visible_city_at(plot, index)
    -- Failure has one representation; never expose raw engine exception text.
    return vc_optional(function()
        if plot == nil or vc_integer(index) == nil then return nil end
        if vis:IsRevealed(index) ~= true or vis:IsVisible(index) ~= true then return nil end
        if plot:GetIndex() ~= index then return nil end
        local x, y = vc_integer(plot:GetX(), 65535), vc_integer(plot:GetY(), 65535)
        if x == nil or y == nil or plot:IsCity() ~= true then return nil end
        if CityManager == nil or type(CityManager.GetCityAt) ~= 'function' then return nil end
        local city = CityManager.GetCityAt(x, y)
        if city == nil then return nil end
        -- GetCityAt/purchase-city semantics must never resolve a remote city.
        -- Read only geometry until exact center identity is established.
        if city:GetX() ~= x or city:GetY() ~= y then return nil end
        if vis:IsRevealed(index) ~= true or vis:IsVisible(index) ~= true then return nil end
        local owner = vc_integer(city:GetOwner(), 63)
        local city_id = vc_integer(city:GetID())
        local population = vc_integer(city:GetPopulation())
        local name = Locale.Lookup(city:GetName())
        if owner == nil or city_id == nil or population == nil or type(name) ~= 'string' then return nil end
        name = name:gsub('[%z\1-\31]', '')
        -- Count UTF-8 leading bytes, preserving multibyte names intact.
        local _, name_length = name:gsub('[^\128-\191]', '')
        if name_length > 256 then return nil end
        local result = {id=city_id, owner_id=owner, x=x, y=y, name=name,
            population=population, visible=true}

        -- A direct lookup of the visible center avoids foreign player/district
        -- scans. Any non-center or mismatched object is rejected before HP reads.
        local health = vc_optional(function()
            if type(CityManager.GetDistrictAt) ~= 'function' then return nil end
            local center = CityManager.GetDistrictAt(x, y)
            if center == nil or center:GetX() ~= x or center:GetY() ~= y then return nil end
            if center:GetOwner() ~= owner then return nil end
            local definition = GameInfo.Districts[center:GetType()]
            if definition == nil or definition.DistrictType ~= 'DISTRICT_CITY_CENTER' then return nil end
            if DefenseTypes == nil or DefenseTypes.DISTRICT_GARRISON == nil
                or DefenseTypes.DISTRICT_OUTER == nil then return nil end
            local damage = vc_integer(center:GetDamage(DefenseTypes.DISTRICT_GARRISON))
            local maximum = vc_integer(center:GetMaxDamage(DefenseTypes.DISTRICT_GARRISON))
            local wall_damage = vc_integer(center:GetDamage(DefenseTypes.DISTRICT_OUTER))
            local wall_maximum = vc_integer(center:GetMaxDamage(DefenseTypes.DISTRICT_OUTER))
            if damage == nil or maximum == nil or wall_damage == nil or wall_maximum == nil
                or damage > maximum or wall_damage > wall_maximum then return nil end
            return {damage=damage, max_damage=maximum,
                wall_damage=wall_damage, wall_max_damage=wall_maximum}
        end)
        if health ~= nil then
            result.damage, result.max_damage = health.damage, health.max_damage
            result.wall_damage, result.wall_max_damage = health.wall_damage, health.wall_max_damage
        end

        result.religion = vc_optional(function()
            local majority = city:GetReligion():GetMajorityReligion()
            if type(majority) ~= 'number' or majority % 1 ~= 0 then return nil end
            if majority <= 0 then return 'NONE' end
            local definition = GameInfo.Religions[majority]
            if definition == nil then return nil end
            return vc_identifier(definition.ReligionType, 'RELIGION_')
        end)

        local production = vc_optional(function()
            local queue = city:GetBuildQueue()
            if queue == nil then return nil end
            local hash = queue:GetCurrentProductionTypeHash()
            if type(hash) ~= 'number' or hash % 1 ~= 0 then return nil end
            if hash == 0 then return {production='NONE', production_turns=0} end
            local choices = {
                {GameInfo.Buildings, 'BuildingType', 'BUILDING_'},
                {GameInfo.Districts, 'DistrictType', 'DISTRICT_'},
                {GameInfo.Units, 'UnitType', 'UNIT_'},
                {GameInfo.Projects, 'ProjectType', 'PROJECT_'}
            }
            for _, choice in ipairs(choices) do
                local definition = choice[1][hash]
                local identifier = definition and vc_identifier(definition[choice[2]], choice[3])
                if identifier ~= nil and not definition.InternalOnly then
                    local turns = vc_optional(function()
                        if choice[2] == 'UnitType' then
                            local formation = queue:GetCurrentProductionTypeModifier()
                            return vc_integer(queue:GetTurnsLeft(identifier, formation))
                        end
                        return vc_integer(queue:GetTurnsLeft(identifier))
                    end)
                    return {production=identifier, production_turns=turns}
                end
            end
            return nil
        end)
        if production ~= nil then
            result.production, result.production_turns = production.production, production.production_turns
        end

        result.districts = vc_optional(function()
            return vc_present_types(GameInfo.Districts, city:GetDistricts(),
                'HasDistrict', 'DistrictType', 'DISTRICT_', true)
        end)
        result.buildings = vc_optional(function()
            return vc_present_types(GameInfo.Buildings, city:GetBuildings(),
                'HasBuilding', 'BuildingType', 'BUILDING_', false)
        end)
        -- Do not return an observation that lost its visibility proof.
        if vis:IsRevealed(index) ~= true or vis:IsVisible(index) ~= true then return nil end
        return result
    end)
end
'''
