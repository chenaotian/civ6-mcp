"""The stock TradeRouteChooser's menu exception to ordinary map visibility.

The caller prepends units._unit(a), providing an owned `unit` and the shared
helpers. No city name or yield is read until CheckTradeRoute and nonempty-path
membership both hold. The menu exception never calls ordinary map readers.
"""
from __future__ import annotations

from .trade_yields import TRADE_YIELD_HELPERS


TRADE_HELPERS = TRADE_YIELD_HELPERS + r'''
local function trade_unavailable()
    out.supported=false
    return nil
end
local function trade_integer(value,maximum)
    return type(value)=="number" and value>=0 and value<=maximum and value%1==0
end
local function trade_number(value)
    return type(value)=="number" and value==value and value~=math.huge and value~=-math.huge
end
local function trade_prepare(unit)
    if not unit or type(unit.GetOwner)~="function" or unit:GetOwner()~=me then return nil end
    for _,key in ipairs({"GetID","GetX","GetY","GetUnitType","GetMovesRemaining"}) do
        if type(unit[key])~="function" then return trade_unavailable() end
    end
    if not GameInfo or not GameInfo.Units or not UnitManager
        or type(UnitManager.GetActivityType)~="function"
        or type(UnitManager.CanStartOperation)~="function" or not ActivityTypes
        or ActivityTypes.ACTIVITY_AWAKE==nil or not UnitOperationTypes then return trade_unavailable() end
    local row=GameInfo.Units[unit:GetUnitType()]
    if not row or row.MakeTradeRoute~=true then return nil end
    if UnitManager.GetActivityType(unit)~=ActivityTypes.ACTIVITY_AWAKE then return nil end
    local moves=unit:GetMovesRemaining()
    if type(moves)~="number" or moves<=0 then return nil end
    local hash=operation("MAKE_TRADE_ROUTE")
    if not hash or not Cities or type(Cities.GetCityInPlot)~="function"
        or type(Game.GetTradeManager)~="function" or type(Game.GetPlayers)~="function"
        or type(player.GetCities)~="function" then return trade_unavailable() end
    for _,key in ipairs({"PARAM_X0","PARAM_Y0","PARAM_X1","PARAM_Y1"}) do
        if UnitOperationTypes[key]==nil then return trade_unavailable() end
    end
    local x,y,id=unit:GetX(),unit:GetY(),unit:GetID()
    if not trade_integer(x,4095) or not trade_integer(y,4095)
        or not trade_integer(id,2147483647) then return trade_unavailable() end
    x,y,id=math.floor(x),math.floor(y),math.floor(id)
    -- TradeRouteChooser:84: origin is the city ON the trader's tile, not the
    -- city owning an arbitrary worked tile (GetPlotPurchaseCity).
    local origin=Cities.GetCityInPlot(x,y)
    if not origin then return nil end
    if type(origin.GetOwner)~="function" then return trade_unavailable() end
    if origin:GetOwner()~=me then return nil end
    if type(origin.GetID)~="function" then return trade_unavailable() end
    local origin_id=origin:GetID()
    if not trade_integer(origin_id,2147483647) then return trade_unavailable() end
    origin_id=math.floor(origin_id)
    local manager=Game.GetTradeManager()
    if not manager or type(manager.GetTradeRoutePath)~="function" then return trade_unavailable() end
    return {unit=unit,unit_id=id,x=x,y=y,origin_id=origin_id,manager=manager,hash=hash}
end
local function trade_collect(state)
    -- TradeRouteChooser:456-489. No IsVisible/IsRevealed/HasMet substitute:
    -- only these native menu checks establish the bounded menu disclosure.
    local players=Game.GetPlayers()
    if type(players)~="table" then return trade_unavailable() end
    local ordered={player}
    for index,candidate in ipairs(players) do
        if index>64 then return trade_unavailable() end
        if not candidate or type(candidate.GetID)~="function" then return trade_unavailable() end
        local candidate_id=candidate:GetID()
        if not trade_integer(candidate_id,63) then return trade_unavailable() end
        if candidate_id~=me then table.insert(ordered,candidate) end
    end
    if #ordered>64 then return trade_unavailable() end
    local offered={}
    local seen={}
    local city_count=0
    for _,candidate in ipairs(ordered) do
        if type(candidate.GetCities)~="function" then return trade_unavailable() end
        local cities=candidate:GetCities()
        if not cities or type(cities.Members)~="function" then return trade_unavailable() end
        for _,city in cities:Members() do
            city_count=city_count+1
            if city_count>4096 then return trade_unavailable() end
            if not city then return trade_unavailable() end
            for _,key in ipairs({"GetOwner","GetID","GetX","GetY"}) do
                if type(city[key])~="function" then return trade_unavailable() end
            end
            local owner,id,x,y=city:GetOwner(),city:GetID(),city:GetX(),city:GetY()
            if not trade_integer(owner,63) or not trade_integer(id,2147483647)
                or not trade_integer(x,4095) or not trade_integer(y,4095) then return trade_unavailable() end
            owner,id,x,y=math.floor(owner),math.floor(id),math.floor(x),math.floor(y)
            local params={[UnitOperationTypes.PARAM_X0]=x,[UnitOperationTypes.PARAM_Y0]=y,
                [UnitOperationTypes.PARAM_X1]=state.x,[UnitOperationTypes.PARAM_Y1]=state.y}
            if can_operation(state.unit,state.hash,params) then
                -- Chooser:472 explicitly says CanStartOperation does NOT
                -- guarantee a route exists. Never publish before this gate.
                local path=state.manager:GetTradeRoutePath(me,state.origin_id,owner,id)
                if type(path)=="table" and next(path)~=nil then
                    local key=tostring(owner)..":"..tostring(id)
                    if not seen[key] then
                        seen[key]=true
                        table.insert(offered,{city=city,owner=owner,id=id,x=x,y=y,params=params})
                    end
                end
            end
        end
    end
    return offered
end
local function trade_find(offered,x,y)
    for _,entry in ipairs(offered) do
        if entry.x==x and entry.y==y then return entry end
    end
    return nil
end
local function trade_item(state,id,name,value,action,description)
    local item={id=id,scope="menu",menu_owner_id=math.floor(me),menu_source="trade",
        menu_offered=true,menu_unit_id=state.unit_id}
    if name~=nil then item.name=name end
    if value~=nil then item.value=value end
    if action~=nil then item.action=action end
    if description~=nil then item.description=description end
    return item
end
local function trade_yields(state,entry,destination)
    local values=menu_trade_yields(state.manager,me,state.origin_id,entry.owner,entry.id,destination,player)
    if not values then return trade_unavailable() end
    return values
end
local function trade_records(state,entry,prefix)
    -- Read names/benefits only for the already-qualified menu entry. Do not
    -- expose its city population, districts, raw bonuses, route or map state.
    if type(entry.city.GetName)~="function" or not Locale or type(Locale.Lookup)~="function" then return trade_unavailable() end
    local origin=trade_yields(state,entry,false)
    if not origin then return nil end
    local destination=trade_yields(state,entry,true)
    if not destination then return nil end
    local action={type="trade_route",unit_id=state.unit_id,x=entry.x,y=entry.y}
    local result={trade_item(state,prefix,Locale.Lookup(entry.city:GetName()),nil,action)}
    local yield_prefix=prefix=="trade_route" and "" or prefix..":"
    for _,value in ipairs(origin) do
        table.insert(result,trade_item(state,yield_prefix.."origin:"..value.name,nil,value.value))
    end
    for _,value in ipairs(destination) do
        table.insert(result,trade_item(state,yield_prefix.."destination:"..value.name,nil,value.value))
    end
    return result
end
'''


