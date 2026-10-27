"""Local player's travelling and stationed spies from stock EspionageOverview.

Base/Assets/UI/PartialScreens/EspionageOverview.lua:128-146,734-757 reads
GetNthOffMapSpy(localPlayer, index), excludes ReturnTurn == -1, and shows
name, rank, remaining travel turns and destination city name. The GS overview
inherits these functions. AddOperative:630-714 supplies current city, mission,
district, remaining turns and effects for own map spies. No other player's
unit, off-map or captive list is read.
"""

from .base import QuerySpec, lua
from .spy_menus import SPY_MISSION_DETAILS


def _stationed():
    from .units import SPY_MISSIONS
    return "\nlocal mission_names=" + lua(["UNITOPERATION_" + name for name in SPY_MISSIONS]) + r'''
local allowed_missions={}
for _,name in ipairs(mission_names) do allowed_missions[name]=true end
local units_ok,units=read(player,'GetUnits')
if units_ok and units and type(units.Members)=='function' and GameInfo and GameInfo.Units then
    local before=#pending
    local complete=pcall(function()
        local examined,number,seen=0,0,{}
        for _,unit in units:Members() do
            examined=examined+1;if examined>4096 then error('unavailable') end
            local owner_ok,owner=read(unit,'GetOwner')
            if not owner_ok then error('unavailable') end
            if owner==me then
                local type_ok,kind=read(unit,'GetUnitType')
                if not type_ok or not integer(kind,0,2147483647) then error('unavailable') end
                local definition=GameInfo.Units[kind]
                if not definition then error('unavailable') end
                if definition and definition.Spy==true then
                    local id_ok,id=read(unit,'GetID')
                    local x_ok,x=read(unit,'GetX')
                    local y_ok,y=read(unit,'GetY')
                    if not id_ok or not integer(id,0,2147483647) then error('unavailable') end
                    if not x_ok or not y_ok or not integer(x,-1,4095) or not integer(y,-1,4095) then error('unavailable') end
                    if x>=0 and y>=0 and not seen[id] then
                        seen[id]=true;number=number+1;if number>128 then error('unavailable') end
                        id=math.floor(id)
                        local prefix='stationed:'..id
                        local name_ok,name=read(unit,'GetName')
                        add(prefix,name_ok and label(name) or nil,id,'本方地图上的间谍；value 为自有单位 ID，状态只读。')
                        local experience_ok,experience=read(unit,'GetExperience')
                        local level_ok,level=read(experience_ok and experience or nil,'GetLevel')
                        if level_ok and integer(level,0,2147483647) then
                            local rank=math.floor((level==2 or level==3 or level==4) and level or 1)
                            add(prefix..':rank',label('LOC_ESPIONAGE_LEVEL_'..rank..'_NAME'),rank)
                        end
                        local plot,city
                        if Map and type(Map.GetPlot)=='function' then
                            local plot_ok,value=pcall(Map.GetPlot,x,y)
                            if plot_ok then plot=value end
                        end
                        if plot and Cities and type(Cities.GetPlotPurchaseCity)=='function' then
                            local city_ok,value=pcall(Cities.GetPlotPurchaseCity,plot)
                            if city_ok then city=value end
                        end
                        if city then
                            local city_name_ok,city_name=read(city,'GetName')
                            city_name=city_name_ok and label(city_name) or nil
                            if city_name then add(prefix..':city','当前驻城',city_name) end
                        end
                        local operation_ok,operation=read(unit,'GetSpyOperation')
                        if operation_ok and operation==-1 then
                            add(prefix..':mission','当前间谍任务','NONE','原版概览显示等待指派。')
                        elseif operation_ok and integer(operation,0,2147483647) and GameInfo.UnitOperations then
                            local row=GameInfo.UnitOperations[operation]
                            if row and allowed_missions[row.OperationType] then
                                add(prefix..':mission',label(row.Description),row.OperationType)
                                local end_ok,ends=read(unit,'GetSpyOperationEndTurn')
                                if end_ok and integer(ends,0,2147483647) then
                                    add(prefix..':turns_remaining','任务剩余回合',math.floor(math.max(0,ends-turn)))
                                end
                                if UnitManager and type(UnitManager.GetTimeToComplete)=='function' then
                                    local total_ok,total=pcall(UnitManager.GetTimeToComplete,operation,unit)
                                    if total_ok and integer(total,0,2147483647) then
                                        add(prefix..':total_turns','当前任务总工期',math.floor(total))
                                    end
                                end
                                -- AddOperative shows the current spy plot's
                                -- district, not future targets or neighboring plots.
                                local district_ok,district_type=read(plot,'GetDistrictType')
                                local district=district_ok and integer(district_type,0,2147483647)
                                    and GameInfo.Districts and GameInfo.Districts[district_type]
                                local district_name=district and label(district.Name)
                                if district and type(district.DistrictType)=='string'
                                    and district.DistrictType:match('^DISTRICT_[A-Z0-9_]+$') then
                                    add(prefix..':target_district',district_name,district.DistrictType)
                                end
                                local details
                                if city then
                                    if row.OperationType=='UNITOPERATION_SPY_COUNTERSPY' then
                                        if district_name and Locale and type(Locale.Lookup)=='function' then
                                            local detail_ok,value=pcall(Locale.Lookup,'LOC_ESPIONAGECHOOSER_COUNTERSPY',district_name)
                                            if detail_ok and type(value)=='string' and #value<=6000
                                                and not value:find('%z') then details=value end
                                        end
                                    else details=spy_formatted_details(unit,city,row) end
                                end
                                if details and details~='' then add(prefix..':effect','当前任务效果',nil,details) end
                            end
                        end
                    end
                end
            end
        end
        add('stationed_count','本方地图上的间谍数量',number)
    end)
    -- Optional map-state failure must not erase a valid off-map snapshot or
    -- leave a partial count that masquerades as a complete own-spy list.
    if not complete then while #pending>before do table.remove(pending) end end
end
'''


