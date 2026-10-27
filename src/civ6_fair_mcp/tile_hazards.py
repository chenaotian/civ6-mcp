"""Optional current-visible tile hazards from the stock Gathering Storm tooltip.

PlotTooltip_Expansion2.lua:23-25 reads these exact plot-local APIs; :215-220
displays the RandomEvents title and remaining drought turns. The caller must
establish current visibility before invoking this helper. No global disaster
enumeration, footprint, trajectory, affected city, or historical data is read.
"""

HAZARD_HELPERS = r'''
local function tile_hazard_read(method, plot)
    local ok, value = pcall(function()
        if GameClimate == nil then return nil end
        local getter = GameClimate[method]
        if type(getter) ~= 'function' then return nil end
        -- Stock API takes the plot directly, not a GameClimate receiver.
        return getter(plot)
    end)
    if ok then return value end
end

local function tile_hazard_definition(value)
    if value == -1 then return 'NONE' end
    if type(value) ~= 'number' or value % 1 ~= 0 or
       value < -2147483648 or value > 4294967295 then return nil end
    local ok, event_type, name = pcall(function()
        if GameInfo == nil or GameInfo.RandomEvents == nil then return nil end
        local row = GameInfo.RandomEvents[value]
        if row == nil then return nil end
        local identifier = row.RandomEventType
        if type(identifier) ~= 'string' or #identifier > 128 or
           not identifier:match('^RANDOM_EVENT_[A-Z0-9_]+$') then return nil end
        return identifier, row.Name
    end)
    if ok then return event_type, name end
end

local function tile_hazard_name(key)
    if type(key) ~= 'string' or #key == 0 or #key > 256 then return nil end
    local ok, name = pcall(function()
        if Locale ~= nil and type(Locale.Lookup) == 'function' then
            return Locale.Lookup(key)
        end
    end)
    if ok and type(name) == 'string' and #name > 0 and #name <= 256 and
       not name:find('[%z\1-\31]') then return name end
end

local function add_visible_tile_hazards(item, plot)
    for field, method in pairs({storm='GetActiveStormTypeAtPlot',
                               drought='GetActiveDroughtTypeAtPlot'}) do
        local event_type, name = tile_hazard_definition(tile_hazard_read(method, plot))
        if event_type ~= nil then
            item[field .. '_type'] = event_type
            if event_type ~= 'NONE' then
                item[field .. '_name'] = tile_hazard_name(name)
                if field == 'drought' then
                    local turns = tile_hazard_read('GetDroughtTurnsAtPlot', plot)
                    if type(turns) == 'number' and turns % 1 == 0 and
                       turns >= 0 and turns <= 1000000 then
                        item.drought_turns = math.floor(turns)
                    end
                end
            end
        end
    end
end
'''
