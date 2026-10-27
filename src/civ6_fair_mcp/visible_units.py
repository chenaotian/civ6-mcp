"""Authored Lua for foreign units detected by the local player's engine state.

The authoritative gate is ``PlayersVisibility[me]:IsUnitVisible(unit)``, used
by the installed game's MapSearchPanel.lua:475 and WorldInput.lua:1041.
Plot visibility alone, unit type lists, distance heuristics, and cached flag
visibility are never accepted as substitutes. See docs/UNIT_VISIBILITY.md.
"""

UNIT_HELPERS = r'''
local function unit_public_integer(value, maximum)
    return type(value) == 'number' and value == value and
        value % 1 == 0 and value >= 0 and value <= maximum
end
local function unit_public_number(value)
    return type(value) == 'number' and value == value and
        value >= 0 and value <= 1000000
end
local function unit_public_read(unit, method)
    -- Called only AFTER the engine has proved per-unit detection.
    local ok, value = pcall(function()
        if type(unit[method]) ~= 'function' then return nil end
        return unit[method](unit)
    end)
    if ok then return value end
    return nil
end
local function unit_public_record(unit, x, y)
    if unit_public_read(unit, 'IsDelayedDeath') ~= false then return nil end
    local owner = unit_public_read(unit, 'GetOwner')
    local id = unit_public_read(unit, 'GetID')
    if not unit_public_integer(owner, 63) or owner == me or
       not unit_public_integer(id, 2147483647) then return nil end
    if unit_public_read(unit, 'GetX') ~= x or unit_public_read(unit, 'GetY') ~= y then
        return nil
    end
    local item = {owner_id=owner, id=id, x=x, y=y, detected=true}
    local unit_type = unit_public_read(unit, 'GetUnitType')
    if unit_public_integer(unit_type, 2147483647) and GameInfo and GameInfo.Units then
        local ok, definition = pcall(function() return GameInfo.Units[unit_type] end)
        if ok and definition and type(definition.UnitType) == 'string' and
           #definition.UnitType <= 128 and definition.UnitType:match('^[A-Z][A-Z0-9_]*$') then
            item.type = definition.UnitType
        end
    end
    local name = unit_public_read(unit, 'GetName')
    if type(name) == 'string' and #name <= 256 and Locale and type(Locale.Lookup) == 'function' then
        local ok, localized = pcall(Locale.Lookup, name)
        if ok and type(localized) == 'string' and #localized <= 256 and
           not localized:find('[%z\1-\31]') then item.name = localized end
    end
    -- Visible target stats appear in UnitPanel.ReadTargetData_Unit. Movement,
    -- build/spread charges, missions, abilities, and promotions are excluded.
    local fields = {
        {'damage', 'GetDamage'}, {'max_damage', 'GetMaxDamage'},
        {'combat', 'GetCombat'}, {'ranged_combat', 'GetRangedCombat'}
    }
    for _, field in ipairs(fields) do
        local value = unit_public_read(unit, field[2])
        if unit_public_number(value) then item[field[1]] = value end
    end
    return item
end
local function visible_units_at(plot, index)
    local empty = array({})
    -- Repeat the caller's plot guard before even obtaining the unit container.
    if vis:IsRevealed(index) ~= true or vis:IsVisible(index) ~= true then return nil end
    local gate_ok, unit_gate = pcall(function() return vis.IsUnitVisible end)
    if not gate_ok or type(unit_gate) ~= 'function' or Units == nil or
       type(Units.GetUnitsInPlotLayerID) ~= 'function' or MapLayers == nil or
       MapLayers.ANY == nil then return nil end
    local x, y = plot:GetX(), plot:GetY()
    if not unit_public_integer(x, 4095) or not unit_public_integer(y, 4095) then return nil end
    local list_ok, candidates = pcall(Units.GetUnitsInPlotLayerID, x, y, MapLayers.ANY)
    if not list_ok or type(candidates) ~= 'table' then return nil end
    local visible = {}
    local seen = {}
    for _, unit in pairs(candidates) do
        -- Absolutely no unit getters, owner/id/type reads, or counts before
        -- this engine gate, including for spies and promotion-based stealth.
        local detected_ok, detected = pcall(unit_gate, vis, unit)
        if detected_ok and detected == true then
            local item = unit_public_record(unit, x, y)
            if item ~= nil then
                local key = tostring(item.owner_id) .. ':' .. tostring(item.id)
                if not seen[key] then
                    seen[key] = true
                    visible[#visible + 1] = item
                end
            end
        end
    end
    -- Normalize only detected records so hidden units cannot affect ordering,
    -- truncation, or any reported total. There is no hidden/filtered count.
    table.sort(visible, function(a, b)
        if a.owner_id ~= b.owner_id then return a.owner_id < b.owner_id end
        return a.id < b.id
    end)
    for i = 1, math.min(#visible, 256) do empty[#empty + 1] = visible[i] end
    return empty
end
'''
