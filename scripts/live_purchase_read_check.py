"""Read-only SCOUT/SLINGER gold-purchase diagnostics for the current own capital.

No RequestCommand, RequestOperation, act, UI selection, or clicks are performed.
The caller must own the game's sole diagnostic connection before running this.
Source: Base/Assets/UI/Panels/ProductionPanel.lua:423,1574,1631-1695.
"""
import asyncio
import json
from pathlib import Path

from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import parse_response
from civ6_fair_mcp.transport import FireTunerTransport


BODY = r'''
local city, first_city
for _,candidate in player:GetCities():Members() do
    if candidate:GetOwner()==me then
        first_city=first_city or candidate
        if candidate:IsCapital() then city=candidate;break end
    end
end
city=city or first_city
if not city or city:GetOwner()~=me then out.available=false;return out end
out.available=true
out.city={owner_id=me,id=city:GetID(),name=Locale.Lookup(city:GetName()),x=city:GetX(),y=city:GetY()}
local treasury=player:GetTreasury()
local city_gold=city:GetGold()
local queue=city:GetBuildQueue()
local gold=GameInfo.Yields['YIELD_GOLD']
local standard=MilitaryFormationTypes.STANDARD_MILITARY_FORMATION
out.gold=treasury:GetGoldBalance()
out.constants={yield_gold_index=gold.Index,yield_gold_enum=YieldTypes.GOLD,
    standard_formation=standard,purchase_command=CityCommandTypes.PURCHASE}

local function capture(fn,...)
    if type(fn)~='function' then return {ok=false,kind='missing'} end
    local ok,value=pcall(fn,...)
    if not ok then return {ok=false,kind='failed'} end
    local kind=type(value)
    local result={ok=true,kind=kind}
    if kind=='number' or kind=='boolean' or kind=='string' then result.value=value end
    return result
end
local function check(row,explicit_formation,exclusion,return_results)
    local params={[CityCommandTypes.PARAM_UNIT_TYPE]=row.Hash,
        [CityCommandTypes.PARAM_YIELD_TYPE]=gold.Index}
    if explicit_formation then params[CityCommandTypes.PARAM_MILITARY_FORMATION_TYPE]=standard end
    local ok,can,results=pcall(CityManager.CanStartCommand,city,CityCommandTypes.PURCHASE,
        exclusion,params,return_results)
    local result={ok=ok,kind=ok and type(can) or 'failed'}
    if ok and type(can)=='boolean' then result.can=can end
    -- Read only the same failure strings displayed by ComposeFailureReasonStrings,
    -- for these two fixed early-game units in our own city. Never forward the
    -- rest of the engine result table or a raw Lua exception.
    if ok and can==false and type(results)=='table' then
        local reasons=results[CityCommandResults.FAILURE_REASONS]
        if type(reasons)=='table' then
            result.failure_reasons=array({})
            for _,reason in ipairs(reasons) do
                if type(reason)=='string' and #reason<=2048 and #result.failure_reasons<32 then
                    table.insert(result.failure_reasons,Locale.Lookup(reason))
                end
            end
        end
    end
    return result
end
out.own_units_on_city_tile=array({})
for _,unit in player:GetUnits():Members() do
    if unit:GetOwner()==me and unit:GetX()==city:GetX() and unit:GetY()==city:GetY() then
        local definition=GameInfo.Units[unit:GetUnitType()]
        table.insert(out.own_units_on_city_tile,{id=unit:GetID(),type=definition and definition.UnitType or 'UNKNOWN'})
    end
end
out.units=array({})
for _,identifier in ipairs({'UNIT_SCOUT','UNIT_SLINGER'}) do
    local row=GameInfo.Units[identifier]
    if row then
        local entry={unit=identifier,index=row.Index,hash=row.Hash,
            static_production_cost=row.Cost,purchase_yield=row.PurchaseYield,
            gold_purchase_cost=capture(city_gold.GetPurchaseCost,city_gold,gold.Index,row.Hash,standard),
            normal_production_cost=capture(queue.GetUnitCost,queue,row.Index),
            can_afford_ui_default=capture(treasury.CanAfford,treasury,city:GetID(),row.Hash),
            can_afford_explicit_standard=capture(treasury.CanAfford,treasury,city:GetID(),row.Hash,standard),
            ui_display_check=check(row,false,true,false),
            ui_execution_check=check(row,false,false,true),
            explicit_standard_display_check=check(row,true,true,false),
            explicit_standard_execution_check=check(row,true,false,true)}
        table.insert(out.units,entry)
    end
end
'''


async def run():
    transport=FireTunerTransport()
    try:
        result=parse_response(await transport.execute(wrap(BODY,'purchase_read_audit')))
        result.pop('session',None)
        path=Path(__file__).resolve().parents[1]/'artifacts'/'live-purchase-read-check.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
        print(str(path))
    finally:
        await transport.close()


if __name__=='__main__':
    asyncio.run(run())
