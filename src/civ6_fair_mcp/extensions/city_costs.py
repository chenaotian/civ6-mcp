"""Fixed read-only city price/production helpers matching the stock UI.

The caller must first establish own-city identity and the relevant menu or plot
eligibility. These helpers never turn a quote into permission to submit an action.
"""

CITY_PURCHASE_HELPERS = r'''
local function city_purchase_in_menu(row, kind, yield)
    -- ProductionPanel's outer gate applies even when the command checker says
    -- yes. A permissive engine check alone does not make an item a UI choice.
    if kind == 'Districts' then return true end
    if kind ~= 'Units' and kind ~= 'Buildings' then return false end
    if row.PurchaseYield == 'YIELD_'..yield then return true end
    if yield ~= 'FAITH' or type(city.GetGold) ~= 'function' then return false end
    local ok, gold = pcall(city.GetGold, city)
    if not ok or gold == nil then return false end
    local name = kind == 'Units' and 'IsUnitFaithPurchaseEnabled' or 'IsBuildingFaithPurchaseEnabled'
    if type(gold[name]) ~= 'function' then return false end
    local enabled
    ok, enabled = pcall(gold[name], gold, row.Hash)
    return ok and enabled == true
end
local function city_can_afford(row, yield, formation)
    local getter
    if yield == 'GOLD' then getter = player.GetTreasury
    elseif yield == 'FAITH' then getter = player.GetReligion
    else return false end
    if type(getter) ~= 'function' then return false end
    local ok, source = pcall(getter, player)
    if not ok or source == nil or type(source.CanAfford) ~= 'function' then return false end
    local affordable
    if formation == 'STANDARD' then
        ok, affordable = pcall(source.CanAfford, source, city:GetID(), row.Hash)
    else
        local f = MilitaryFormationTypes and MilitaryFormationTypes[formation..'_MILITARY_FORMATION']
        if type(f) ~= 'number' then return false end
        ok, affordable = pcall(source.CanAfford, source, city:GetID(), row.Hash, f)
    end
    return ok and affordable == true
end
local function city_can_afford_plot(index)
    if type(city.GetGold) ~= 'function' or type(player.GetTreasury) ~= 'function' then return false end
    local gold_ok, gold = pcall(city.GetGold, city)
    local treasury_ok, treasury = pcall(player.GetTreasury, player)
    if not gold_ok or not treasury_ok or not gold or not treasury
        or type(gold.GetPlotPurchaseCost) ~= 'function' or type(treasury.GetGoldBalance) ~= 'function' then return false end
    local cost_ok, cost = pcall(gold.GetPlotPurchaseCost, gold, index)
    local balance_ok, balance = pcall(treasury.GetGoldBalance, treasury)
    return cost_ok and balance_ok and type(cost) == 'number' and cost == cost and cost >= 0 and cost < 1e12
        and type(balance) == 'number' and balance == balance and balance >= cost and balance < 1e12
end
'''


CITY_PRODUCTION_DIAGNOSTICS = r'''
-- Retain only disabled entries whose stock menu visibility can be established
-- without the new-district/wonder purchasable-plot adjacency helpers.
local function production_diagnostic_allowed(row,kind,placed)
    if kind~='Buildings' and kind~='Districts' then return false end
    local queue=city_cost_read(city,'GetBuildQueue')
    if not queue or type(queue.GetCurrentProductionTypeHash)~='function' then return false end
    local ok,current=pcall(queue.GetCurrentProductionTypeHash,queue)
    if not ok or (current~=nil and (type(current)~='number' or current~=current)) then return false end
    if kind=='Districts' then
        -- ProductionPanel.lua:1909-1911. New placements remain on the existing
        -- path because purchasable plots can change the stock disabled state.
        return placed==true and (row.Hash~=current or row.OnePerCity==false)
    end
    if row.IsWonder or row.RequiresPlacement or row.Hash==current then return false end
    -- A repairing prerequisite district suppresses its building list entirely.
    local district=current~=nil and GameInfo.Districts and GameInfo.Districts[current]
    if district and row.PrereqDistrict then
        local name=district.DistrictType
        local replacement=GameInfo.DistrictReplaces and GameInfo.DistrictReplaces[name]
        if replacement then name=replacement.ReplacesDistrictType end
        if row.PrereqDistrict==name then return false end
    end
    return true
end
local function production_condition_quote(id,row,kind,available,results)
    add(id..':production_available','当前直接生产条件通过',
        '当前直接生产检查；新区域或奇观的选址及购地按钮仍需单独检查。',available==true)
    local component,argument
    if kind=='Buildings' then component=city_cost_read(city,'GetBuildings');argument=row.Hash
    elseif kind=='Districts' then component=city_cost_read(city,'GetDistricts');argument=row.Index end
    if component then
        local repair=city_cost_read(component,'IsPillaged',argument)
        if type(repair)=='boolean' then
            add(id..':repair','修复项目','原版生产菜单的掠夺/修复标记。',repair)
        end
    end
    if available then return end
    -- ProductionPanel.lua:1574-1583 localizes the failure array. Its flood
    -- special case (62,1934) also accepts already-localized text. Only match
    -- these reviewed no-argument static messages; never localize unknown data.
    local safe={}
    for _,key in ipairs({
        'LOC_BUILDING_CONSTRUCT_IS_OCCUPIED',
        'LOC_BUILDING_CONSTRUCT_DISTRICT_IS_OCCUPIED_BY_ENEMY',
        'LOC_BUILDING_CONSTRUCT_DISTRICT_IS_PILLAGED',
        'LOC_DISTRICT_REPAIR_LOCATION_FLOODED'}) do
        local text=key
        if Locale and type(Locale.Lookup)=='function' then
            local ok,value=pcall(Locale.Lookup,key)
            if ok and type(value)=='string' and #value>0 and #value<=2048 then text=value end
        end
        safe[key]=text;safe[text]=text
    end
    local flag=CityCommandResults and CityCommandResults.FAILURE_REASONS
    local reasons=type(results)=='table' and flag~=nil and results[flag]
    local seen,n={},0
    if type(reasons)=='table' then
        for i,value in ipairs(reasons) do
            if i>64 then break end
            local text=type(value)=='string' and safe[value]
            if text and not seen[text] then
                seen[text]=true;n=n+1
                add(id..':failure_reason:'..n,'原版生产限制',text,text)
            end
        end
    end
    add(id..':failure_explanation_available','已提供固定原版失败原因',
        '仅返回已核对的固定原版原因；未列出的原因不代表不存在，false 表示本次未提供具体原因。',n>0)
end
'''


