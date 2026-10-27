"""Read-only labels from the same definitions/results used by stock UnitPanel.

UnitPanel.lua:427-530 and 574-704 use action Description, ACTION_NAME and
ADDITIONAL_DESCRIPTION. Promotions use Name/Description (2288-2294 and
UnitPromotionPopup.lua:274-275). Failure reasons and target/result lists are
deliberately not inspected. All callers first establish own actor/menu eligibility.
"""

UNIT_LABEL_HELPERS = r'''
local function unit_text(value,limit)
    if type(value)~="string" or value=="" or #value>limit or value:find("%z") then return nil end
    return value
end
local function unit_localize(key,limit,...)
    if type(key)~="string" or key=="" or not Locale or type(Locale.Lookup)~="function" then return nil end
    local ok,value=pcall(Locale.Lookup,key,...)
    if ok and not (value==key and key:match("^LOC_")) then return unit_text(value,limit) end
end
local function unit_safe_read(object,method,...)
    if not object or type(object[method])~="function" then return nil end
    local ok,value=pcall(object[method],object,...)
    if ok then return value end
end
local function unit_row_text(row)
    if not row then return nil,nil end
    local description=unit_localize(row.Description,8192)
    -- Action rows normally have only Description: it is their actual UI label.
    local name=unit_localize(row.Name,1024) or unit_text(description,1024)
    return name,description
end
local function unit_action_row(family,name)
    local rows=family=="operation" and GameInfo.UnitOperations or GameInfo.UnitCommands
    return rows and rows[(family=="operation" and "UNITOPERATION_" or "UNITCOMMAND_")..name]
end
local function unit_join_text(first,second)
    if not first then return second end
    if not second then return first end
    return unit_text(first.."[NEWLINE]"..second,8192) or first
end
local function unit_apply_result_text(item,results)
    if not UnitOperationResults or type(results)~="table" then return end
    local action_key=UnitOperationResults.ACTION_NAME
    if action_key~=nil then
        local text=unit_localize(results[action_key],8192)
        if text then
            item.description=text
            item.name=unit_text(text,1024) or item.name
        end
    end
    local extra_key=UnitOperationResults.ADDITIONAL_DESCRIPTION
    if extra_key~=nil then
        local extra=results[extra_key]
        if type(extra)=="table" then
            for index,key in ipairs(extra) do
                if index>64 then break end
                item.description=unit_join_text(item.description,unit_localize(key,8192))
            end
        end
    end
end
local function unit_result_labels_impl(item,unit,family,hash,params)
    -- Additional metadata must never authorize an action. The existing caller
    -- has already checked this precise self-tile option; this is optional text.
    if not UnitManager or not UnitOperationResults then return end
    local method=family=="operation" and UnitManager.CanStartOperation or UnitManager.CanStartCommand
    if type(method)~="function" then return end
    local ok,allowed,results
    if family=="operation" then
        local mode=params and true or (OperationResultsTypes and OperationResultsTypes.NO_TARGETS)
        if mode==nil then return end
        ok,allowed,results=pcall(method,unit,hash,nil,params or false,mode)
    else
        ok,allowed,results=pcall(method,unit,hash,params or false,true)
    end
    if not ok or allowed~=true or type(results)~="table" then return end
    unit_apply_result_text(item,results)
    -- UnitPanel:478-487 gives a successful upgrade's destination type and own
    -- gold cost. No failure/hidden-target result fields are touched.
    if family=="command" and UnitCommandTypes and hash==UnitCommandTypes.UPGRADE
        and UnitCommandResults and UnitCommandResults.UNIT_TYPE~=nil then
        local index=results[UnitCommandResults.UNIT_TYPE]
        local row=type(index)=="number" and GameInfo.Units and GameInfo.Units[index]
        local cost=unit_safe_read(unit,"GetUpgradeCost")
        if row and type(row.Name)=="string" and type(cost)=="number" and cost==cost and cost>=0 and cost<1e15 then
            local text=unit_localize("LOC_UNITOPERATION_UPGRADE_INFO",8192,row.Name,cost)
            item.description=unit_join_text(text,item.description)
            item.value=cost
        end
    end
end
local function unit_result_labels(item,unit,family,hash,params)
    -- Treat all metadata as optional, including result-key access failures.
    -- Build separately so a failed formatter cannot partially alter a choice.
    local metadata={name=item.name,description=item.description,value=item.value}
    local ok=pcall(unit_result_labels_impl,metadata,unit,family,hash,params)
    if ok then
        item.name,item.description,item.value=metadata.name,metadata.description,metadata.value
    end
end
local function unit_great_person_action(unit,hash)
    -- UnitPanel:466-530 keeps an own-unit command visible when the UI-mode
    -- check succeeds, even when its current-location check disables it. This
    -- record describes that button; it never contains an executable action.
    if not hash or not UnitManager or type(UnitManager.CanStartCommand)~="function" then return nil end
    local ok,shown=pcall(UnitManager.CanStartCommand,unit,hash,true)
    if not ok or shown~=true then return nil end
    local checked,available,results=pcall(UnitManager.CanStartCommand,unit,hash,false,true)
    local name,description=unit_row_text(unit_action_row("command","ACTIVATE_GREAT_PERSON"))
    local item={name=name,description=description}
    -- A current-location check may not provide a boolean. Its absence says
    -- nothing about whether this already UI-authorized description is public.
    -- Preserve the text; never coerce unknown availability into false/true.
    if checked and type(available)=="boolean" then item.value=available end
    local metadata={name=name,description=description}
    if checked and pcall(unit_apply_result_text,metadata,results) then
        item.name,item.description=metadata.name,metadata.description
    end
    return item
end
local function unit_great_person_ability_impl(row)
    -- CivilopediaPage_GreatPerson:27-35,137-154 describes the already-owned
    -- individual's static ability regardless of the current unit's location.
    -- This is a rules description, never an activation candidate or forecast.
    if not row or type(row.GreatPersonIndividualType)~="string" then return nil end
    if row.GreatPersonClassType=="GREAT_PERSON_CLASS_PROPHET" then
        local description=unit_localize("LOC_GREATPERSON_ACTION_USAGE_FOUND_RELIGION",8192)
        if description then return {description=description} end
        return nil
    end
    local charges=row.ActionCharges
    if type(charges)~="number" or charges%1~=0 or charges<=0 or charges>1024 then return nil end
    local description
    if row.ActionEffectTextOverride~=nil then
        description=unit_localize(row.ActionEffectTextOverride,8192)
    elseif GameInfo.GreatPersonIndividualActionModifiers and GameEffects
        and type(GameEffects.GetModifierTextKey)=="function" and type(GameEffects.GetModifierText)=="function" then
        local parts,n={},0
        for modifier in GameInfo.GreatPersonIndividualActionModifiers() do
            n=n+1; if n>8192 then return nil end
            if modifier.GreatPersonIndividualType==row.GreatPersonIndividualType then
                local id=modifier.ModifierId
                if type(id)=="string" then
                    -- GameEffectsText.lua:11-15: the engine formats the public
                    -- Summary using this ruleset/game speed. No manual effect
                    -- reconstruction, runtime modifier enumeration or timeline.
                    local key=GameEffects.GetModifierTextKey(id,"Summary")
                    if type(key)=="string" and key~="" then
                        local text=unit_text(GameEffects.GetModifierText(id,key),8192)
                        if text then
                            if #parts>=64 then return nil end
                            parts[#parts+1]=text
                        end
                    end
                end
            end
        end
        description=unit_text(table.concat(parts,"[NEWLINE]"),8192)
    end
    if not description then return nil end
    local action_name=row.ActionNameTextOverride or "LOC_GREATPERSON_ACTION_NAME_DEFAULT"
    local name=unit_localize("LOC_UI_PEDIA_GREATPERSON_ACTION",1024,action_name,charges)
    return {name=name,description=description}
end
local function unit_great_person_ability(row)
    local ok,info=pcall(unit_great_person_ability_impl,row)
    if ok then return info end
end
'''
