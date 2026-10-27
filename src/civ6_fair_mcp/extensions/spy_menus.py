"""Spy chooser information, including its explicitly offered fogged targets.

The Base chooser (421-428) requires revealed city centers. Expansion1/2 replace
only its player filter (27-36). Mission targets come from that city's chooser
check (190-240), never an arbitrary coordinate query. Destination previews are
not executable missions (278-283, 358-365). Ordinary offensive acceptance is a
no-parameter request (EspionagePopup 472-477); counterspy supplies its district.
"""
from __future__ import annotations

from .base import lua


SPY_MISSION_DETAILS = r'''
-- EspionageSupport.lua:2-23. Call only for an operation/city already authorized
-- by the chooser or by the own-spy overview. Optional text failure omits text.
local function spy_formatted_details(u,city,row)
    if not UnitManager or type(UnitManager.GetOperationDetailText)~='function'
        or not Map or type(Map.GetPlot)~='function' or not city or not row
        or type(row.Index)~='number' or type(row.OperationType)~='string'
        or not Locale or type(Locale.Lookup)~='function' then return nil end
    local ok,result=pcall(function()
        local details=UnitManager.GetOperationDetailText(row.Index,u,Map.GetPlot(city:GetX(),city:GetY()))
        if type(details)~='string' then return nil end
        local mission=row.OperationType
        local key='LOC_SPYMISSIONDETAILS_'..mission
        if mission=='UNITOPERATION_SPY_SIPHON_FUNDS' then
            local name=city:GetName()
            if type(Locale.ToUpper)=='function' then name=Locale.ToUpper(name) end
            return Locale.Lookup(key,name,details)
        elseif mission=='UNITOPERATION_SPY_GREAT_WORK_HEIST' or mission=='UNITOPERATION_SPY_FOMENT_UNREST'
            or mission=='UNITOPERATION_SPY_FABRICATE_SCANDAL' or mission=='UNITOPERATION_SPY_NEUTRALIZE_GOVERNOR' then
            return Locale.Lookup(key,details)
        elseif details~='' then return details
        else return Locale.Lookup(key) end
    end)
    if ok and type(result)=='string' and #result<=6000 and not result:find('%z') then return result end
end
'''


