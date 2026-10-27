"""Fixed, read-only empire diagnostics. No gameplay requests or UI callbacks.

Reads named enum availability, public rule-field types, and own player APIs.
It intentionally cannot found a city or arrange a test state.
"""
import asyncio
import json
from pathlib import Path

from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import parse_response
from civ6_fair_mcp.transport import FireTunerTransport


BODY = r'''
out.enum_checks=array({})
local enum_sets={
    PlayerOperations={'APPOINT_GOVERNOR','PROMOTE_GOVERNOR','ASSIGN_GOVERNOR',
        'RECRUIT_GREAT_PERSON','REJECT_GREAT_PERSON','PATRONIZE_GREAT_PERSON',
        'UNLOCK_POLICIES','COMMEMORATE','FOUND_PANTHEON','ADD_BELIEF','FOUND_RELIGION',
        'PARAM_GOVERNOR_TYPE','PARAM_GOVERNOR_PROMOTION_TYPE','PARAM_PLAYER_ONE','PARAM_CITY_DEST',
        'PARAM_GREAT_PERSON_INDIVIDUAL_TYPE','PARAM_YIELD_TYPE','PARAM_COMMEMORATION_TYPE',
        'PARAM_BELIEF_TYPE','PARAM_INSERT_MODE','VALUE_EXCLUSIVE','PARAM_RELIGION_TYPE','PARAM_RELIGION_CUSTOM_NAME'},
    CityOperationTypes={'BUILD','PARAM_UNIT_TYPE','PARAM_BUILDING_TYPE','PARAM_DISTRICT_TYPE','PARAM_PROJECT_TYPE',
        'PARAM_X','PARAM_Y','PARAM_INSERT_MODE','VALUE_APPEND','VALUE_EXCLUSIVE','VALUE_REMOVE_AT','VALUE_MOVE_TO',
        'MILITARY_FORMATION_TYPE','PARAM_QUEUE_LOCATION','PARAM_QUEUE_SOURCE_LOCATION','PARAM_QUEUE_DESTINATION_LOCATION'},
    CityCommandTypes={'PURCHASE','MANAGE','SWAP_TILE_OWNER','SET_FOCUS','NAME_CITY','DESTROY',
        'PARAM_UNIT_TYPE','PARAM_BUILDING_TYPE','PARAM_DISTRICT_TYPE','PARAM_YIELD_TYPE',
        'PARAM_MILITARY_FORMATION_TYPE','PARAM_X','PARAM_Y','PARAM_PLOT_PURCHASE','PARAM_MANAGE_CITIZEN',
        'PARAM_SWAP_TILE_OWNER','PARAM_FLAGS','PARAM_DATA0','PARAM_NAME'},
    CityCommandResults={'PLOTS','CITIZENS','MAX_CITIZENS','LOCKED_CITIZENS'},
    CityOperationResults={'CAN_TRAIN_CORPS','CAN_TRAIN_ARMY'},
    MilitaryFormationTypes={'STANDARD_MILITARY_FORMATION','CORPS_MILITARY_FORMATION','ARMY_MILITARY_FORMATION'},
    YieldTypes={'GOLD','FAITH'},CityDestroyDirectives={'KEEP','REJECT'},
    UnitOperationTypes={'PARAM_FLAGS'},GlobalParameters={'GOVERNMENT_UNLOCK_WITH_FAITH'}}
local namespaces={PlayerOperations=PlayerOperations,CityOperationTypes=CityOperationTypes,
    CityCommandTypes=CityCommandTypes,CityCommandResults=CityCommandResults,
    CityOperationResults=CityOperationResults,
    MilitaryFormationTypes=MilitaryFormationTypes,YieldTypes=YieldTypes,
    CityDestroyDirectives=CityDestroyDirectives,UnitOperationTypes=UnitOperationTypes,
    GlobalParameters=GlobalParameters}
for name,keys in pairs(enum_sets) do
    for _,key in ipairs(keys) do
        local value=namespaces[name] and namespaces[name][key]
        local kind=type(value)
        table.insert(out.enum_checks,{namespace=name,key=key,kind=kind,
            value=(kind=='number' or kind=='boolean' or kind=='string') and value or nil})
    end
end
out.rule_fields=array({})
local fields={Units={'MustPurchase','RequiresPlacement','InternalOnly'},
    Buildings={'MustPurchase','RequiresPlacement','InternalOnly','IsWonder'},
    Districts={'MustPurchase','RequiresPlacement','InternalOnly'},Projects={'MustPurchase','RequiresPlacement','InternalOnly'},
    Religions={'Pantheon','RequiresCustomName'},GovernorsCannotAssign={'CannotAssign'}}
for tab,keys in pairs(fields) do
    if GameInfo[tab] then
        for _,key in ipairs(keys) do
            local variants={}
            for row in GameInfo[tab]() do
                local value=row[key]
                local encoded=type(value)..':'..tostring(value)
                variants[encoded]=(variants[encoded] or 0)+1
            end
            table.insert(out.rule_fields,{table=tab,key=key,variants=variants})
        end
    end
end
out.methods=array({})
local sets={
    {name='culture',object=player:GetCulture(),keys={'CanChangeGovernmentAtAll','GovernmentChangeMade',
        'CivicCompletedThisTurn','PolicyChangeMade','GetCostToUnlockPolicies','GetNumPolicySlots','GetSlotType','GetSlotPolicy'}},
    {name='governors',object=player:GetGovernors(),keys={'HasGovernor','CanEverAppointGovernor','CanAppoint',
        'CanEarnPromotion','CanAssignGovernor','GetGovernor','GetGovernorPoints','GetGovernorPointsSpent'}},
    {name='religion',object=player:GetReligion(),keys={'CanCreatePantheon','GetNumBeliefsEarned',
        'GetReligionTypeCreated','HasReligiousFoundingUnit','GetPantheon'}},
    {name='city_manager',object=CityManager,keys={'CanStartOperation','CanStartCommand','GetCommandTargets'}}}
for _,set in ipairs(sets) do
    for _,key in ipairs(set.keys) do
        table.insert(out.methods,{object=set.name,key=key,kind=type(set.object and set.object[key])})
    end
end
out.city_count=0
for _,city in player:GetCities():Members() do
    if city:GetOwner()==me then out.city_count=out.city_count+1 end
end
out.interface_parameters=array({})
for _,key in ipairs({'PARAM_PLOT_PURCHASE','PARAM_MANAGE_CITIZEN','PARAM_SWAP_TILE_OWNER'}) do
    local value=UI.GetInterfaceModeParameter(CityCommandTypes[key])
    table.insert(out.interface_parameters,{key=key,kind=type(value),value=value})
end
'''


async def run():
    transport = FireTunerTransport()
    try:
        result = parse_response(await transport.execute(wrap(BODY, 'empire_read_audit')))
        result.pop('session', None)
        path = Path(__file__).resolve().parents[1] / 'artifacts' / 'live-empire-api-check.json'
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'ok': result.get('ok'), 'turn': result.get('turn'),
            'city_count': result.get('city_count'), 'enum_checks': len(result.get('enum_checks', [])),
            'missing_constants': [row for row in result.get('enum_checks', []) if row['kind'] != 'number'],
            'method_checks': len(result.get('methods', [])),
            'missing_methods': [row for row in result.get('methods', []) if row['kind'] != 'function'],
            'interface_parameters': result.get('interface_parameters'), 'artifact': str(path)},
            ensure_ascii=False, indent=2))
    finally:
        await transport.close()


if __name__ == '__main__':
    asyncio.run(run())
