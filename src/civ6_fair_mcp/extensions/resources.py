"""Own resource balances from stock TopPanel/ReportScreen/GlobalResourcePopup.

GS TopPanel_Expansion2.lua:43-104 supplies the amount, stockpile/reservation,
income and demand fields. Base TopPanel.lua:318-320 supplies amount only.
PlotTooltip_Expansion2.lua:167 establishes IsResourceVisible(Hash) as the
player's resource-unlock gate. No map, city or foreign source enumeration.
"""
from .base import QuerySpec, lua


_FIELDS = (
    ("stockpile_cap", "GetResourceStockpileCap", "库存上限", True),
    ("reserved", "GetReservedResourceAmount", "已预留数量", True),
    ("accumulation_per_turn", "GetResourceAccumulationPerTurn", "每回合采集量", False),
    ("import_per_turn", "GetResourceImportPerTurn", "每回合城邦输入量", False),
    ("bonus_per_turn", "GetBonusResourcePerTurn", "每回合其他奖励量", False),
    ("unit_demand_per_turn", "GetUnitResourceDemandPerTurn", "每回合单位需求量", True),
    ("power_demand_per_turn", "GetPowerResourceDemandPerTurn", "每回合发电需求量", True),
)


def own_resources(_a: dict) -> str:
    return r'''
out.supported=false
local function read(object,method,...)
    if type(object)~="table" and type(object)~="userdata" then return nil end
    local found,fn=pcall(function() return object[method] end)
    if not found or type(fn)~="function" then return nil end
    -- Civ VI's shipped UI uses global unpack; newer Lua test runtimes expose
    -- table.unpack. Forward varargs directly so neither API is required.
    local ok,value=pcall(fn,object,...)
    if ok then return value end
end
local function finite(value)
    return type(value)=="number" and value==value and math.abs(value)<1e12
end
local function localized(key)
    if type(key)~="string" or key=="" or not Locale or type(Locale.Lookup)~="function" then return nil end
    local ok,value=pcall(Locale.Lookup,key)
    if ok and type(value)=="string" and value~="" and #value<=1024 and not value:find("%z")
        and not (value==key and value:match("^LOC_")) then return value end
end
local resources=read(player,"GetResources")
if not resources or not GameInfo or not GameInfo.Resources then return end
local ready,has_gate=pcall(function() return type(resources.IsResourceVisible)=="function" end)
if not ready or not has_gate then return end
local gs=false
if GameConfiguration and type(GameConfiguration.GetValue)=="function" then
    local ok,rules=pcall(GameConfiguration.GetValue,"RULESET")
    gs=ok and rules=="RULESET_EXPANSION_2"
end
local records,seen={},{}
local function append(id,name,value,description)
    if #records>=2048 then error("unavailable") end
    records[#records+1]={id=id,name=name,value=value,description=description,scope="self",owner_id=me}
end
local function collect()
    local checked=0
    for row in GameInfo.Resources() do
        checked=checked+1
        if checked>1024 then error("unavailable") end
        if row.ResourceClassType=="RESOURCECLASS_STRATEGIC" then
            local hash=row.Hash
            if finite(hash) and hash%1==0 and hash>=-2147483648 and hash<=4294967295 then
                -- Unlock before reading the resource identifier/name or any
                -- amount. A failed gate cannot expose a partially read row.
                local ok,visible=pcall(resources.IsResourceVisible,resources,hash)
                if not ok or type(visible)~="boolean" then error("unavailable") end
                if visible then
                    local id=row.ResourceType
                    if type(id)=="string" and #id<=128 and id:match("^RESOURCE_[A-Z0-9_]+$") then
                        if seen[id] then error("unavailable") end
                        seen[id]=true
                        local name=localized(row.Name) or id
                        local values={}
                        local function field(key,method,label,nonnegative)
                            local value=read(resources,method,id)
                            if finite(value) and (not nonnegative or value>=0) then
                                values[key]=value
                                append(id..":"..key,name,value,label)
                            end
                        end
                        append(id,name,id)
''' + f'''
                        field("amount","GetResourceAmount",{lua("可用数量（风云变幻：当前可用库存）")},true)
                        if gs then
''' + "".join(
        f"                            field({lua(key)},{lua(method)},{lua(label)},{lua(nonnegative)})\n"
        for key, method, label, nonnegative in _FIELDS
    ) + f'''
                            local function derived(key,value,label)
                                if finite(value) then values[key]=value;append(id..":"..key,name,value,label) end
                            end
                            if values.amount~=nil and values.reserved~=nil and values.stockpile_cap~=nil then
                                derived("stockpile_total",math.min(values.amount+values.reserved,values.stockpile_cap),
                                    {lua("原版顶部栏库存合计（可用数量加预留，上限封顶）")})
                            end
                            if values.accumulation_per_turn~=nil and values.import_per_turn~=nil and values.bonus_per_turn~=nil then
                                derived("income_per_turn",values.accumulation_per_turn+values.import_per_turn+values.bonus_per_turn,
                                    {lua("每回合收入合计（采集加城邦输入加其他奖励）")})
                            end
                            if values.unit_demand_per_turn~=nil and values.power_demand_per_turn~=nil then
                                derived("demand_per_turn",values.unit_demand_per_turn+values.power_demand_per_turn,
                                    {lua("每回合需求合计（单位加发电）")})
                            end
                            if values.income_per_turn~=nil and values.demand_per_turn~=nil then
                                derived("net_per_turn",values.income_per_turn-values.demand_per_turn,
                                    {lua("每回合收入减需求；未计库存上限或短缺，不保证下回合实际库存变化")})
                            end
                        end
                    end
                end
            end
        end
    end
end
-- Structural/gate failures clear the query, without exposing errors, row
-- counts or the point at which a hidden definition could not be checked.
if not pcall(collect) then return end
out.supported=true
for _,record in ipairs(records) do add_item(record) end
'''


