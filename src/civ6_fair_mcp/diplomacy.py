"""Read-only, met-civilization intelligence from the installed vanilla GS UI.

The player explicitly permits public ribbon statistics and public victory data.
This is still a disclosure allowlist: no foreign cities/districts, unseen player
identity, unrevealed agenda, AI strategy, or generic requirement dump is read.
See docs/DIPLOMACY_POLICY.md for installed-source evidence and omitted fields.
"""

from __future__ import annotations

from .lua_common import wrap
from .diplomatic_relationships import RELATIONSHIP_HELPERS


_BODY = r'''
local function finite(value)
    return type(value) == 'number' and value == value
        and value ~= math.huge and value ~= -math.huge and math.abs(value) < 1e15
end
local function identifier(value)
    return type(value) == 'string' and #value <= 128
        and value:match('^[A-Z][A-Z0-9_]*$') ~= nil
end
local function optional(target, key, fn, kind)
    local good, value = pcall(fn)
    if not good then return end
    if kind == 'number' and finite(value) then target[key] = value
    elseif kind == 'boolean' and type(value) == 'boolean' then target[key] = value
    elseif kind == 'identifier' and identifier(value) then target[key] = value
    elseif kind == 'string' and type(value) == 'string' and #value <= 1024 then
        target[key] = value
    elseif kind == 'array' and type(value) == 'table' then target[key] = value end
end
local function enabled(fn)
    local good, value = pcall(fn)
    return good and value == true
end
local function capability(name)
    return enabled(function() return GameCapabilities.HasCapability(name) end)
end
local function victory_enabled(name)
    return enabled(function() return Game.IsVictoryEnabled(name) end)
end
local function rounded(value, places)
    if not finite(value) then error('unavailable') end
    -- Installed SupportFunctions.lua Round: floor(num * mult + 0.5) / mult.
    if places == nil then return math.floor(value + 0.5) end
    local mult = 10 ^ places
    return math.floor(value * mult + 0.5) / mult
end
local function whole(value)
    if not finite(value) or value < 0 or value % 1 ~= 0 then error('unavailable') end
    -- Lua runtimes may return 8.0 from an integer-count getter. Preserve the
    -- integer wire schema without silently converting fractional engine values.
    return math.floor(value)
end
''' + RELATIONSHIP_HELPERS + r'''

-- This installed GS API returns major civilizations that actually participated,
-- including eliminated civilizations. Counting the list needs no unknown identity.
local participants = PlayerManager.GetWasEverAliveMajors()
if type(participants) ~= 'table' or #participants < 1 or #participants > 64 then
    error('unavailable')
end
out.civilization_count = #participants
out.civilizations = array({})
local diplomacy = player:GetDiplomacy()
local seen = {}
for _, other in ipairs(participants) do
    -- A numeric slot is needed solely to ask the LOCAL player's HasMet gate.
    -- For an unmet slot, no config, life state, agenda, economy, or stats is read.
    local id = other:GetID()
    if type(id) ~= 'number' or id % 1 ~= 0 or id < 0 or id > 63 or seen[id] then
        error('unavailable')
    end
    seen[id] = true
    local known = id == me or enabled(function() return diplomacy:HasMet(id) end)
    if known then
        local item = {id=id, met=true}
        local configuration = PlayerConfigurations[id]
        optional(item, 'civilization', function() return configuration:GetCivilizationTypeName() end, 'identifier')
        optional(item, 'leader', function() return configuration:GetLeaderTypeName() end, 'identifier')
        optional(item, 'name', function() return Locale.Lookup(configuration:GetPlayerName()) end, 'string')
        optional(item, 'alive', function() return other:IsAlive() end, 'boolean')
        optional(item, 'at_war', function()
            if id == me then return false end
            return diplomacy:IsAtWarWith(id)
        end, 'boolean')
        if item.alive == true then
            if id~=me then item.relationship=public_relationship(other,id,configuration) end
            -- Match public ribbon capability gates AND its displayed precision.
            local yields = capability('CAPABILITY_DISPLAY_TOP_PANEL_YIELDS')
            if yields and capability('CAPABILITY_GOLD') then
                optional(item, 'gold', function() return math.floor(other:GetTreasury():GetGoldBalance()) end, 'number')
                -- Exact foreign net GPT is not proven by the installed ribbon UI.
                if id == me then
                    optional(item, 'gold_per_turn', function()
                        local treasury = other:GetTreasury()
                        return treasury:GetGoldYield() - treasury:GetTotalMaintenance()
                    end, 'number')
                end
            end
            if yields and capability('CAPABILITY_SCIENCE') then
                optional(item, 'science_per_turn', function() return rounded(other:GetTechs():GetScienceYield()) end, 'number')
            end
            if yields and capability('CAPABILITY_CULTURE') then
                optional(item, 'culture_per_turn', function() return rounded(other:GetCulture():GetCultureYield()) end, 'number')
            end
            if yields and victory_enabled('VICTORY_CONQUEST') then
                optional(item, 'military_strength', function()
                    return rounded(other:GetStats():GetMilitaryStrengthWithoutTreasury())
                end, 'number')
            end
            if capability('CAPABILITY_DISPLAY_SCORE') and victory_enabled('VICTORY_SCORE') then
                optional(item, 'score', function() return rounded(other:GetScore()) end, 'number')
            end

            optional(item, 'agendas', function()
                local values, added = array({}), {}
                local human = configuration:IsHuman()
                if human == true then return values end
                if human ~= false then error('unavailable') end
                local access = diplomacy:GetVisibilityOn(id)
                if not finite(access) or access < 0 then error('unavailable') end
                local entries = other:GetAgendasAndVisibilities()
                if type(entries) ~= 'table' or #entries > 64 then error('unavailable') end
                for _, entry in ipairs(entries) do
                    -- GS uses per-agenda access thresholds. Never look up the
                    -- identity/definition of an entry failing this exact gate.
                    local required = entry.Visibility
                    if finite(required) and required >= 0 and required <= access then
                        local definition = GameInfo.Agendas[entry.Agenda]
                        local agenda = definition and definition.AgendaType
                        if identifier(agenda) and not added[agenda] then
                            values[#values + 1] = {id=agenda, visible=true}
                            added[agenda] = true
                        end
                    end
                end
                table.sort(values, function(a, b) return a.id < b.id end)
                return values
            end, 'array')

            local progress = {}
            if victory_enabled('VICTORY_TECHNOLOGY') then
                optional(progress, 'science_techs_researched', function()
                    return whole(other:GetStats():GetNumTechsResearched())
                end, 'number')
                local projects = {
                    {'science_satellite_completed', 'PROJECT_LAUNCH_EARTH_SATELLITE'},
                    {'science_moon_completed', 'PROJECT_LAUNCH_MOON_LANDING'},
                    {'science_mars_completed', 'PROJECT_LAUNCH_MARS_BASE'},
                    {'science_exoplanet_completed', 'PROJECT_LAUNCH_EXOPLANET_EXPEDITION'}
                }
                for _, project in ipairs(projects) do
                    optional(progress, project[1], function()
                        local definition = GameInfo.Projects[project[2]]
                        if definition == nil or not finite(definition.Index) then error('unavailable') end
                        local completed = other:GetStats():GetNumProjectsAdvanced(definition.Index)
                        if not finite(completed) or completed < 0 then error('unavailable') end
                        return completed > 0
                    end, 'boolean')
                end
                -- GS does not show expedition travel before launch; never read it.
                if progress.science_exoplanet_completed == true then
                    optional(progress, 'science_light_years', function()
                        local needed = player:GetStats():GetScienceVictoryPointsTotalNeeded()
                        local current = other:GetStats():GetScienceVictoryPoints()
                        if not finite(needed) or needed <= 0 or not finite(current) or current < 0 then
                            error('unavailable')
                        end
                        return math.min(current, needed)
                    end, 'number')
                    optional(progress, 'science_light_years_per_turn', function()
                        return other:GetStats():GetScienceVictoryPointsPerTurn()
                    end, 'number')
                end
            end
            if victory_enabled('VICTORY_CULTURE') then
                optional(progress, 'culture_domestic_tourists', function()
                    return whole(other:GetCulture():GetStaycationers())
                end, 'number')
                optional(progress, 'culture_visiting_tourists', function()
                    return whole(other:GetCulture():GetTouristsTo())
                end, 'number')
            end
            if victory_enabled('VICTORY_RELIGIOUS') then
                optional(progress, 'religion_cities_following', function()
                    return whole(other:GetStats():GetNumCitiesFollowingReligion())
                end, 'number')
                optional(progress, 'religion_faith_per_turn', function()
                    return rounded(other:GetReligion():GetFaithYield(), 1)
                end, 'number')
            end
            if victory_enabled('VICTORY_DIPLOMATIC') then
                optional(progress, 'diplomatic_points', function()
                    return whole(other:GetStats():GetDiplomaticVictoryPoints())
                end, 'number')
                optional(progress, 'diplomatic_points_required', function()
                    return whole(GlobalParameters.DIPLOMATIC_VICTORY_POINTS_REQUIRED)
                end, 'number')
            end
            if next(progress) ~= nil then item.victory = progress end
        end
        out.civilizations[#out.civilizations + 1] = item
    end
end
if not seen[me] then error('unavailable') end
table.sort(out.civilizations, function(a, b) return a.id < b.id end)
'''


def build_diplomacy_query(nonce: str) -> str:
    """Return public intelligence only for self or met major civilizations."""
    return wrap(_BODY, nonce)
