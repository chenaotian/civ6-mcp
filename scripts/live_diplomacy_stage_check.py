"""Fixed, read-only diplomacy diagnostics; close the normal MCP client first.

Only fixed stage names and booleans leave the diagnostic. No activity entries,
deal terms, player/session IDs, dialog text, arbitrary error text or actions.
This script never submits an operation or changes a working deal.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.diplomacy_actions import QUERIES, _target, _DEAL_HELPERS
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import envelope, parse_response
from civ6_fair_mcp.transport import FireTunerTransport


STAGES = frozenset({
    'start', 'manager_lookup', 'manager_returned', 'menu_read', 'rules_read',
    'iterating', 'validating_entry', 'entry_validated', 'name_lookup',
    'name_returned', 'projecting', 'query_done', 'unknown_counterpart',
    'known_counterpart', 'session_found', 'phase_found', 'phase_unknown',
    'pending', 'accepted', 'proposed', 'adjusted', 'rejected', 'equalize_failed',
    'inspect', 'closed', 'rejected_permanent', 'demanded',
})
CHECKS = frozenset({'ran', 'self_initiated', 'observed', 'active', 'updated',
                    'native_pending', 'public_action_integer_encoding'})


def emergency_body() -> str:
    body = QUERIES['emergencies'].body({})
    markers = [
        ('local manager=Game.GetEmergencyManager()', "stage='manager_lookup'\nlocal manager=Game.GetEmergencyManager()\nstage='manager_returned'"),
        ('local emergencies=manager:GetEmergencyInfoTable(me)', "stage='menu_read'\nlocal emergencies=manager:GetEmergencyInfoTable(me)"),
        ('local rulesOK,definitions=pcall', "stage='rules_read'\nlocal rulesOK,definitions=pcall"),
        ('local function menu_entry(entry)', "local function menu_entry(entry)\n    stage='validating_entry'"),
        ('    return entry,def', "    stage='entry_validated'\n    return entry,def"),
        ('    for _,entry in ipairs(emergencies) do', "    stage='iterating'\n    for _,entry in ipairs(emergencies) do"),
        ('        local name=label(def.Name)', "        stage='name_lookup'\n        local name=label(def.Name)\n        stage='name_returned'"),
        ('        add(id,name,stage)', "        probe_stage='projecting'\n        add(id,name,stage)"),
    ]
    # The query uses its own local 'stage' for public activity state. Rename
    # diagnostic markers to probe_stage so these scopes cannot shadow each other.
    for old, new in markers:
        if body.count(old) != 1:
            raise ValueError('fixed emergency query changed; review probe')
        new = new.replace("stage='", "probe_stage='").replace('probe_probe_stage=', 'probe_stage=')
        body = body.replace(old, new, 1)
    return '''
local probe_stage='start';local probe_checks={}
out.items=array({});out.supported=false
local ran=pcall(function()
''' + LUA_HELPERS + body + '''
probe_stage='query_done'
end)
probe_checks.ran=ran
-- Check only the exact authored action's numeric encoding, not entry values.
local integer_encoding=true
for _,item in ipairs(out.items or {}) do
    if item.action and item.action.emergency~=nil then
        if type(item.action.emergency)~='number' or not string.match(tostring(item.action.emergency),'^%d+$') then
            integer_encoding=false
        end
    end
end
probe_checks.public_action_integer_encoding=integer_encoding
out.items=nil;out.probe_stage=probe_stage;out.probe_checks=probe_checks
'''


def deal_body(target: int) -> str:
    validate(target, 'id')
    if target > 63:
        raise ValueError('invalid target')
    return '''
local probe_stage='unknown_counterpart';local probe_checks={}
out.items=array({});out.supported=false
local ran=pcall(function()
''' + LUA_HELPERS + _target(target) + _DEAL_HELPERS + '''
probe_stage='known_counterpart'
local sid=session_for(target)
if not sid then return end
probe_stage='session_found'
local info=DiplomacyManager.GetSessionInfo(sid)
probe_checks.self_initiated=info.FromPlayer==me
local phase=deal_phase(target,sid)
if not phase then probe_stage='phase_unknown';return end
probe_stage='phase_found'
probe_checks.observed=phase.observed==true
probe_checks.active=phase.active==true
probe_checks.updated=phase.updated==true
if DealManager and type(DealManager.HasPendingDeal)=='function' then
    local pending=DealManager.HasPendingDeal(me,target)
    if type(pending)=='boolean' then probe_checks.native_pending=pending end
end
for _,name in ipairs({'PENDING','ACCEPTED','PROPOSED','ADJUSTED','REJECTED','EQUALIZE_FAILED','INSPECT','CLOSED','REJECTED_PERMANENT','DEMANDED'}) do
    if proposal_is(phase.action,name) then probe_stage=string.lower(name);break end
end
out.supported=true
end)
probe_checks.ran=ran
out.items=nil;out.probe_stage=probe_stage;out.probe_checks=probe_checks
'''


def build_probe(category: str, target: int | None = None) -> str:
    if category == 'emergencies' and target is None:
        body = emergency_body()
    elif category == 'deal-phase' and target is not None:
        body = deal_body(target)
    else:
        raise ValueError('invalid fixed diagnostic')
    return wrap(body, secrets.token_hex(16))


def project(raw: dict) -> dict:
    envelope(raw)
    stage, checks = raw.get('probe_stage'), raw.get('probe_checks')
    if (type(stage) is not str or stage not in STAGES or type(checks) is not dict
            or checks.keys() - CHECKS or any(type(v) is not bool for v in checks.values())
            or type(raw.get('supported')) is not bool):
        raise ValueError('invalid diagnostic response')
    return {'ok': True, 'stage': stage, 'supported': raw['supported'], 'checks': checks}


async def run(category: str, target: int | None) -> dict:
    script = build_probe(category, target)
    client = FireTunerTransport()
    try:
        return project(parse_response(await client.execute(script)))
    except Exception:
        return {'ok': False, 'error': 'diplomacy_stage_unavailable'}
    finally:
        try:
            await client.close()
        except Exception:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('category', choices=['emergencies', 'deal-phase'])
    parser.add_argument('--target-player', type=int)
    args = parser.parse_args()
    result = asyncio.run(run(args.category, args.target_player))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result['ok'] else 1)
