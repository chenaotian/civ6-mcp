"""Numeric subset of stock TradeSupport.GetYieldsForRoute.

Callers must establish their own route/menu membership before invoking this
helper. It returns totals only: no path, religion, tooltip or city-state data.
"""

TRADE_YIELD_HELPERS = r'''
local function menu_trade_number(value)
    return type(value)=="number" and value==value and value~=math.huge and value~=-math.huge
end
local function menu_trade_yields(manager,origin_owner,origin_id,dest_owner,dest_id,destination,origin_player)
    -- TradeOverview:342-348 calls TradeSupport.GetYieldsForRoute for both
    -- benefits views. TradeSupport:62-146 uses these exact three arrays and
    -- the receiving player's international multiplier (yieldIndex, not +1).
    if not manager or not GameInfo or not GameInfo.Yields then return nil end
    local prefix=destination and "CalculateDestinationYields" or "CalculateOriginYields"
    for _,suffix in ipairs({"FromPotentialRoute","FromPath","FromModifiers"}) do
        if type(manager[prefix..suffix])~="function" then return nil end
    end
    local base=manager[prefix.."FromPotentialRoute"](manager,origin_owner,origin_id,dest_owner,dest_id)
    local path=manager[prefix.."FromPath"](manager,origin_owner,origin_id,dest_owner,dest_id)
    local modifiers=manager[prefix.."FromModifiers"](manager,origin_owner,origin_id,dest_owner,dest_id)
    if type(base)~="table" or type(path)~="table" or type(modifiers)~="table" then return nil end
    local trade=nil
    if dest_owner~=origin_owner then
        local recipient=destination and Players[dest_owner] or origin_player
        if not recipient or type(recipient.GetTrade)~="function" then return nil end
        trade=recipient:GetTrade()
        if not trade or type(trade.GetInternationalYieldModifier)~="function" then return nil end
    end
    local values={}
    for _,name in ipairs({"YIELD_FOOD","YIELD_PRODUCTION","YIELD_GOLD","YIELD_SCIENCE","YIELD_CULTURE","YIELD_FAITH"}) do
        local row=GameInfo.Yields[name]
        if not row or type(row.Index)~="number" or row.Index<0 or row.Index%1~=0 then return nil end
        local index=row.Index+1
        if not menu_trade_number(base[index]) or not menu_trade_number(path[index])
            or not menu_trade_number(modifiers[index]) then return nil end
        local total=base[index]+path[index]+modifiers[index]
        if trade then
            local multiplier=trade:GetInternationalYieldModifier(row.Index)
            if not menu_trade_number(multiplier) then return nil end
            if total>0 and multiplier~=1 then total=total*multiplier end
        end
        if not menu_trade_number(total) then return nil end
        table.insert(values,{name=name,value=total})
    end
    return values
end
'''