SPY_HELPERS = SPY_MISSION_DETAILS + r'''
local spy_actor_id=nil
local function spy_missing()
    out.supported=false
    return nil
end
local function spy_coord(x,y)
    return type(x)=="number" and type(y)=="number" and x%1==0 and y%1==0
        and x>=0 and y>=0 and x<4096 and y<4096
end
local function spy_integer(value,minimum,maximum)
    if type(value)=="number" and value%1==0 and value>=minimum and value<=maximum then
        return math.floor(value)
    end
end
local function spy_setup(u)
    if not GameConfiguration or type(GameConfiguration.GetValue)~="function"
        or type(Game.GetPlayers)~="function" or not GameInfo.DiplomaticStates
        or not GameInfo.UnitOperations or not GameInfo.Units or not GameInfo.Districts or not UnitManager
        or type(UnitManager.CanStartOperation)~="function" or not UnitOperationTypes
        or UnitOperationTypes.PARAM_X==nil or UnitOperationTypes.PARAM_Y==nil
        or not UnitOperationResults or UnitOperationResults.PLOTS==nil
        or not Map or type(Map.GetPlot)~="function" or type(Map.GetPlotByIndex)~="function"
        or type(Map.GetGridSize)~="function" or not Cities
        or type(Cities.GetPlotPurchaseCity)~="function" then return spy_missing() end
    local rules=GameConfiguration.GetValue("RULESET")
    if rules~="RULESET_STANDARD" and rules~="RULESET_EXPANSION_1"
        and rules~="RULESET_EXPANSION_2" then return spy_missing() end
    if type(u.GetID)~="function" or type(u.GetUnitType)~="function" or type(u.GetMovesRemaining)~="function"
        or type(u.GetX)~="function" or type(u.GetY)~="function" then return spy_missing() end
    spy_actor_id=spy_integer(u:GetID(),0,2147483647)
    if spy_actor_id==nil then return spy_missing() end
    local row=GameInfo.Units[u:GetUnitType()]
    if not row or row.Spy~=true then return nil end
    return rules
end
local function spy_mobile(u)
    local moves=u:GetMovesRemaining()
    return type(moves)=="number" and moves>0
end
local function spy_menu_item(u,item)
    item.scope="menu"; item.menu_owner_id=me; item.menu_source="spy"
    item.menu_offered=true; item.menu_unit_id=spy_actor_id
    add_item(item)
end
local function spy_cities(rules)
    if type(player.GetTeam)~="function" then return spy_missing() end
    local our_team=player:GetTeam()
    if type(our_team)~="number" then return spy_missing() end
    local players=Game.GetPlayers()
    if type(players)~="table" then return spy_missing() end
    local cities,seen={},{}
    local player_count,city_count=0,0
    for _,candidate in ipairs(players) do
        player_count=player_count+1
        if player_count>64 then return spy_missing() end
        if type(candidate.GetID)~="function" or type(candidate.GetTeam)~="function"
            or type(candidate.GetDiplomaticAI)~="function" then return spy_missing() end
        local owner=spy_integer(candidate:GetID(),0,63)
        if owner==nil then return spy_missing() end
        local ai=candidate:GetDiplomaticAI()
        if not ai or type(ai.GetDiplomaticStateIndex)~="function" then return spy_missing() end
        local state_id=ai:GetDiplomaticStateIndex(me)
        if type(state_id)~="number" then return spy_missing() end
        if state_id~=-1 then
            local state_row=GameInfo.DiplomaticStates[state_id]
            if not state_row or type(state_row.StateType)~="string" then return spy_missing() end
            local team=candidate:GetTeam()
            if type(team)~="number" then return spy_missing() end
            local eligible=state_row.StateType~="DIPLO_STATE_ALLIED"
                and (owner==me or team==-1 or our_team==-1 or team~=our_team)
            if eligible then
                if rules=="RULESET_STANDARD" then
                    if type(candidate.IsMajor)~="function" then return spy_missing() end
                    eligible=candidate:IsMajor()==true
                else
                    if type(candidate.IsFreeCities)~="function" then return spy_missing() end
                    eligible=candidate:IsFreeCities()==false
                end
            end
            if eligible then
                if type(candidate.GetCities)~="function" then return spy_missing() end
                local collection=candidate:GetCities()
                if not collection or type(collection.Members)~="function" then return spy_missing() end
                for _,city in collection:Members() do
                    city_count=city_count+1
                    if city_count>4096 then return spy_missing() end
                    if type(city.GetX)~="function" or type(city.GetY)~="function" then return spy_missing() end
                    local x,y=city:GetX(),city:GetY()
                    -- No other city field is read until the exact chooser
                    -- reveal test succeeds. Current visibility is irrelevant.
                    if spy_coord(x,y) and vis:IsRevealed(x,y)==true then
                        x,y=math.floor(x),math.floor(y)
                        if type(city.GetOwner)~="function" or type(city.GetID)~="function" then return spy_missing() end
                        if city:GetOwner()==owner then
                            local id=spy_integer(city:GetID(),0,2147483647)
                            if id==nil then return spy_missing() end
                            local key=tostring(owner)..":"..tostring(id)
                            if not seen[key] then
                                seen[key]=true
                                cities[#cities+1]={city=city,owner=owner,id=id,x=x,y=y}
                            end
                        end
                    end
                end
            end
        end
    end
    table.sort(cities,function(a,b)
        if a.y~=b.y then return a.y<b.y end
        if a.x~=b.x then return a.x<b.x end
        if a.owner~=b.owner then return a.owner<b.owner end
        return a.id<b.id
    end)
    return cities
end
local function spy_current(u,cities)
    local x,y=u:GetX(),u:GetY()
    if not spy_coord(x,y) then return nil end
    x,y=math.floor(x),math.floor(y)
    -- These are the owned actor's known coordinates, not caller coordinates.
    local plot=Map.GetPlot(x,y)
    if not plot then return nil end
    local current=Cities.GetPlotPurchaseCity(plot)
    if not current or type(current.GetOwner)~="function" or type(current.GetID)~="function" then return nil end
    local owner,id=current:GetOwner(),current:GetID()
    for _,entry in ipairs(cities) do
        if entry.owner==owner and entry.id==id then return entry end
    end
end
local function spy_travel_entry(u)
    if not spy_mobile(u) then return false end
    local hash=operation("SPY_TRAVEL_NEW_CITY")
    if not hash then spy_missing(); return false end
    -- UnitPanel 672-677: visibility test followed by current availability.
    local no_targets=OperationResultsTypes and OperationResultsTypes.NO_TARGETS or false
    return UnitManager.CanStartOperation(u,hash,nil,true)==true
        and UnitManager.CanStartOperation(u,hash,nil,false,no_targets)==true
end
local function spy_can_travel(u,entry)
    local hash=operation("SPY_TRAVEL_NEW_CITY")
    local params=xy_params(UnitOperationTypes,entry.x,entry.y)
    if not hash or not params then spy_missing(); return false end
    local plot=Map.GetPlot(entry.x,entry.y)
    return plot~=nil and UnitManager.CanStartOperation(u,hash,plot,params)==true
end
local function spy_same_city(a,b)
    return a~=nil and b~=nil and a.owner==b.owner and a.id==b.id
end
local function spy_mission_entry(u,entry,missions)
    if not spy_mobile(u) then return false end
    -- Selection opens this chooser automatically for a ready awake spy.
    if type(u.IsReadyToMove)=="function" and u:IsReadyToMove()==true
        and type(UnitManager.GetActivityType)=="function" and ActivityTypes
        and ActivityTypes.ACTIVITY_AWAKE~=nil
        and UnitManager.GetActivityType(u)==ActivityTypes.ACTIVITY_AWAKE then return true end
    -- Manual UnitPanel paths, 614-628, have different checks.
    if entry.owner==me then
        local hash=operation("SPY_COUNTERSPY")
        return hash~=nil and UnitManager.CanStartOperation(u,hash,nil,true)==true
    end
    for _,mission in ipairs(missions) do
        local row=GameInfo.UnitOperations["UNITOPERATION_"..mission]
        local hash=operation(mission)
        if row and row.CategoryInUI=="OFFENSIVESPY" and hash
            and UnitManager.CanStartOperation(u,hash,nil,false,false)==true then return true end
    end
    return false
end
local function spy_text(value)
    return type(value)=="string" and #value<=6000 and not string.find(value,"%z") and value or nil
end
local function spy_localize(value)
    if type(value)~="string" then return nil end
    if Locale and type(Locale.Lookup)=="function" then return spy_text(Locale.Lookup(value)) end
    return spy_text(value)
end
local function spy_city_name(entry)
    if type(entry.city.GetName)~="function" then spy_missing(); return nil end
    return spy_localize(entry.city:GetName())
end
local function spy_operation_details(u,entry,mission)
    return spy_formatted_details(u,entry.city,mission.row)
end
local function spy_sources_remaining(u,entry)
    -- RefreshTop 107-121 displays this only in the current city's actual
    -- MISSION_CHOOSER, never the destination chooser's remote preview.
    if type(player.GetDiplomacy)~='function' then return end
    local ok,diplomacy=pcall(player.GetDiplomacy,player)
    if not ok or (type(diplomacy)~='table' and type(diplomacy)~='userdata') then return end
    local value
    ok,value=pcall(function()
        if type(diplomacy.GetSourceTurnsRemaining)=='function' then
            return diplomacy:GetSourceTurnsRemaining(entry.city)
        end
    end)
    value=ok and spy_integer(value,0,2147483647) or nil
    if value~=nil then
        spy_menu_item(u,{id='sources_turns_remaining',name='获取来源加成剩余回合',value=value,
            description='当前驻城任务菜单显示的加成剩余回合；0 表示没有生效的来源加成。'})
    end
end
local function spy_districts(entry)
    if type(entry.city.GetDistricts)~="function" then return spy_missing() end
    local districts=entry.city:GetDistricts()
    if not districts or type(districts.Members)~="function" then return spy_missing() end
    local results={}
    local n=0
    for _,district in districts:Members() do
        n=n+1
        if n>256 then return spy_missing() end
        if type(district.GetX)~="function" or type(district.GetY)~="function"
            or type(district.GetType)~="function" then return spy_missing() end
        local x,y=district:GetX(),district:GetY()
        if spy_coord(x,y) then
            results[#results+1]={district=district,x=math.floor(x),y=math.floor(y)}
        end
    end
    return results
end
local function spy_district_name(districts,x,y)
    for _,district in ipairs(districts or {}) do
        if district.x==x and district.y==y and GameInfo.Districts then
            local row=GameInfo.Districts[district.district:GetType()]
            return row and spy_localize(row.Name) or nil
        end
    end
end
local function spy_rows(u,entry,missions,filter_x,filter_y)
    local city_plot=Map.GetPlot(entry.x,entry.y)
    if not city_plot then return {} end
    local rows={}
    local districts=nil
    local width,height=Map.GetGridSize()
    if type(width)~="number" or type(height)~="number" or width<=0 or height<=0
        or width*height>262144 then return spy_missing() end
    for _,mission in ipairs(missions) do
        local row=GameInfo.UnitOperations["UNITOPERATION_"..mission]
        local hash=operation(mission)
        local counter=mission=="SPY_COUNTERSPY"
        if row and hash and ((entry.owner==me and counter)
            or (entry.owner~=me and row.CategoryInUI=="OFFENSIVESPY")) then
            local can_start,result=UnitManager.CanStartOperation(u,hash,city_plot,false,true)
            if can_start==true then
                local added=false
                local plots=type(result)=="table" and result[UnitOperationResults.PLOTS] or nil
                if type(plots)=="table" then
                    local seen={}
                    for i,index in ipairs(plots) do
                        if i>512 then return spy_missing() end
                        if type(index)=="number" and index%1==0 and index>=0 and index<width*height and not seen[index] then
                            index=math.floor(index)
                            seen[index]=true
                            -- This plot came from the offered city mission.
                            -- Never substitute a caller-selected plot read.
                            local plot=Map.GetPlotByIndex(index)
                            if plot and type(plot.GetX)=="function" and type(plot.GetY)=="function" then
                                local x,y=plot:GetX(),plot:GetY()
                                if spy_coord(x,y) then
                                    x,y=math.floor(x),math.floor(y)
                                    local permitted=true
                                    if counter then
                                        if districts==nil then districts=spy_districts(entry) end
                                        if not districts then return nil end
                                        permitted=false
                                        for _,d in ipairs(districts) do
                                            if d.x==x and d.y==y then permitted=true; break end
                                        end
                                    end
                                    if permitted then
                                        added=true
                                        if filter_x==nil or (filter_x==x and filter_y==y) then
                                            rows[#rows+1]={mission=mission,row=row,hash=hash,plot=plot,x=x,y=y,available=true}
                                        end
                                    end
                                end
                            end
                        end
                    end
                end
                -- Offensive chooser fallback only. Counterspy without an
                -- offered matching district never gets a city-center target.
                if not counter and not added and (filter_x==nil or (filter_x==entry.x and filter_y==entry.y)) then
                    rows[#rows+1]={mission=mission,row=row,hash=hash,plot=city_plot,x=entry.x,y=entry.y,available=true}
                end
            elseif not counter and type(result)=="table" and UnitOperationResults.FAILURE_REASONS~=nil
                and type(result[UnitOperationResults.FAILURE_REASONS])=="table"
                and (filter_x==nil or (filter_x==entry.x and filter_y==entry.y)) then
                local reasons={}
                for i,reason in ipairs(result[UnitOperationResults.FAILURE_REASONS]) do
                    if i>32 then break end
                    local value=spy_text(reason)
                    if value then reasons[#reasons+1]=value end
                end
                rows[#rows+1]={mission=mission,row=row,hash=hash,plot=city_plot,x=entry.x,y=entry.y,
                    available=false,reason=table.concat(reasons,"; ")}
            end
        end
    end
    return rows
end
local function spy_destination_description(u,entry)
    local parts={"("..entry.x..", "..entry.y..")"}
    if type(UnitManager.GetTravelTime)=="function" and type(UnitManager.GetEstablishInCityTime)=="function" then
        local travel,establish=UnitManager.GetTravelTime(u,entry.city),UnitManager.GetEstablishInCityTime(u,entry.city)
        if type(travel)=="number" and type(establish)=="number" then
            parts[#parts+1]="Travel: "..travel.."; establish: "..establish
        end
    end
    local districts=spy_districts(entry)
    if districts then
        local names={}
        for _,district in ipairs(districts) do
            local d=district.district
            if type(d.IsComplete)~="function" then spy_missing(); return nil end
            if d:IsComplete()==true and GameInfo.Districts then
                local row=GameInfo.Districts[d:GetType()]
                if row and row.DistrictType~="DISTRICT_WONDER" then
                    local name=spy_localize(row.Name)
                    if name then names[#names+1]=name end
                end
            end
        end
        if #names>0 then parts[#parts+1]="Districts: "..table.concat(names,", ") end
    end
    return table.concat(parts,"; ")
end
local function spy_emit_rows(u,entry,rows,clickable)
    local city_name=spy_city_name(entry)
    if not city_name then return end
    local districts=spy_districts(entry)
    if not districts then return end
    for _,mission in ipairs(rows) do
        local parts={city_name,"("..mission.x..", "..mission.y..")"}
        local district=spy_district_name(districts,mission.x,mission.y)
        if district then parts[#parts+1]=district end
        if mission.reason then parts[#parts+1]=mission.reason end
        -- AddCounterspyOperation shows only the mission/district labels and
        -- hides its stats stack. Do not query offensive detail/probability APIs
        -- for it merely because the engine might provide additional data.
        if mission.mission~="SPY_COUNTERSPY" then
            if type(UnitManager.GetTimeToComplete)=="function" and type(mission.row.Index)=="number" then
                local turns=UnitManager.GetTimeToComplete(mission.row.Index,u)
                if type(turns)=="number" then parts[#parts+1]="Turns: "..turns end
            end
            if mission.available then
                local details=spy_operation_details(u,entry,mission)
                if details and details~="" then parts[#parts+1]=details end
            end
            if type(UnitManager.GetResultProbability)=="function"
                and type(mission.row.Index)=="number" then
                local probabilities=UnitManager.GetResultProbability(mission.row.Index,u,mission.plot)
                if type(probabilities)=="table" and type(probabilities.ESPIONAGE_SUCCESS_UNDETECTED)=="number" then
                    local success=probabilities.ESPIONAGE_SUCCESS_UNDETECTED
                    if type(probabilities.ESPIONAGE_SUCCESS_MUST_ESCAPE)=="number" then
                        success=success+probabilities.ESPIONAGE_SUCCESS_MUST_ESCAPE
                    end
                    if success>=0 and success<=1 then parts[#parts+1]="Success: "..math.floor(success*100+0.5).."%" end
                end
            end
        end
        local action=nil
        if clickable and mission.available then
            action={type="spy_mission",unit_id=spy_actor_id,mission=mission.mission,x=mission.x,y=mission.y}
        end
        spy_menu_item(u,{id=mission.mission..":"..mission.x..":"..mission.y,
            name=spy_localize(mission.row.Description) or mission.mission,
            description=table.concat(parts,"; "),value=action~=nil,action=action})
    end
end
'''