def trade_body(a: dict) -> str:
    return TRADE_HELPERS + f'''
if not tactical() then return end
local state=trade_prepare(unit)
if not state then return end
local offered=trade_collect(state)
if not offered then return end
local entry=trade_find(offered,{a['x']},{a['y']})
if not entry then return end
if type(UnitManager.RequestOperation)~="function" then trade_unavailable(); return end
-- Recheck immediately before submitting the ordinary UI request. The whole
-- menu (including a nonempty path) was rebuilt in this same action call.
if not can_operation(unit,state.hash,entry.params) then return end
attempt(UnitManager.RequestOperation,unit,state.hash,entry.params)
'''


def trade_options(a: dict) -> str:
    return TRADE_HELPERS + f'''
local state=trade_prepare(unit)
if not state then return end
local offered=trade_collect(state)
if not offered then return end
local entry=trade_find(offered,{a['x']},{a['y']})
if not entry then return end
local records=trade_records(state,entry,"trade_route")
if not records then return end
for _,record in ipairs(records) do add_item(record) end
'''


def trade_destinations(a: dict) -> str:
    return TRADE_HELPERS + f'''
local state=trade_prepare(unit)
if not state then return end
local offered=trade_collect(state)
if not offered then return end
-- Offset is within the qualified menu, never the raw foreign-city scan.
local stop=math.min({a['offset']}+64,#offered)
local pending={{}}
for index={a['offset']}+1,stop do
    local entry=offered[index]
    local records=trade_records(state,entry,"trade:"..entry.x..":"..entry.y)
    if not records then return end
    for _,record in ipairs(records) do table.insert(pending,record) end
end
table.insert(pending,trade_item(state,"next_offset",nil,stop<#offered and stop or -1))
-- Buffer the complete page so a missing capability cannot publish a partial
-- set of actions without its required displayed benefit totals.
for _,record in ipairs(pending) do add_item(record) end
'''
