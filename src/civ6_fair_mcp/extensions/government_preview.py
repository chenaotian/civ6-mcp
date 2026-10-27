"""Optional fields from the normal government selection card, after unlock.

GovernmentScreen.lua:654-675, 2427-2454; GS replacement:18-49.
Never derive modifier totals or use another player's government state.
"""

GOVERNMENT_PREVIEW = r'''
local function government_preview(row, item)
    -- Caller has already checked this row with IsGovernmentUnlocked.
    local function field(object,key)
        local ok,value=pcall(function() return object[key] end)
        if ok then return value end
    end
    local function text(value,...)
        if type(value)~='string' or value=='' or #value>2400 or value:find('%z') then return nil end
        if Locale and type(Locale.Lookup)=='function' then
            local ok,result=pcall(Locale.Lookup,value,...)
            if not ok or type(result)~='string' or result=='' or #result>2400
                or result:find('%z') or result:match('^LOC_') then return nil end
            return result
        end
        if not value:match('^LOC_') then return value end
    end
    local function count(value,minimum)
        if type(value)=='number' and value==value and value>=minimum
            and value<=1000000 and value==math.floor(value) then return math.floor(value) end
    end
    local description={}
    local description_bytes=0
    local function describe(label,value)
        if value and description_bytes+#label+#value+1<=8000 then
            description[#description+1]=label..value
            description_bytes=description_bytes+#label+#value+1
        end
    end
    local function emit(suffix,name,value,details)
        add_item({id=row.GovernmentType..':'..suffix,name=name,value=value,description=details,
            scope='self',owner_id=me})
    end
    describe('固有效果：',text(field(row,'InherentBonusDesc')))
    -- The active rules database supplies the XP1/XP2 replacement text. Do not
    -- reconstruct its percentages from GovernmentModifiers/ModifierArguments.
    local ruleset_bonus=text(field(row,'AccumulatedBonusDesc'))
        or text(field(row,'AccumulatedBonusShortDesc'))
    describe('规则集效果：',ruleset_bonus)

    local influence=count(field(row,'InfluencePointsPerTurn'),0)
    local threshold=count(field(row,'InfluencePointsThreshold'),1)
    local tokens=count(field(row,'InfluenceTokensPerThreshold'),0)
    if influence and threshold and tokens then
        describe('',text('LOC_GOVT_INFLUENCE_POINTS_TOWARDS_ENVOYS',influence,threshold,tokens))
        emit('influence_points_per_turn','基础影响力点数／回合',influence)
        emit('influence_points_threshold','基础使者授予所需影响力点数',threshold)
        emit('influence_tokens_per_threshold','达到阈值时的基础使者数',tokens)
    end
    local rules_ok,rules=pcall(function() return GameConfiguration.GetValue('RULESET') end)
    if rules_ok and rules=='RULESET_EXPANSION_2' then
        local favor_ok,favor=pcall(function()
            if not GameInfo.Governments_XP2 then return nil end
            local n=0
            for entry in GameInfo.Governments_XP2() do
                n=n+1;if n>128 then return nil end
                if entry.GovernmentType==row.GovernmentType then return count(entry.Favor,0) end
            end
        end)
        if favor_ok and favor~=nil then
            describe('',text('LOC_GOVT_FAVOR_PER_TURN',favor))
            emit('favor_per_turn','基础外交支持／回合',favor)
        end
    end

    -- These are exactly the selection card's base icons, not the player's
    -- extra slots. The current actual slots remain the existing slot:* rows.
    local types={'SLOT_MILITARY','SLOT_ECONOMIC','SLOT_DIPLOMATIC','SLOT_WILDCARD'}
    local fallback={'军事','经济','外交','通配'}
    local slots_ok,slots=pcall(function()
        if not GameInfo.Government_SlotCounts then return nil end
        local result={SLOT_MILITARY=0,SLOT_ECONOMIC=0,SLOT_DIPLOMATIC=0,SLOT_WILDCARD=0}
        local n,found,total=0,false,0
        for entry in GameInfo.Government_SlotCounts() do
            n=n+1;if n>4096 then return nil end
            if entry.GovernmentType==row.GovernmentType then
                local slot=entry.GovernmentSlotType
                if slot=='SLOT_GREAT_PERSON' then slot='SLOT_WILDCARD' end
                local number=count(entry.NumSlots,0)
                if result[slot]==nil or number==nil then return nil end
                found=true;result[slot]=result[slot]+number;total=total+number
                if total>128 then return nil end
            end
        end
        if found then result.total=total;return result end
    end)
    if slots_ok and slots then
        local summary={}
        for index,slot in ipairs(types) do
            local definition=GameInfo.GovernmentSlots and field(GameInfo.GovernmentSlots,slot)
            local name=text(definition and field(definition,'Name')) or fallback[index]
            summary[#summary+1]=name..' '..slots[slot]
            emit('base_slots:'..slot,name,slots[slot],
                '政体选择卡的基础槽位；不含文明、奇观等额外槽位。当前实际槽位见 slot:*。')
        end
        emit('base_slots:total','政体基础槽位总数',slots.total,
            '政体选择卡的基础槽位合计；不代表切换后本玩家的最终槽位总数。')
        describe('基础槽位（不含额外槽位）：',table.concat(summary,'；'))
    end
    if #description>0 then item.description=table.concat(description,'\n') end
end
'''
