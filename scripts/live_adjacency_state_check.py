"""One fixed-context read of preview lifecycle booleans; never enters the UI.

Root must close the ordinary client before running this. The fixed expected
city/item are the already public T94 request. This reads no labels, controls,
plots, yields, raw errors, IDs, names, session tokens, or private UI upvalues.
An unknown capability yields null, not false. It cannot reconstruct past event
ordering from a stopped observer and must not be treated as proof of a cause.
"""
from __future__ import annotations

import asyncio
import json

from civ6_fair_mcp.transport import FireTunerTransport

CONTEXT = "DistrictPlotIconManager"
EXPECTED_CITY = 393221
EXPECTED_ITEM = "DISTRICT_CAMPUS"
CHECKS = {
    "observer_exists": "type(s)=='table'",
    "active_exists": "type(s)=='table' and type(s.active)=='table'",
    "published_exists": "type(s)=='table' and type(s.published)=='table'",
    "pending_exists": "type(s)=='table' and type(s.pending)=='table'",
    "arming": "type(s)=='table' and s.arming==true",
    "get_wrapper_intact": "type(s)=='table' and type(s.get_wrapper)=='function' and GetInstanceAt==s.get_wrapper",
    "realize_wrapper_intact": "type(s)=='table' and type(s.realize_wrapper)=='function' and Realize2dArtForCityDistricts==s.realize_wrapper",
    "clear_wrapper_intact": "type(s)=='table' and type(s.clear_wrapper)=='function' and ClearEveything==s.clear_wrapper",
    "active_expected_own_city": "type(s)=='table' and type(s.active)=='table' and s.active.player==me and s.active.city_id==EXPECTED_CITY",
    "active_current_turn": "type(s)=='table' and type(s.active)=='table' and s.active.turn==Game.GetCurrentGameTurn()",
    "active_current_session": "type(s)=='table' and type(s.active)=='table' and ExposedMembers.Civ6FairState.session==s.active.session",
    "mode_selection": "UI.GetInterfaceMode()==InterfaceModeTypes.SELECTION",
    "mode_placement": "UI.GetInterfaceMode()==InterfaceModeTypes.DISTRICT_PLACEMENT",
    "selected_expected_own_city": "selected_matches()",
    "district_parameter_expected": "UI.GetInterfaceModeParameter(CityOperationTypes.PARAM_DISTRICT_TYPE)==GameInfo.Districts.DISTRICT_CAMPUS.Hash",
    "adjacency_layer_on": "UILens.IsLayerOn(UILens.CreateLensLayerHash('Adjacency_Bonus_Districts'))==true",
    "empire_layer_on": "UILens.IsLayerOn(UILens.CreateLensLayerHash('Empire_Details'))==true",
    "selection_intent_exists": "type(s)=='table' and type(s.selection)=='table'",
    "selection_event_seen": "type(s)=='table' and type(s.selection)=='table' and s.selection.seen==true",
    "selection_expected_own_city": "type(s)=='table' and type(s.selection)=='table' and s.selection.player==me and s.selection.city_id==EXPECTED_CITY",
    "observer_v2": "type(s)=='table' and s.version==2",
    "legacy_forwarding_layer": "type(s)=='table' and s.legacy_shim==true",
    "begin_trace_current_turn": "type(s)=='table' and type(s.begin_trace)=='table' and s.begin_trace.player==me and s.begin_trace.turn==Game.GetCurrentGameTurn()",
    "begin_mode_started": "type(s)=='table' and type(s.begin_trace)=='table' and s.begin_trace.mode_started==true",
    "begin_mode_returned": "type(s)=='table' and type(s.begin_trace)=='table' and s.begin_trace.mode_returned==true",
    "begin_close_started": "type(s)=='table' and type(s.begin_trace)=='table' and s.begin_trace.close_started==true",
    "begin_close_returned": "type(s)=='table' and type(s.begin_trace)=='table' and s.begin_trace.close_returned==true",
    "begin_calls_completed": "type(s)=='table' and type(s.begin_trace)=='table' and s.begin_trace.completed==true",
}


def build_probe() -> str:
    checks = '{' + ','.join('{"' + key + '",function() return ' + expression + ' end}'
                            for key, expression in CHECKS.items()) + '}'
    return '''do
local permitted,authorized=pcall(function()
    if GameConfiguration.IsAnyMultiplayer()~=false or GameConfiguration.IsHotseat()~=false
        or GameConfiguration.IsWorldBuilderEditor()~=false or Automation.IsActive()~=false then return false end
    local me=Game.GetLocalPlayer()
    if type(me)~='number' or me%1~=0 or me<0 or Game.GetLocalObserver()~=me then return false end
    local player=Players[me]
    return player~=nil and player:IsAlive()==true and player:IsHuman()==true
end)
local payload='{"ok":false,"error":"preview_state_unavailable"}'
if permitted and authorized==true then
    local ok,id=pcall(function() return ContextPtr:GetID() end)
    if ok and (id=='DistrictPlotIconManager' or id=='DistrictPlotIconManager.xml') then
        local me=Game.GetLocalPlayer()
        local EXPECTED_CITY=''' + str(EXPECTED_CITY) + '''
        local s=_CIV6FAIR_DISTRICT_PREVIEW
        local function selected_matches()
            local city=UI.GetHeadSelectedCity()
            return city~=nil and city:GetOwner()==me and city:GetID()==EXPECTED_CITY
        end
        local fields={}
        for _,check in ipairs(''' + checks + ''') do
            local success,value=pcall(check[2])
            local literal='null'
            if success and type(value)=='boolean' then literal=value and 'true' or 'false' end
            fields[#fields+1]='"'..check[1]..'":'..literal
        end
        payload='{"ok":true,"context_verified":true,"checks":{'..table.concat(fields,',')..'}}'
    end
end
print('CIV6FAIR_JSON:'..payload)
print('---END---')
end'''


def project(response: str) -> dict:
    frames = [line.removeprefix('CIV6FAIR_JSON:') for line in response.splitlines()
              if line.startswith('CIV6FAIR_JSON:')]
    if len(frames) != 1:
        raise ValueError('invalid preview state response')
    raw = json.loads(frames[0])
    if type(raw) is not dict or raw.get('ok') is not True:
        return {'ok': False, 'error': 'preview_state_unavailable'}
    values = raw.get('checks')
    if (raw.get('context_verified') is not True or type(values) is not dict or values.keys() != CHECKS.keys()
            or any(value is not None and type(value) is not bool for value in values.values())):
        raise ValueError('invalid preview state response')
    return {'ok': True, 'context_verified': True, 'checks': values}


async def run() -> dict:
    client = FireTunerTransport()
    try:
        return project(await client.execute(build_probe(), context=CONTEXT))
    except Exception:
        return {'ok': False, 'error': 'preview_state_unavailable'}
    finally:
        try:
            await client.close()
        except Exception:
            pass


if __name__ == '__main__':
    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result['ok'] else 1)
