"""Optional plot-tooltip planning fields, only on currently visible tiles.

Base PlotToolTip.lua:346-397,470-471,637-675; GS retains the same display
rules at PlotToolTip_Expansion2.lua:223-274. No yield or resource getter.
"""

PLANNING_HELPERS = r'''
local function planning_read(plot,method)
    local ok,value=pcall(function()
        local getter=plot[method]
        if type(getter)=='function' then return getter(plot) end
    end)
    if ok then return value end
end
local function planning_number(value,low,high)
    return type(value)=='number' and value==value and value>=low and value<=high
end
local function add_visible_tile_planning(item,plot)
    -- Caller has already checked perception; preserve a local guard as well.
    if item.revealed~=true or item.visible~=true then return end
    local impassable=planning_read(plot,'IsImpassable')
    if type(impassable)=='boolean' then item.impassable=impassable end
    local lake=planning_read(plot,'IsLake')
    if type(lake)=='boolean' then item.lake=lake end
    if impassable==false then
        local cost=planning_read(plot,'GetMovementCost')
        if planning_number(cost,0,1000000) and cost>0 then item.movement_cost=cost end
    end
    local defense=planning_read(plot,'GetDefenseModifier')
    if planning_number(defense,-1000000,1000000) then item.defense_modifier=defense end
    -- Appeal is displayed only with this capability and on land or a natural
    -- wonder. Use the already public tile fields, not any neighboring plots.
    local appeal_ok,appeal=pcall(function()
        if not GameCapabilities or type(GameCapabilities.HasCapability)~='function'
            or GameCapabilities.HasCapability('CAPABILITY_LENS_APPEAL')~=true then return nil end
        if item.water~=false then
            local feature=GameInfo and GameInfo.Features and GameInfo.Features[item.feature]
            if not feature or feature.NaturalWonder~=true then return nil end
        end
        local amount=planning_read(plot,'GetAppeal')
        if not planning_number(amount,-1000000,1000000) or not GameInfo
            or not GameInfo.AppealHousingChanges then return nil end
        local count=0
        for row in GameInfo.AppealHousingChanges() do
            count=count+1
            if count>128 then return nil end
            if planning_number(row.MinimumValue,-1000000,1000000)
                and amount>=row.MinimumValue and type(row.Description)=='string' and #row.Description>0 then
                return amount
            end
        end
    end)
    if appeal_ok and appeal~=nil then item.appeal=appeal end
    local has_route=planning_read(plot,'IsRoute')
    if has_route==false then item.route='NONE'
    elseif has_route==true then
        local ok,identifier,cost=pcall(function()
            local index=planning_read(plot,'GetRouteType')
            if not planning_number(index,0,2147483647) or index%1~=0
                or not GameInfo or not GameInfo.Routes then return nil end
            local row=GameInfo.Routes[index]
            if not row or type(row.RouteType)~='string' or #row.RouteType>128
                or not row.RouteType:match('^ROUTE_[A-Z0-9_]+$')
                or type(row.Name)~='string' or #row.Name==0
                or not planning_number(row.MovementCost,0,1000000) then return nil end
            return row.RouteType,row.MovementCost
        end)
        if ok and identifier then
            item.route=identifier
            item.route_movement_cost=cost
            local pillaged=planning_read(plot,'IsRoutePillaged')
            if type(pillaged)=='boolean' then item.route_pillaged=pillaged end
        end
    end
end
'''
