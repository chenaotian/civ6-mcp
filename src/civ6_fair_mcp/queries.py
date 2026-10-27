"""Strict player-perspective observations with no fog or foreign-state cache.

API evidence (original Firaxis UI source, also verified in the local Steam install):
* WorldViewIconsManager.lua:301: player resource layer with plot index.
* ToolTips/PlotToolTip.lua:316: player-specific IsResourceVisible(resourceHash).
* ToolTips/PlotToolTip.lua:721: IsRevealed and public plot fields.
* Panels/UnitPanel.lua: ReadUnitData, own unit movement/damage/build charges.
* ActionPanel.lua:438,644: GetFirstReadyUnit identifies the next own ready unit.
* TopPanel.lua: RefreshYields, own balances and yield rates.
* CitySupport.lua: own city population/production/aggregate yields.
https://github.com/chaorace/Civ6-UIFiles

Deliberately stricter than the base plot tooltip: revealed-but-not-visible plots
never have live contents read; tile yields and resource counts are omitted.
Foreign city centers require visibility and units require individual detection.
"""

from __future__ import annotations

from .lua_common import wrap
from .tile_planning import PLANNING_HELPERS
from .tile_hazards import HAZARD_HELPERS
from .visible_cities import CITY_HELPERS
from .visible_units import UNIT_HELPERS

_PLAYER = r'''
local treasury = player:GetTreasury()
local religion = player:GetReligion()
local techs = player:GetTechs()
local culture = player:GetCulture()
out.player = {
    gold=treasury:GetGoldBalance(),
    gold_per_turn=treasury:GetGoldYield() - treasury:GetTotalMaintenance(),
    faith=religion:GetFaithBalance(), faith_per_turn=religion:GetFaithYield(),
    science_per_turn=techs:GetScienceYield(), culture_per_turn=culture:GetCultureYield()
}
local research = techs:GetResearchingTech()
if research ~= nil and research >= 0 then
    local definition = GameInfo.Technologies[research]
    if definition ~= nil then out.player.research = definition.TechnologyType end
end
local civic = culture:GetProgressingCivic()
if civic ~= nil and civic >= 0 then
    local definition = GameInfo.Civics[civic]
    if definition ~= nil then out.player.civic = definition.CivicType end
end

out.units = array({})
local units = player:GetUnits()
local own_unit_ids = {}
for _, unit in units:Members() do
    -- Ownership is established before any details are inspected.
    if unit:GetOwner() == me then
        local x, y = unit:GetX(), unit:GetY()
        if x >= 0 and y >= 0 then
            local definition = GameInfo.Units[unit:GetUnitType()]
            out.units[#out.units + 1] = {
                owner_id=me, id=unit:GetID(), x=x, y=y,
                type=definition and definition.UnitType or 'UNKNOWN',
                name=Locale.Lookup(unit:GetName()),
                moves=unit:GetMovesRemaining(), max_moves=unit:GetMaxMoves(),
                damage=unit:GetDamage(), max_damage=unit:GetMaxDamage(),
                build_charges=unit:GetBuildCharges()
            }
            own_unit_ids[out.units[#out.units].id] = true
        end
    end
    if #out.units > 4096 then error('unavailable') end
end

-- Optional readiness is the same own-player API used by ActionPanel. Preserve
-- "none ready" separately from an unavailable API without encoding Lua nil.
if type(units.GetFirstReadyUnit) == 'function' then
    local ready_ok, ready = pcall(units.GetFirstReadyUnit, units)
    if ready_ok and ready == nil then
        out.first_ready_unit_checked = true
    elseif ready_ok and (type(ready) == 'table' or type(ready) == 'userdata')
        and type(ready.GetOwner) == 'function' and ready:GetOwner() == me then
        -- Ownership is checked before even looking up the ID getter.
        if type(ready.GetID) == 'function' then
            local id = ready:GetID()
            if own_unit_ids[id] then
                out.first_ready_unit_checked = true
                out.first_ready_unit_id = id
            end
        end
    end
end

-- Definitions are public rules; this does not inspect another player's queue.
local production_types = {}
for definition in GameInfo.Units() do production_types[definition.Hash] = definition.UnitType end
for definition in GameInfo.Buildings() do production_types[definition.Hash] = definition.BuildingType end
for definition in GameInfo.Districts() do production_types[definition.Hash] = definition.DistrictType end
for definition in GameInfo.Projects() do production_types[definition.Hash] = definition.ProjectType end
out.cities = array({})
for _, city in player:GetCities():Members() do
    if city:GetOwner() == me then
        local item = {
            owner_id=me, id=city:GetID(), x=city:GetX(), y=city:GetY(),
            name=Locale.Lookup(city:GetName()), population=city:GetPopulation(),
            food=city:GetYield(YieldTypes.FOOD),
            production_per_turn=city:GetYield(YieldTypes.PRODUCTION),
            gold_per_turn=city:GetYield(YieldTypes.GOLD),
            science_per_turn=city:GetYield(YieldTypes.SCIENCE),
            culture_per_turn=city:GetYield(YieldTypes.CULTURE),
            faith_per_turn=city:GetYield(YieldTypes.FAITH)
        }
        local queue = city:GetBuildQueue()
        if queue:GetSize() > 0 then
            item.production = production_types[queue:GetCurrentProductionTypeHash()]
            -- ProductionPanel (817/882/961/1048) renders -1 as "999+" and
            -- CITY_WILL_NOT_COMPLETE. It is a normal UI state, not an invalid
            -- city snapshot. A missing/unknown estimate remains optional.
            if type(queue.GetTurnsLeft) == 'function' then
                local turns_ok, turns = pcall(queue.GetTurnsLeft, queue)
                if turns_ok and turns == -1 then
                    item.production_indefinite = true
                elseif turns_ok and type(turns) == 'number' and turns >= 0 and
                       turns <= 2147483647 and turns % 1 == 0 then
                    item.production_turns = math.floor(turns)
                end
            end
        end
        out.cities[#out.cities + 1] = item
    end
    if #out.cities > 1024 then error('unavailable') end
end
'''