def spy_overview(_):
    return SPY_MISSION_DETAILS + r'''
out.supported=false
local function read(object,key,...)
    if type(object)~='table' and type(object)~='userdata' then return false,nil end
    local ok,method=pcall(function() return object[key] end)
    if not ok or type(method)~='function' then return false,nil end
    return pcall(method,object,...)
end
local function integer(value,minimum,maximum)
    return type(value)=='number' and value%1==0 and value>=minimum and value<=maximum
end
local function text(value)
    return type(value)=='string' and #value>0 and #value<=1024
        and not value:find('%z') and value or nil
end
local function label(value)
    if not text(value) then return nil end
    if Locale and type(Locale.Lookup)=='function' then
        local ok,result=pcall(Locale.Lookup,value)
        if ok then return text(result) end
        return nil
    end
    return value
end
local ok,diplomacy=read(player,'GetDiplomacy')
if not ok or not diplomacy then return end
local count_ok,count=read(diplomacy,'GetNumSpiesOffMap')
if not count_ok or not integer(count,0,128)
    or type(diplomacy.GetNthOffMapSpy)~='function' then return end
local pending={}
local function add(id,name,value,description)
    pending[#pending+1]={id=id,name=name,value=value,description=description,scope='self',owner_id=me}
end
local travelling=0
for index=0,count-1 do
    -- The owner argument is always the local player; it is never caller input.
    local entry_ok,entry=read(diplomacy,'GetNthOffMapSpy',me,index)
    if not entry_ok then return end
    if entry~=nil then
        if type(entry)~='table' then return end
        -- Normal API ownership follows from the receiver and explicit player
        -- argument. Reject a contradictory owner before any identity/position.
        if entry.OwningPlayer~=nil and entry.OwningPlayer~=me then return end
        if not integer(entry.ReturnTurn,-1,2147483647) then return end
        if entry.ReturnTurn~=-1 then
            local name=label(entry.Name)
            if not name or not integer(entry.Level,0,2147483647) then return end
            travelling=travelling+1
            local prefix='travelling:'..index
            add(prefix,name,'TRAVELLING','本方离图旅行中的间谍；序号仅用于本次查询，不是可操作的 unit_id。')
            local level=entry.Level
            local rank=math.floor((level==2 or level==3 or level==4) and level or 1)
            add(prefix..':rank',label('LOC_ESPIONAGE_LEVEL_'..rank..'_NAME'),rank)
            add(prefix..':turns_remaining','旅行剩余回合',math.floor(math.max(0,entry.ReturnTurn-turn)))
            -- Only the destination name shown in AddOffMapOperative is read.
            -- Coordinates bind the own trip to its city; no plot state, city
            -- identity, foreign collection, yields or nearby objects are read.
            local x,y=entry.XLocation,entry.YLocation
            if integer(x,0,4095) and integer(y,0,4095)
                and Map and type(Map.GetPlot)=='function'
                and Cities and type(Cities.GetPlotPurchaseCity)=='function' then
                local plot_ok,plot=pcall(Map.GetPlot,x,y)
                if plot_ok and plot~=nil then
                    local city_ok,city=pcall(Cities.GetPlotPurchaseCity,plot)
                    if city_ok and city~=nil then
                        local name_ok,city_name=read(city,'GetName')
                        local destination=name_ok and label(city_name) or nil
                        if destination then add(prefix..':destination','旅行目的地',destination) end
                    end
                end
            end
        end
    end
end
add('travelling_count','本方旅行中的间谍数量',travelling)
local capacity_ok,capacity=read(diplomacy,'GetSpyCapacity')
if capacity_ok and integer(capacity,0,2147483647) then
    add('capacity','间谍容量',math.floor(capacity))
end
''' + _stationed() + r'''
for _,item in ipairs(pending) do add_item(item) end
out.supported=true
'''


ACTIONS = {}
QUERIES = {
    "spy_overview": QuerySpec({}, spy_overview,
        "Own travelling and stationed spies: name, rank, remaining turns, destination/current city, "
        "current mission district/effect when available, and own spy capacity. Travelling snapshot "
        "indices are not unit IDs; stationed rows include the own unit ID. Missing optional fields are unknown. "
        "No captured spies or foreign off-map lists."),
}
