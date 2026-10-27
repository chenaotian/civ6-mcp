"""Optional own era-panel state; no rival scores or hidden future dedications."""

ERA_OBSERVATION = r'''
do
    local function read_era(method)
        local ok,value=pcall(function()
            if type(eras[method])=="function" then return eras[method](eras,me) end
        end)
        if ok then return value end
    end
    for id,method in pairs({era_score="GetPlayerCurrentScore",dark_age_threshold="GetPlayerDarkAgeThreshold",
        golden_age_threshold="GetPlayerGoldenAgeThreshold"}) do
        local value=read_era(method)
        if type(value)=="number" and value==value and value%1==0 and value>=0 and value<1e12 then
            add(id,nil,nil,math.floor(value))
        end
    end
    local heroic,golden,dark=read_era("HasHeroicGoldenAge"),read_era("HasGoldenAge"),read_era("HasDarkAge")
    local age
    if heroic==true then age="heroic"
    elseif heroic==false and golden==true then age="golden"
    elseif heroic==false and golden==false and dark==true then age="dark"
    elseif heroic==false and golden==false and dark==false then age="normal" end
    if age then add("age",nil,nil,age) end
    local normal_quests
    if age=="heroic" or age=="golden" then normal_quests=read_era("IsPlayerAlwaysAllowedCommemorationQuest") end
    local active=read_era("GetPlayerActiveCommemorations")
    if type(active)=="table" then
        local records,seen={},{}
        local count=0
        local ok=pcall(function()
            for _,index in ipairs(active) do
                count=count+1;if count>128 or type(index)~="number" or index%1~=0 or index<0 then error("unavailable") end
                local row=GameInfo.CommemorationTypes[index]
                if not row or type(row.CommemorationType)~="string" or not row.CommemorationType:match("^COMMEMORATION_[A-Z0-9_]+$")
                    or seen[row.CommemorationType] then error("unavailable") end
                seen[row.CommemorationType]=true
                local bonus
                if age=="heroic" or age=="golden" then bonus=row.GoldenAgeBonusDescription
                elseif age=="dark" then bonus=row.DarkAgeBonusDescription
                elseif age=="normal" then bonus=row.NormalAgeBonusDescription end
                records[#records+1]={id="active:"..row.CommemorationType,name=row.CategoryDescription,description=bonus}
                if normal_quests==true then
                    records[#records+1]={id="active:"..row.CommemorationType..":normal_age_bonus",
                        name=row.CategoryDescription,description=row.NormalAgeBonusDescription}
                end
            end
        end)
        if ok then for _,record in ipairs(records) do add(record.id,record.name,record.description,true) end end
    end
end
'''