_MAP = r'''
local cx, cy, radius = __X__, __Y__, __RADIUS__
if Map.GetPlot(cx, cy) == nil then error('unavailable') end
out.tiles = array({})
local visited = {}
for dy = -radius, radius do
    for dx = -radius, radius do
        local plot = Map.GetPlot(cx + dx, cy + dy)
        if plot ~= nil then
            -- Index/coordinates identify public lattice cells, not contents.
            local index = plot:GetIndex()
            local x, y = plot:GetX(), plot:GetY()
            if not visited[index] and Map.GetPlotDistance(cx, cy, x, y) <= radius then
                visited[index] = true
                local revealed = vis:IsRevealed(index) == true
                local visible = revealed and vis:IsVisible(index) == true
                local item = {x=x, y=y, revealed=revealed, visible=visible}
                -- The gate PRECEDES every read of live tile contents.
                if revealed and visible then
                    local terrain = GameInfo.Terrains[plot:GetTerrainType()]
                    local feature = GameInfo.Features[plot:GetFeatureType()]
                    item.terrain = terrain and terrain.TerrainType or 'UNKNOWN'
                    item.feature = feature and feature.FeatureType or 'NONE'
                    item.hills = plot:IsHills()
                    item.river = plot:IsRiver()
                    item.water = plot:IsWater()
                    item.owner_id = plot:GetOwner()
                    add_visible_tile_hazards(item, plot)
                    add_visible_tile_planning(item, plot)
                    -- PlotToolTip.lua:673-675 reads these three cliff-edge
                    -- flags. Keep the exact API orientation names; never read
                    -- neighboring or fogged plots to reconstruct other edges.
                    for field,method in pairs({is_nw_of_cliff='IsNWOfCliff',
                            is_w_of_cliff='IsWOfCliff',is_ne_of_cliff='IsNEOfCliff'}) do
                        local ok,value=pcall(function()
                            local getter=plot[method]
                            if type(getter)=='function' then return getter(plot) end
                        end)
                        if ok and type(value)=='boolean' then item[field]=value end
                    end
                    -- PlotToolTip.FetchData reads the district on this exact
                    -- tile (line 647). No owning-city district list is needed.
                    if type(plot.GetDistrictType) == 'function' then
                        local ok, district_index = pcall(plot.GetDistrictType, plot)
                        if ok and district_index == -1 then
                            item.district = 'NONE'
                        elseif ok and type(district_index) == 'number' and
                               district_index >= 0 and district_index % 1 == 0 and
                               GameInfo.Districts ~= nil then
                            local definition = GameInfo.Districts[district_index]
                            local district = definition and definition.DistrictType
                            if type(district) == 'string' and #district <= 128 and
                               district:match('^DISTRICT_[A-Z0-9_]+$') then
                                item.district = district
                            end
                        end
                    end
                    -- Goody huts and barbarian camps are improvements, not features.
                    -- Only inspect the current visible tile; never inspect hut rewards.
                    if type(plot.GetImprovementType) == 'function' then
                        local ok, improvement_index = pcall(plot.GetImprovementType, plot)
                        if ok and improvement_index == -1 then
                            item.improvement = 'NONE'
                        elseif ok and type(improvement_index) == 'number' and
                               improvement_index >= 0 and improvement_index % 1 == 0 and
                               GameInfo.Improvements ~= nil then
                            local definition = GameInfo.Improvements[improvement_index]
                            if definition ~= nil and type(definition.ImprovementType) == 'string' then
                                item.improvement = definition.ImprovementType
                                if type(plot.IsImprovementPillaged) == 'function' then
                                    local pillaged_ok, pillaged = pcall(plot.IsImprovementPillaged, plot)
                                    if pillaged_ok and type(pillaged) == 'boolean' then
                                        item.improvement_pillaged = pillaged
                                    end
                                end
                            end
                        end
                    end
                    item.units = visible_units_at(plot, index)
                    item.city = visible_city_at(plot, index)
                    -- Player resource layer used by WorldViewIconsManager,
                    -- AND unlock proof used by PlotToolTip. No raw type read.
                    if type(vis.GetLayerValue) == 'function' and
                       VisibilityLayerTypes ~= nil and VisibilityLayerTypes.RESOURCES ~= nil and
                       type(player.GetResources) == 'function' then
                        local resource_index = vis:GetLayerValue(VisibilityLayerTypes.RESOURCES, index)
                        if type(resource_index) == 'number' and resource_index >= 0 then
                            local resource = GameInfo.Resources[resource_index]
                            local resources = player:GetResources()
                            if resource ~= nil and type(resource.ResourceType) == 'string' and
                               type(resource.Hash) == 'number' and resources ~= nil and
                               type(resources.IsResourceVisible) == 'function' and
                               resources:IsResourceVisible(resource.Hash) == true then
                                item.resource = resource.ResourceType
                                item.resource_visible = true
                            end
                        end
                    end
                end
                out.tiles[#out.tiles + 1] = item
            end
        end
    end
end
'''


def build_player_query(nonce: str) -> str:
    """Observe only the bound local player's own public-to-them state."""
    return wrap(_PLAYER, nonce)


def build_map_query(nonce: str, x: int, y: int, radius: int) -> str:
    """Observe at most a radius-eight hex region, masking every nonvisible tile."""
    for value, minimum, maximum in ((x, 0, 4095), (y, 0, 4095), (radius, 0, 8)):
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError("Invalid map request")
    body = _MAP.replace("__X__", str(x)).replace("__Y__", str(y)).replace("__RADIUS__", str(radius))
    return wrap(UNIT_HELPERS + "\n" + CITY_HELPERS + "\n" + HAZARD_HELPERS + "\n" + PLANNING_HELPERS + "\n" + body, nonce)
