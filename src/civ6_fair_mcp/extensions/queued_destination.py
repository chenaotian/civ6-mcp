"""Optional own-unit queued movement goal, never an automation inference.

WorldInput.lua:813-823 and :1157-1166 read GetQueuedDestination for the
selected own unit. :882-915 checks the busy state, IgnoreMoves and Map.IsPlot.
The stock source does not document a no-goal sentinel; null/invalid values
remain unknown. Only a currently visible goal's coordinates are returned.
"""
from .base import lua


_STATUS = {
    "visible": "己方单位有排队移动目的地；坐标仅表示当前目标，不保证直达、可达或安全。",
    "hidden": "己方单位有排队移动目的地，但目标不在当前可见范围，坐标未披露。",
    "unknown": "当前无法确认排队移动目的地；不表示没有队列，也不判断是否正在自动探索。",
}


# Included only after the shared own_unit lookup. Do not use pathfinding or
# derive a route/automation mode from this single native goal identifier.
QUEUED_DESTINATION_OBSERVATION = f'''
do
    local labels={lua(_STATUS)}
    local function integer(value,low,high)
        return type(value)=="number" and value==value and value%1==0 and value>=low and value<=high
    end
    local function collect()
        if not UI or type(UI.IsGameCoreBusy)~="function" or UI.IsGameCoreBusy()~=false then return end
        if not GameInfo or not GameInfo.Units or type(unit.GetUnitType)~="function" then return end
        local unit_type=unit:GetUnitType()
        if not integer(unit_type,0,2147483647) then return end
        local definition=GameInfo.Units[unit_type]
        if not definition then return end
        local ignore=definition.IgnoreMoves
        if ignore~=nil and ignore~=false and ignore~=0 then return end
        if not UnitManager or type(UnitManager.GetQueuedDestination)~="function"
            or not Map or type(Map.IsPlot)~="function" then return end
        local goal=UnitManager.GetQueuedDestination(unit)
        if not integer(goal,0,2147483647) or Map.IsPlot(goal)~=true then return end
        -- Use the stock IsVisible(plotID) overload BEFORE constructing a plot.
        if not vis or type(vis.IsVisible)~="function" or type(vis.IsRevealed)~="function" then return end
        local visible=vis:IsVisible(goal)
        if visible==false then return "hidden" end
        if visible~=true then return end
        local revealed=vis:IsRevealed(goal)
        if revealed==false then return "hidden" end
        if revealed~=true then return end
        if type(Map.GetPlotByIndex)~="function" or type(Map.GetGridSize)~="function" then return end
        local width,height=Map.GetGridSize()
        if not integer(width,1,4096) or not integer(height,1,4096) then return end
        local plot=Map.GetPlotByIndex(goal)
        if not plot or type(plot.GetX)~="function" or type(plot.GetY)~="function" then return end
        local x,y=plot:GetX(),plot:GetY()
        if not integer(x,0,width-1) or not integer(y,0,height-1) then return end
        return "visible",math.floor(x),math.floor(y)
    end
    local ok,status,x,y=pcall(collect)
    if not ok or not labels[status] then status="unknown" end
    add_item({{id="queued_destination",scope="self",owner_id=me,value=status,description=labels[status]}})
    if status=="visible" then
        add_item({{id="queued_destination_x",scope="self",owner_id=me,value=x}})
        add_item({{id="queued_destination_y",scope="self",owner_id=me,value=y}})
    end
end
'''
