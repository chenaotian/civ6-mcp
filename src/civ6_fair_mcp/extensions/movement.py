"""Bounded public movement preview and a fixed revealed-goal movement request.

WorldInput.lua:884 checks IsGameCoreBusy and :897-900 excludes IgnoreMoves; :961 calls
UnitManager.GetMoveToPathEx(unit, plotIndex). Its plots are numeric plot IDs
(:965-966), turns are matched to plots (:1052-1058), and entrancePortals /
exitPortals are separate path display geometry (:1124-1141). No path metadata
is returned until every plot is currently visible; portal paths stay unknown.
"""
from .base import ActionSpec, QuerySpec, lua, own_unit


_STATUS = {
    "direct": "原版当前预览为直接进入相邻目标格；不保证安全或请求提交后到达。",
    "detour": "原版当前预览需绕路；相邻目标不会按这份预览直接一步到达。",
    "route": "原版当前预览有到达远处目标的全程可见路线；不保证最短、安全或提交后到达。",
    "no_path": "原版当前预览没有到目标的路线；不说明具体阻挡原因。",
    "unknown": "当前公开信息不足以确认路线；不提供下一步或预计回合。",
}


def unit_move_preview(a: dict) -> str:
    return "out.supported=false\n" + own_unit(a["unit_id"]) + f'''
local labels={lua(_STATUS)}
local function integer(value,low,high)
    return type(value)=="number" and value==value and value%1==0 and value>=low and value<=high
end
local function status(value)
    return {{{{id="status",scope="self",owner_id=me,value=value,description=labels[value]}}}}
end
local function scalar(items,id,value,description)
    items[#items+1]={{id=id,scope="self",owner_id=me,value=math.floor(value),description=description}}
end
local function dense(values,maximum)
    if type(values)~="table" then return nil end
    local count,seen=0,{{}}
    for key in pairs(values) do
        if not integer(key,1,maximum) then return nil end
        count=count+1
        if count>maximum then return nil end
        seen[key]=true
    end
    -- Civ VI's Lua runtime omits rawget. Check our own plain index set,
    -- never a potentially missing values[index] and its __index fallback.
    for index=1,count do if seen[index]~=true then return nil end end
    return count
end
local function collect()
    if not Map or type(Map.GetGridSize)~="function" or type(Map.GetPlotDistance)~="function"
        or type(Map.GetPlot)~="function" or type(Map.GetPlotByIndex)~="function"
        or not UnitManager or type(UnitManager.GetMoveToPathEx)~="function"
        or not UI or type(UI.IsGameCoreBusy)~="function"
        or type(vis.IsVisible)~="function" or type(vis.IsRevealed)~="function" then return nil end
    local busy=UI.IsGameCoreBusy()
    if type(busy)~="boolean" then return nil end
    if busy then return status("unknown") end
    -- Stock preview excludes traders, spies and air units using IgnoreMoves.
    -- This is the owned actor's static definition, not another unit's state.
    if type(unit.GetUnitType)~="function" or not GameInfo or not GameInfo.Units then return nil end
    local unit_type=unit:GetUnitType()
    if not integer(unit_type,0,2147483647) then return nil end
    local definition=GameInfo.Units[unit_type]
    if not definition then return nil end
    local ignore=definition.IgnoreMoves
    if ignore==true or ignore==1 then return status("unknown") end
    if ignore~=nil and ignore~=false and ignore~=0 then return nil end
    local width,height=Map.GetGridSize()
    if not integer(width,1,4096) or not integer(height,1,4096) then return nil end
    local x,y=unit:GetX(),unit:GetY()
    if not integer(x,0,width-1) or not integer(y,0,height-1)
        or {a['x']}>=width or {a['y']}>=height then return nil end
    local distance=Map.GetPlotDistance(x,y,{a['x']},{a['y']})
    if not integer(distance,0,8192) then return nil end
    if distance==0 then return status("unknown") end
    -- A request for a fogged target is not a pathfinder probe. Check before
    -- Map.GetPlot or any plot getter, including the destination's index.
    if vis:IsRevealed(x,y)~=true or vis:IsVisible(x,y)~=true
        or vis:IsRevealed({a['x']},{a['y']})~=true or vis:IsVisible({a['x']},{a['y']})~=true then
        return status("unknown")
    end
    local origin,target=Map.GetPlot(x,y),Map.GetPlot({a['x']},{a['y']})
    if not origin or not target or type(origin.GetIndex)~="function"
        or type(target.GetIndex)~="function" then return nil end
    local start_id,target_id=origin:GetIndex(),target:GetIndex()
    local max_id=width*height-1
    if not integer(start_id,0,max_id) or not integer(target_id,0,max_id)
        or start_id==target_id then return nil end
    local path=UnitManager.GetMoveToPathEx(unit,target_id)
    if type(path)~="table" then return nil end
    local plots=path.plots
    local count=dense(plots,4096)
    if count==nil then return nil end
    -- IsVisible(plotID) is the exact stock WorldInput.lua:1006 overload.
    -- Inspect no geometry, turn count, obstacle or portal before this gate.
    for index=1,count do
        local id=plots[index]
        if not integer(id,0,max_id) then return nil end
        if vis:IsVisible(id)~=true or vis:IsRevealed(id)~=true then return status("unknown") end
    end
    -- Portal geometry can alter the real first transition. Do not guess its
    -- meaning or expose a portal outside the currently visible path.
    for _,name in ipairs({{"entrancePortals","exitPortals"}}) do
        local portals=path[name]
        if type(portals)~="table" then return nil end
        local n=0
        for index,id in pairs(portals) do
            n=n+1
            if n>4096 or not integer(index,1,count) then return nil end
            -- Stock tests `if portal and portal >= 0`: false/nil and any
            -- negative number mean no portal. Reject nonnumeric truthy and
            -- nonfinite markers; any actual portal remains unreported.
            if id~=false then
                if type(id)~="number" or id-id~=0 then return nil end
                if id>=0 then return status("unknown") end
            end
        end
    end
    -- An empty long-distance result has no visible route to audit. Do not
    -- expose reachability of intervening fog or private blocking factors.
    if count==0 then return status(distance==1 and "no_path" or "unknown") end
    if plots[1]~=start_id then return nil end
    if count==1 then return status(distance==1 and "no_path" or "unknown") end
    if plots[count]~=target_id then return status("unknown") end
    if count<distance+1 then return nil end
    local seen={{}}
    for index=1,count do
        if seen[plots[index]] then return nil end
        seen[plots[index]]=true
    end
    -- All path IDs have passed visibility. Only the first step's native
    -- coordinates are needed, never terrain/units/resources or hidden plots.
    local first=Map.GetPlotByIndex(plots[2])
    if not first or type(first.GetX)~="function" or type(first.GetY)~="function" then return nil end
    local nx,ny=first:GetX(),first:GetY()
    if not integer(nx,0,width-1) or not integer(ny,0,height-1) then return nil end
    if Map.GetPlotDistance(x,y,nx,ny)~=1 then return status("unknown") end
    if count==2 and (nx~={a['x']} or ny~={a['y']}) then return nil end
    local items=status(distance>1 and "route" or (count==2 and "direct" or "detour"))
    scalar(items,"first_step_x",nx,"原版当前路线的首个移动格坐标；不表示安全。")
    scalar(items,"first_step_y",ny,"原版当前路线的首个移动格坐标；不表示安全。")
    -- Optional arrival estimate: stock tests nTurnCount>1 for later turns.
    -- Missing/invalid estimates do not invalidate otherwise known geometry.
    local turns=path.turns
    if dense(turns,4096)==count then
        local valid=true
        local previous=-1
        for index=1,count do
            if not integer(turns[index],0,1000000) or turns[index]<previous then valid=false; break end
            previous=turns[index]
        end
        if valid and turns[count]>=1 then
            scalar(items,"arrival_turn",turns[count],"原版路径终点回合编号：1 为本回合；是预览估计，不保证到达。")
        end
    end
    return items
end
local ok,items=pcall(collect)
if not ok or type(items)~="table" then return end
out.supported=true
for _,item in ipairs(items) do add_item(item) end
'''


