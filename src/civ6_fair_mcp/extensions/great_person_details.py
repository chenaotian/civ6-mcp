"""Own GP points and visible price buttons from GreatPeoplePopup.lua."""

GP_MENU_HELPERS = r'''
local function gp_read(object,method,...)
    if not object then return nil end
    local ok,fn=pcall(function() return object[method] end)
    if not ok or type(fn)~="function" then return nil end
    local called,value=pcall(fn,object,...)
    if called then return value end
end
local function gp_number(value)
    return type(value)=="number" and value==value and value>=0 and value<1e12
end
local function gp_capability(name)
    if not GameCapabilities or type(GameCapabilities.HasCapability)~="function" then return false end
    local ok,value=pcall(GameCapabilities.HasCapability,name)
    return ok and value==true
end
local function gp_patronage(people,individual,yield)
    if not gp_capability("CAPABILITY_GREAT_PEOPLE_RECRUIT_WITH_"..yield)
        or gp_read(people,"CanRecruitPerson",me,individual)~=false
        or gp_read(people,"CanRejectPerson",me,individual)~=false then return nil,false end
    local yield_type=YieldTypes and YieldTypes[yield]
    if type(yield_type)~="number" then return nil,false end
    local cost=gp_read(people,"GetPatronizeCost",me,individual,yield_type)
    -- Exact stock button visibility threshold; a displayed unaffordable
    -- quote is informational and never becomes permission to patronize.
    if not gp_number(cost) or cost>=1000000 then return nil,false end
    return cost,gp_read(people,"CanPatronizePerson",me,individual,yield_type)==true
end
'''

GP_POINT_OBSERVATION = r'''
do
    local points=gp_read(player,"GetGreatPeoplePoints")
    if points and GameInfo.GreatPersonClasses then
        local function collect_points()
            local records,seen={},{}
            local checked=0
            for row in GameInfo.GreatPersonClasses() do
                checked=checked+1;if checked>128 then return nil end
                local identifier,index=row.GreatPersonClassType,row.Index
                if type(identifier)~="string" or not identifier:match("^GREAT_PERSON_CLASS_[A-Z0-9_]+$")
                    or #identifier>128 or not gp_number(index) or index%1~=0 or seen[identifier] then return nil end
                seen[identifier]=true
                local total=gp_read(points,"GetPointsTotal",index)
                local per_turn=gp_read(points,"GetPointsPerTurn",index)
                if gp_number(total) then records[#records+1]={id=identifier..":points",name=row.Name,value=total} end
                if gp_number(per_turn) then
                    -- GreatPeoplePopup:441 rounds its point-rate tooltip to one decimal.
                    records[#records+1]={id=identifier..":points_per_turn",name=row.Name,value=math.floor(per_turn*10+0.5)/10}
                end
            end
            return records
        end
        local ok,records=pcall(collect_points)
        if ok and type(records)=="table" then
            for _,record in ipairs(records) do add(record.id,record.name,nil,record.value) end
        end
    end
end
'''