CITY_COST_HELPERS = r'''
local function city_cost_read(object, name, ...)
    if object == nil then return nil end
    local found, method = pcall(function() return object[name] end)
    if not found or type(method) ~= 'function' then return nil end
    local ok, value = pcall(method, object, ...)
    if ok then return value end
    return nil
end
local function city_cost_number(value)
    return type(value) == 'number' and value == value and value >= 0 and value < 1e12
end
local function city_cost_index(value)
    return city_cost_number(value) and value <= 2147483647 and value == math.floor(value)
end
local function production_quote(id, row, kind, formation, include_turns)
    if not city_cost_index(row.Index) then return end
    local queue = city_cost_read(city, 'GetBuildQueue')
    local stem = ({Units='Unit',Buildings='Building',Districts='District',Projects='Project'})[kind]
    if not stem then return end
    local cost_method = 'Get'..stem..'Cost'
    if kind == 'Units' and formation == 'CORPS' then cost_method = 'GetUnitCorpsCost'
    elseif kind == 'Units' and formation == 'ARMY' then cost_method = 'GetUnitArmyCost' end
    local cost = city_cost_read(queue, cost_method, row.Index)
    local progress = city_cost_read(queue, 'Get'..stem..'Progress', row.Index)
    if city_cost_number(cost) then
        add(id..':production_cost', '生产成本', '单位：生产力点；当前城市的实际成本，含适用的编队或修复规则。', cost)
    end
    if city_cost_number(progress) then
        add(id..':production_progress', '已有生产进度', '单位：生产力点；当前城市已经投入的生产进度。', progress)
    end
    if include_turns == false then return end
    -- ProductionPanel uses type strings for districts/projects, hashes for
    -- units/buildings, and a second formation argument only for corps/armies.
    local target = row.Hash
    if kind == 'Districts' then target = row.DistrictType
    elseif kind == 'Projects' then target = row.ProjectType end
    local turns
    if kind == 'Units' and formation ~= 'STANDARD' then
        local f = MilitaryFormationTypes and MilitaryFormationTypes[formation..'_MILITARY_FORMATION']
        if type(f) == 'number' then turns = city_cost_read(queue, 'GetTurnsLeft', target, f) end
    elseif target ~= nil then turns = city_cost_read(queue, 'GetTurnsLeft', target) end
    if turns == -1 then
        add(id..':production_indefinite', '当前无法完成生产', '原版预计工期为 999+；不表示已完成，也不等于零回合。', true)
    elseif city_cost_index(turns) then
        add(id..':production_turns', '预计生产工期', '单位：回合；当前城市条件下的估算，产出或其他条件变化时会改变。', math.floor(turns))
    end
end
local function purchase_quote_value(row, kind, yield, formation)
    local definition = GameInfo.Yields['YIELD_'..yield]
    if not definition or not city_cost_index(definition.Index) or type(row.Hash) ~= 'number' then return nil end
    local gold = city_cost_read(city, 'GetGold')
    local value
    if kind == 'Units' then
        local f = MilitaryFormationTypes and MilitaryFormationTypes[formation..'_MILITARY_FORMATION']
        if type(f) ~= 'number' then return nil end
        value = city_cost_read(gold, 'GetPurchaseCost', definition.Index, row.Hash, f)
    else value = city_cost_read(gold, 'GetPurchaseCost', definition.Index, row.Hash) end
    if city_cost_number(value) then return value end
    return nil
end
local function purchase_quote(id, value, yield, available)
    if city_cost_number(value) then
        local currency = yield == 'GOLD' and '金币' or '信仰值'
        add(id..':purchase_cost', currency..'购买价格', '单位：'..currency..'；当前城市的实际购买价格，报价本身不授予购买资格。', value)
    end
    add(id..':purchase_available', '当前购买条件通过', '是否通过当前购买资格；需要选址的物品仍须检查具体位置。false 仅为原版菜单价格预览，没有操作。', available == true)
end
local function plot_purchase_quote(id, plot_id)
    if not city_cost_index(plot_id) then return end
    local cost = city_cost_read(city_cost_read(city, 'GetGold'), 'GetPlotPurchaseCost', plot_id)
    if city_cost_number(cost) then
        add(id..':purchase_cost', '地块购买价格', '单位：金币；当前城市对这个可见购买目标的实际报价。', cost)
    end
end
'''