def _missions() -> str:
    # Keep the reviewed operation whitelist owned by units; avoid import cycles.
    from .units import SPY_MISSIONS
    return lua(list(SPY_MISSIONS))


def spy_travel_body(a: dict) -> str:
    return SPY_HELPERS + f'''
if not tactical() then return end
local rules=spy_setup(unit)
if not rules or not spy_travel_entry(unit) then return end
local cities=spy_cities(rules)
if not cities then return end
for _,entry in ipairs(cities) do
    if entry.x=={a['x']} and entry.y=={a['y']} and spy_can_travel(unit,entry) then
        if type(UnitManager.RequestOperation)~="function" then return end
        local current=spy_current(unit,cities)
        -- Selecting the own city we already occupy opens the counterspy
        -- chooser in stock UI; it does not send a travel request.
        if entry.owner==me and spy_same_city(entry,current) then return end
        attempt(UnitManager.RequestOperation,unit,operation("SPY_TRAVEL_NEW_CITY"),
            xy_params(UnitOperationTypes,entry.x,entry.y))
        return
    end
end
'''


def spy_body(a: dict) -> str:
    return SPY_HELPERS + f'''
if not tactical() then return end
local rules=spy_setup(unit)
if not rules then return end
local cities=spy_cities(rules)
if not cities then return end
local current=spy_current(unit,cities)
local missions={_missions()}
if not current or not spy_mission_entry(unit,current,missions) then return end
local rows=spy_rows(unit,current,{{{lua(a['mission'])}}},{a['x']},{a['y']})
if not rows or type(UnitManager.RequestOperation)~="function" then return end
for _,mission in ipairs(rows) do
    if mission.available then
        if mission.mission=="SPY_COUNTERSPY" then
            local params=xy_params(UnitOperationTypes,mission.x,mission.y)
            if not params then return end
            attempt(UnitManager.RequestOperation,unit,mission.hash,params)
        else
            attempt(UnitManager.RequestOperation,unit,mission.hash)
        end
        return
    end
end
'''


