"""Read-only fields displayed by the stock city-state menu.

Source: Base/Assets/UI/PartialScreens/CityStates.lua:24-27,128-188,
255-274,377-389,1330-1352,1440-1552,1593-1620; Gathering Storm
CityStates_Expansion2.lua:14-44. No foreign city/unit/resource scans.
"""

# Thresholds intentionally match the installed stock UI constants (1/3/6 and
# minimum 3 for suzerainty). That UI has no exposed engine threshold getter.
# Locale resolves the installed ruleset's reward descriptions.
CITY_STATE_DETAILS = r'''
local function city_state_details(id,other,name,local_influence,can_envoy,can_levy,can_war,can_peace)
    -- The caller has already applied the shared city_state predicate. Keep the
    -- knowledge check here too, before any detail or identity getter.
    if id==me or not known_player(id) then return end
    local prefix="city_state_"..id
    local complete=true
    local function read(object,method,...)
        if not object or type(object[method])~="function" then return nil end
        local ok,value=pcall(object[method],object,...)
        if ok then return value end
        return nil
    end
    local function put(key,title,value,description)
        local row={id=prefix..(key~="" and ":"..key or ""),name=name..(title~="" and ": "..title or ""),
            scope="met",owner_id=id,met=true}
        if value~=nil then row.value=value end
        if description~=nil then row.description=description end
        add_item(row)
    end
    local function count(value)
        return int(value) and value>=0 and value<2147483648
    end
    local function number_field(key,title,value)
        if count(value) then put(key,title,value);return value end
        complete=false
        return nil
    end
    put("","",id,"Encountered living city-state; retained even when no action is currently available.")
    local influence=read(other,"GetInfluence")
    local envoys=number_field("envoys","Your envoys",read(influence,"GetTokensReceived",me))
    local most=number_field("most_envoys","Most envoys received",read(influence,"GetMostTokensReceived"))
    local suzerain=read(influence,"GetSuzerain")
    if int(suzerain) and suzerain>=-1 and suzerain<=63 then
        put("is_suzerain","You are suzerain",suzerain==me)
        if suzerain==-1 then
            put("suzerain","Suzerain","none",label("LOC_CITY_STATES_NONE"))
        elseif suzerain==me then
            put("suzerain","Suzerain","self",label("LOC_CITY_STATES_YOU"))
        elseif known_player(suzerain) then
            local config=PlayerConfigurations[suzerain]
            local text=read(config,"GetPlayerName") or read(config,"GetCivilizationShortDescription")
            put("suzerain","Suzerain","known",type(text)=="string" and label(text) or "Known civilization")
            put("suzerain_player","Known suzerain player",suzerain)
        else
            -- No unknown ID in any key, value, caption, or permission metadata.
            put("suzerain","Suzerain","unknown",label("LOCAL_CITY_STATES_UNKNOWN"))
        end
        if most then
            local target=most<3 and 3 or (suzerain~=me and most+1 or most)
            put("suzerain_target_envoys","Suzerain envoy total shown by stock UI",target,
                "The menu's total envoy target, not an extra envoy cost; ties do not create a suzerain.")
        end
    else complete=false end

    -- The stock "Influenced by" list shows each positive envoy count and an
    -- anonymous caption for unmet contributors. Sort anonymous counts without
    -- carrying their player IDs into record IDs or output permission metadata.
    if PlayerManager and type(PlayerManager.GetAliveMajorIDs)=="function" then
        local ok,majors=pcall(PlayerManager.GetAliveMajorIDs)
        if ok and type(majors)=="table" and #majors<=64 then
            local anonymous,seen={},{}
            for _,major in ipairs(majors) do
                if int(major) and major>=0 and major<=63 and not seen[major] then
                    seen[major]=true
                    local tokens=read(influence,"GetTokensReceived",major)
                    if count(tokens) then
                        if tokens>0 then
                            if major==me then
                                put("influence:self","Your envoy contribution",tokens)
                            elseif known_player(major) then
                                local cfg=PlayerConfigurations[major]
                                local title=read(cfg,"GetPlayerName") or read(cfg,"GetCivilizationShortDescription")
                                put("influence:"..major,type(title)=="string" and label(title) or "Known civilization",tokens)
                            else
                                anonymous[#anonymous+1]=tokens
                            end
                        end
                    else complete=false end
                else complete=false end
            end
            table.sort(anonymous,function(a,b) return a>b end)
            for index,tokens in ipairs(anonymous) do
                put("influence_unknown:"..index,label("LOCAL_CITY_STATES_UNKNOWN"),tokens,
                    "Anonymous contributor in this menu; the ordinal is not a player ID.")
            end
        else complete=false end
    else complete=false end

    local diplomacy=read(player,"GetDiplomacy")
    local at_war=read(diplomacy,"IsAtWarWith",id)
    if type(at_war)=="boolean" then put("at_war","At war",at_war) else complete=false end
    local military=city_state_military_allowed()==true
    put("military_available","Military actions available",military)
    put("can_send_envoy","Can send one envoy",can_envoy,
        not can_envoy and "The normal envoy menu does not currently permit sending one envoy." or nil)
    put("can_levy","Can levy military",can_levy,
        not can_levy and "The normal levy button is unavailable or disabled." or nil)
    put("can_declare_war","Can declare war",can_war,
        not can_war and (at_war==true and "Already at war." or "The normal war button is unavailable or disabled.") or nil)
    put("can_make_peace","Can make peace",can_peace,
        not can_peace and (at_war==false and "Not at war." or "The normal peace button is unavailable or disabled.") or nil)
    if military then
        local levy_cost=read(local_influence,"GetLevyMilitaryCost",id)
        if count(levy_cost) then
            -- Preserve the pre-existing cost record ID, now also when disabled,
            -- as the stock button tooltip shows the price before affordability.
            add_item({id="levy_cost_"..id,name=name..": levy gold cost",value=levy_cost,scope="met",owner_id=id,met=true})
        else complete=false end
        number_field("levy_duration","Levy duration",read(influence,"GetLevyTurnLimit"))
        local levy_counter=read(influence,"GetLevyTurnCounter")
        if type(levy_counter)=="number" then put("levy_active","Military already levied",levy_counter>=0)
        else complete=false end
    end

    local config=PlayerConfigurations[id]
    local leader=read(config,"GetLeaderTypeName")
    local info=type(leader)=="string" and GameInfo.Leaders and GameInfo.Leaders[leader]
    local category=nil
    for _,kind in ipairs({"SCIENTIFIC","RELIGIOUS","TRADE","CULTURAL","MILITARISTIC","INDUSTRIAL"}) do
        local parent="LEADER_MINOR_CIV_"..kind
        if leader==parent or (info and info.InheritFrom==parent) then category=kind;break end
    end
    if category then
        put("type",label("LOC_CITY_STATES_TYPE_"..category),category=="CULTURAL" and "CULTURE" or category)
        for _,tier in ipairs({{1,"SMALL"},{3,"MEDIUM"},{6,"LARGE"}}) do
            local text=label("LOC_MINOR_CIV_"..category.."_TRAIT_"..tier[2].."_INFLUENCE_BONUS")
            put("bonus:"..tier[1],label("LOC_MINOR_CIV_"..tier[2].."_INFLUENCE_ENVOYS"),tier[1],text)
        end
    else complete=false end

    -- Only the unique trait text and diplomatic rules from the public tooltip.
    -- Its resource-inventory suffix is intentionally not evaluated (P04).
    if type(leader)=="string" and GameInfo.LeaderTraits and GameInfo.Traits then
        local examined=0
        for pair in GameInfo.LeaderTraits() do
            examined=examined+1;if examined>2048 then error("unavailable") end
            if pair.LeaderType==leader then
                local trait=GameInfo.Traits[pair.TraitType]
                if trait and type(trait.Description)=="string" then
                    put("unique_bonus:"..pair.TraitType,"Unique suzerain bonus",nil,label(trait.Description))
                end
            end
        end
        put("suzerain_rules","Suzerain diplomatic benefits",nil,label("LOC_CITY_STATES_SUZERAIN_DIPLOMATIC_BONUS"))
    else complete=false end
    local disabled=read(influence,"IsSuzerainUniqueBonusDisabled")
    if type(disabled)=="boolean" then put("unique_bonus_disabled","Unique suzerain bonus disabled",disabled) end

    -- These eight stock quests contain only this player's menu objective text;
    -- never query a target plot, another player's quest, or a modded quest body.
    local allowed={QUEST_CONVERT_CAPITAL_TO_RELIGION=true,QUEST_SEND_TRADE_ROUTE=true,
        QUEST_CLEAR_BARBARIAN_CAMP=true,QUEST_TRAIN_UNIT_TYPE=true,QUEST_ZONE_DISTRICT_TYPE=true,
        QUEST_TRIGGER_TECH_BOOST=true,QUEST_TRIGGER_CIVIC_BOOST=true,QUEST_RECRUIT_GREAT_PERSON_CLASS=true}
    local manager=nil
    if Game and type(Game.GetQuestsManager)=="function" then
        local ok,value=pcall(Game.GetQuestsManager);if ok then manager=value end
    end
    if manager and type(manager.HasActiveQuestFromPlayer)=="function" and GameInfo.Quests then
        local active,examined=0,0
        local count_known=true
        for quest in GameInfo.Quests() do
            examined=examined+1;if examined>256 then error("unavailable") end
            if allowed[quest.QuestType] then
                local is_active=read(manager,"HasActiveQuestFromPlayer",me,id,quest.Index)
                if is_active==true then
                    active=active+1
                    local title=read(manager,"GetActiveQuestName",me,id,quest.Index)
                    local description=read(manager,"GetActiveQuestDescription",me,id,quest.Index)
                    local reward=read(manager,"GetActiveQuestReward",me,id,quest.Index)
                    if type(title)=="string" and type(description)=="string" and type(reward)=="string" then
                        put("quest:"..quest.QuestType,title,nil,description.."\n"..reward)
                    else complete=false end
                elseif is_active~=false then complete=false;count_known=false end
            else complete=false;count_known=false end
        end
        if count_known then put("quest_count","Current local quests",active) end
    else complete=false end
    put("details_status","Detail availability",complete and "complete" or "partial",
        not complete and "Some menu details are unavailable; missing fields are not zero or false." or nil)
end
'''