def queue_move(a: dict) -> str:
    """Issue the stock long-range goal once; never inspect its route/legality.

    WorldInput.lua:791-808 excludes IgnoreMoves, then Civ6Common.lua:102-163
    passes destination coordinates to MOVE_TO without an adjacency limit or
    target CanStartOperation(MOVE_TO) check. Keep the adapter's no-ATTACK policy
    and require a revealed goal, a stricter boundary than the stock click.
    """
    return own_unit(a["unit_id"]) + f'''
local function integer(value,low,high)
    return type(value)=="number" and value==value and value%1==0 and value>=low and value<=high
end
if type(Game.IsAllowTacticalCommands)~="function" or Game.IsAllowTacticalCommands(me)~=true
    or not UI or type(UI.IsGameCoreBusy)~="function" or UI.IsGameCoreBusy()~=false
    or not UnitManager or type(UnitManager.RequestOperation)~="function"
    or type(unit.GetMovesRemaining)~="function" or type(unit.GetUnitType)~="function"
    or type(unit.GetX)~="function" or type(unit.GetY)~="function" then return end
local moves=unit:GetMovesRemaining()
if type(moves)~="number" or moves~=moves or moves<=0 or moves==math.huge then return end
local unit_type=unit:GetUnitType()
if not integer(unit_type,0,2147483647) or not GameInfo or not GameInfo.Units then return end
local row=GameInfo.Units[unit_type]
if not row or (row.Domain~="DOMAIN_LAND" and row.Domain~="DOMAIN_SEA")
    or (row.IgnoreMoves~=nil and row.IgnoreMoves~=false and row.IgnoreMoves~=0) then return end
if not Map or type(Map.GetGridSize)~="function" or not vis or type(vis.IsRevealed)~="function" then return end
local width,height=Map.GetGridSize()
if not integer(width,1,4096) or not integer(height,1,4096)
    or {a['x']}>=width or {a['y']}>=height then return end
local ux,uy=unit:GetX(),unit:GetY()
if not integer(ux,0,width-1) or not integer(uy,0,height-1)
    or (ux=={a['x']} and uy=={a['y']}) then return end
-- This is a public exploration flag, not a current terrain/occupancy probe.
-- Do not construct the target plot or call CanStartOperation/pathfinding.
if vis:IsRevealed({a['x']},{a['y']})~=true then return end
if not UnitOperationTypes or type(UnitOperationTypes.MOVE_TO)~="number"
    or UnitOperationTypes.PARAM_X==nil or UnitOperationTypes.PARAM_Y==nil
    or UnitOperationTypes.PARAM_MODIFIERS==nil or not UnitOperationMoveModifiers
    or UnitOperationMoveModifiers.NONE~=0
    or not integer(UnitOperationMoveModifiers.MOVE_IGNORE_UNEXPLORED_DESTINATION,1,2147483647) then return end
local params={{[UnitOperationTypes.PARAM_X]={a['x']},[UnitOperationTypes.PARAM_Y]={a['y']},
    [UnitOperationTypes.PARAM_MODIFIERS]=UnitOperationMoveModifiers.NONE
        + UnitOperationMoveModifiers.MOVE_IGNORE_UNEXPLORED_DESTINATION}}
-- The shared attempt wrapper hides native success/failure/error values.
-- No automatic cancel, retry, attack, alternative action or path output.
attempt(UnitManager.RequestOperation,unit,UnitOperationTypes.MOVE_TO,params)
'''


ACTIONS = {
    "queue_move": ActionSpec({"unit_id": "id", "x": "coord", "y": "coord"}, queue_move,
        "Queue one normal MOVE_TO goal for an owned land/naval unit with movement remaining. "
        "The destination must already be revealed; current visibility and adjacency are not required. "
        "No attack flag, hidden target/path inspection, reachability result or automatic retry. "
        "Submitted does not mean queued or arrived; inspect own queued_destination and position afterward."),
}
QUERIES = {
    "unit_move_preview": QuerySpec({"unit_id": "id", "x": "coord", "y": "coord"}, unit_move_preview,
        "Read the stock MOVE_TO preview for an owned unit and a currently visible target. "
        "Reports direct/detour for adjacent goals, route for distant goals, or no_path/unknown. "
        "An empty distant path stays unknown; only fully visible, understood paths may include "
        "first_step_x/y and native arrival_turn (1=current turn). No raw path, hidden geometry, "
        "terrain, units, resources, action or safety guarantee. Does not change orders or movement."),
}