def spy_options(a: dict) -> str:
    return SPY_HELPERS + f'''
local rules=spy_setup(unit)
if not rules then return end
local cities=spy_cities(rules)
if not cities then return end
local current=spy_current(unit,cities)
local missions={_missions()}
local travel_entry=spy_travel_entry(unit)
local selected=nil
for _,entry in ipairs(cities) do
    if entry.x=={a['x']} and entry.y=={a['y']} then selected=entry; break end
end
local function inspect(entry,filter_x,filter_y)
    local here=spy_same_city(entry,current)
    local clickable=here and spy_mission_entry(unit,entry,missions)
    if not clickable and not travel_entry then return end
    local rows=spy_rows(unit,entry,missions,filter_x,filter_y)
    if not rows then return end
    if here and clickable then spy_sources_remaining(unit,entry) end
    spy_emit_rows(unit,entry,rows,clickable)
end
if selected then
    -- A city-center query discovers every offered district target.
    inspect(selected,nil,nil)
    if travel_entry and spy_can_travel(unit,selected)
        and not (selected.owner==me and spy_same_city(selected,current)) then
        spy_menu_item(unit,{{id="spy_travel",name=spy_city_name(selected),
            action={{type="spy_travel",unit_id=spy_actor_id,x=selected.x,y=selected.y}}}})
    end
else
    -- Compatibility for an already offered district coordinate: membership
    -- is established from city menus before reading any target plot.
    for _,entry in ipairs(cities) do inspect(entry,{a['x']},{a['y']}) end
end
'''


def spy_destinations(a: dict) -> str:
    return SPY_HELPERS + f'''
local rules=spy_setup(unit)
if not rules or not spy_travel_entry(unit) then return end
local cities=spy_cities(rules)
if not cities then return end
local current=spy_current(unit,cities)
local stop=math.min({a['offset']}+64,#cities)
for index={a['offset']}+1,stop do
    local entry=cities[index]
    local action=nil
    if spy_can_travel(unit,entry) and not (entry.owner==me and spy_same_city(entry,current)) then
        action={{type="spy_travel",unit_id=spy_actor_id,x=entry.x,y=entry.y}}
    end
    local name=spy_city_name(entry)
    local description=spy_destination_description(unit,entry)
    if name and description then
        spy_menu_item(unit,{{id="spy:"..entry.x..":"..entry.y,name=name,description=description,action=action}})
    end
end
spy_menu_item(unit,{{id="next_offset",value=stop<#cities and stop or -1,
    description="Offset in the stock spy chooser's revealed eligible city list; -1 means complete."}})
'''