def own_luxuries(_a: dict) -> str:
    """The stock GlobalResourcePopup's local-player inventory, luxury class only."""
    return r'''
out.supported=false
local function finite(value)
    return type(value)=="number" and value==value and math.abs(value)<1e12
end
local records,seen,indices={},{},{}
local function collect()
    if not player or type(player.GetResources)~="function" or not GameInfo or not GameInfo.Resources then return end
    local resources=player:GetResources()
    if not resources or type(resources.GetResourceAmount)~="function" then return end
    local checked=0
    for row in GameInfo.Resources() do
        checked=checked+1
        if checked>1024 then error("unavailable") end
        if row.ResourceClassType=="RESOURCECLASS_LUXURY" then
            local index=row.Index
            if not finite(index) or index%1~=0 or index<0 or index>2147483647 or indices[index] then error("unavailable") end
            indices[index]=true
            -- Stock GlobalResourcePopup.lua:118-129 enumerates the local
            -- inventory by Index, including Frequency=0 Great Merchant goods.
            -- No map-reveal gate or tradeability test is applied to this own
            -- positive balance. Strategic rows are never queried here.
            local amount=resources:GetResourceAmount(index)
            if not finite(amount) or amount%1~=0 then error("unavailable") end
            if amount>0 then
                local id=row.ResourceType
                if type(id)~="string" or #id>128 or not id:match("^RESOURCE_[A-Z0-9_]+$") or seen[id] then error("unavailable") end
                seen[id]=true
                local name=id
                if type(row.Name)=="string" and Locale and type(Locale.Lookup)=="function" then
                    local ok,value=pcall(Locale.Lookup,row.Name)
                    if ok and type(value)=="string" and value~="" and #value<=1024 and not value:find("%z")
                        and not (value==row.Name and value:match("^LOC_")) then name=value end
                end
                records[#records+1]={id=id,name=name,value=id,scope="self",owner_id=me}
                records[#records+1]={id=id..":amount",name=name,value=math.floor(amount),
                    description=''' + lua("原版资源总览的本方持有份数；不是对特定文明可交易的上限，不包括来源或地块信息") + r''',
                    scope="self",owner_id=me}
            end
        end
    end
    return true
end
-- Unknown quantities cannot be silently treated as absent holdings. Commit
-- only the complete, bounded inventory, without partial rows or error text.
local ok,complete=pcall(collect)
if not ok or complete~=true then return end
out.supported=true
for _,record in ipairs(records) do add_item(record) end
'''


ACTIONS = {}
QUERIES = {
    "own_resources": QuerySpec({}, own_resources,
        "Own unlocked strategic resources only. IDs RESOURCE_*:<field> expose amount, "
        "and verified Gathering Storm stockpile/income/demand fields. Missing values are unknown, "
        "not zero. net_per_turn is income minus demand before caps/shortages. "
        "No foreign sources, resource locations or locked resource names."),
    "own_luxuries": QuerySpec({}, own_luxuries,
        "Own positive luxury-resource holdings from the stock resource overview, including Great Merchant goods. "
        "RESOURCE_*:amount is held copies, not a trade offer limit or a source breakdown. "
        "No player/resource selectors, foreign holdings, map locations or strategic-resource reads. "
        "Unavailable core amounts fail closed; missing names fall back to the resource ID."),
}
