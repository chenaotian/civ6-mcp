"""Current own outgoing routes, using the stock My Routes inventory.

TradeOverview.lua:51-78 supplies capacity/count and the own-city route lists;
TradeSupport.lua:2-27 associates TraderUnitID and classifies idle own traders.
UnitPanel.lua:2172-2185 displays route endpoint names. No route duration getter
is used by this stock UI; TradeOverview's displayed distance is not remaining
turns (:435-437), and its separate duration labels are hidden in the XML.
"""
from .base import QuerySpec
from .trade_yields import TRADE_YIELD_HELPERS


def own_trade_routes(_a: dict) -> str:
    return TRADE_YIELD_HELPERS + r'''
out.supported=false
local function integer(v,low,high)
    return type(v)=="number" and v==v and v%1==0 and v>=low and v<=high
end
local function read(object,key,...)
    if type(object)~="table" and type(object)~="userdata" then return nil end
    local ok,fn=pcall(function() return object[key] end)
    if not ok or type(fn)~="function" then return nil end
    local success,value=pcall(fn,object,...)
    if success then return value end
end
local function city_name(city)
    local name=read(city,"GetName")
    if type(name)~="string" or not Locale or type(Locale.Lookup)~="function" then return nil end
    local ok,value=pcall(Locale.Lookup,name)
    if ok and type(value)=="string" and #value>0 and #value<=1024 and not value:find("%z") then return value end
end
local function dense(values)
    if type(values)~="table" then return nil end
    local n,seen=0,{}
    for key in pairs(values) do
        if not integer(key,1,1024) then return nil end
        seen[key]=true;n=n+1
    end
    for i=1,n do if not seen[i] then return nil end end
    return n
end
local records={}
local function append(record)
    if #records>=2048 then error("unavailable") end
    records[#records+1]=record
end
local function self_value(id,value)
    append({id=id,value=value,scope="self",owner_id=me})
end
local function route_value(route,field,value)
    if value==nil then return end
    append({id="route:"..route.trader..":"..field,value=value,scope="menu",
        menu_source="trade_overview",menu_owner_id=me,menu_offered=true,
        menu_unit_id=route.trader,menu_origin_owner_id=me,menu_origin_city_id=route.origin_id,
        menu_destination_owner_id=route.destination_owner,
        menu_yields_calculated=route.yields_calculated==true,
        menu_destination_known=route.destination_known==true,
        menu_destination_revealed=route.destination_revealed==true})
end
local function coordinates(city)
    local x,y=read(city,"GetX"),read(city,"GetY")
    if integer(x,0,4095) and integer(y,0,4095) then return math.floor(x),math.floor(y) end
end
local function endpoint(route,cities)
    local owner=route.destination_owner
    if owner~=me then
        local diplomacy=read(player,"GetDiplomacy")
        if read(diplomacy,"HasMet",owner)~=true then return end
    end
    route.destination_known=true
    route_value(route,"destination_owner_id",owner)
    -- The only foreign lookup is this exact endpoint in an existing own
    -- outgoing route. No foreign city iteration or arbitrary caller target.
    local collection=owner==me and cities or read(Players[owner],"GetCities")
    local destination=read(collection,"FindID",route.destination_id)
    if not destination or read(destination,"GetOwner")~=owner
        or read(destination,"GetID")~=route.destination_id then return end
    route.destination_confirmed=true
    route_value(route,"destination_name",city_name(destination))
    local x,y=coordinates(destination)
    if x==nil or not vis or type(vis.IsRevealed)~="function" then return end
    local ok,revealed=pcall(vis.IsRevealed,vis,x,y)
    if ok and revealed==true then
        route.destination_revealed=true
        route_value(route,"destination_x",x);route_value(route,"destination_y",y)
    end
end
local function benefits(route)
    -- Only a confirmed endpoint in the complete own My Routes inventory.
    -- A currently fogged endpoint is still a normal trade-menu entry; no
    -- plot or raw path is queried to compute the displayed benefit totals.
    if route.destination_known~=true or route.destination_confirmed~=true then return end
    if not Game or type(Game.GetTradeManager)~="function" then return end
    local manager=Game.GetTradeManager()
    for _,side in ipairs({"origin","destination"}) do
        local ok,values=pcall(menu_trade_yields,manager,me,route.origin_id,
            route.destination_owner,route.destination_id,side=="destination",player)
        if ok and type(values)=="table" then
            local valid=true
            for _,value in ipairs(values) do
                if not menu_trade_number(value.value) or math.abs(value.value)>1000000 then valid=false;break end
            end
            if valid then
                route.yields_calculated=true
                -- TradeOverview:359 / SupportFunctions:473: Round(total,1).
                for _,value in ipairs(values) do
                    route_value(route,side.."_yield:"..value.name,math.floor(value.value*10+0.5)/10)
                end
            end
        end
    end
end
local function collect()
    if not UI or type(UI.IsGameCoreBusy)~="function" or UI.IsGameCoreBusy()~=false then return end
    local trade=read(player,"GetTrade")
    local active,capacity=read(trade,"GetNumOutgoingRoutes"),read(trade,"GetOutgoingRouteCapacity")
    if not integer(active,0,4096) or not integer(capacity,0,4096) then return end
    local cities,units=read(player,"GetCities"),read(player,"GetUnits")
    if not cities or type(cities.Members)~="function" or not units or type(units.Members)~="function"
        or not GameInfo or not GameInfo.Units then return end
    local routes,by_trader,city_ids={},{},{}
    local checked=0
    for _,city in cities:Members() do
        checked=checked+1;if checked>4096 then return end
        if city:GetOwner()==me then
            local city_id=read(city,"GetID")
            if not integer(city_id,0,2147483647) or city_ids[city_id] then return end
            city_ids[city_id]=true
            local city_trade=read(city,"GetTrade")
            local rows=read(city_trade,"GetOutgoingRoutes")
            local count=dense(rows)
            if count==nil then return end
            for i=1,count do
                local row=rows[i]
                if type(row)~="table" or row.OriginCityPlayer~=me or row.OriginCityID~=city_id then return end
                local trader,owner,id=row.TraderUnitID,row.DestinationCityPlayer,row.DestinationCityID
                if not integer(trader,0,2147483647) or by_trader[trader]
                    or not integer(owner,0,63) or not integer(id,0,2147483647) then return end
                if #routes>=1024 then return end
                local route={trader=math.floor(trader),origin_id=math.floor(city_id),origin=city,
                    destination_owner=math.floor(owner),destination_id=math.floor(id)}
                by_trader[trader]=route;routes[#routes+1]=route
            end
        end
    end
    -- Never label a trader idle from an incomplete list or a transient count.
    if #routes~=active then return end
    local traders,unit_ids={},{}
    checked=0
    for _,unit in units:Members() do
        checked=checked+1;if checked>4096 then return end
        if unit:GetOwner()==me then
            local id,kind=read(unit,"GetID"),read(unit,"GetUnitType")
            if not integer(id,0,2147483647) or unit_ids[id] or not integer(kind,0,2147483647) then return end
            unit_ids[id]=true
            local definition=GameInfo.Units[kind]
            if not definition then return end
            local can_trade=definition.MakeTradeRoute
            if can_trade==true or can_trade==1 then traders[#traders+1]=math.floor(id)
            elseif can_trade~=nil and can_trade~=false and can_trade~=0 then return end
        end
    end
    table.sort(traders)
    table.sort(routes,function(a,b) return a.trader<b.trader end)
    self_value("active_count",math.floor(active));self_value("capacity",math.floor(capacity))
    local idle=0
    for _,id in ipairs(traders) do
        local status=by_trader[id] and "active" or "idle"
        if status=="idle" then idle=idle+1 end
        self_value("trader:"..id..":status",status)
    end
    self_value("idle_trader_count",idle)
    for _,route in ipairs(routes) do
        route_value(route,"trader_unit_id",route.trader)
        route_value(route,"origin_city_id",route.origin_id)
        route_value(route,"origin_name",city_name(route.origin))
        local x,y=coordinates(route.origin)
        if x~=nil then route_value(route,"origin_x",x);route_value(route,"origin_y",y) end
        -- Endpoint metadata is optional. Loss/destruction/capture does not
        -- erase an otherwise confirmed own route or invent an ending reason.
        pcall(endpoint,route,cities)
        -- Optional display data must not erase a confirmed route if a yield
        -- API is absent or a destination has disappeared during UI refresh.
        pcall(benefits,route)
    end
    if UI.IsGameCoreBusy()~=false or read(trade,"GetNumOutgoingRoutes")~=active
        or read(trade,"GetOutgoingRouteCapacity")~=capacity then return end
    return true
end
local ok,complete=pcall(collect)
if not ok or complete~=true then return end
out.supported=true
for _,record in ipairs(records) do add_item(record) end
'''


ACTIONS = {}
QUERIES = {
    "own_trade_routes": QuerySpec({}, own_trade_routes,
        "Current own outgoing trade routes, active count/capacity, linked TraderUnitID and idle own traders. "
        "Route endpoints are the stock My Routes menu entries; foreign owner/name require meeting, "
        "and destination coordinates require revelation. Optional origin/destination yield totals use "
        "the stock route benefit calculation. Idle means no route in a complete current list, "
        "not a cancellation/completion reason. No remaining turns, raw paths, foreign city details or actions."),
}
