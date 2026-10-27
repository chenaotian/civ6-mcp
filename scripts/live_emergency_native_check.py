"""Locate failure inside the unchanged native emergency query and JSON encoder.

One fixed ordinary query, no actions. Prints only fixed stages, Lua field types
and per-field encodability booleans; no values, IDs, names, counts or errors.
Close the normal MCP client before root runs this diagnostic.
"""
from __future__ import annotations

import asyncio
import json
import secrets

from civ6_fair_mcp.extensions import build_inspection_query
from civ6_fair_mcp.lua_common import _SUFFIX
from civ6_fair_mcp.policy import MAX_RESPONSE_BYTES, _reject_constant, _unique_object
from civ6_fair_mcp.transport import FireTunerTransport


STAGES = frozenset({'prefix_failed', 'collect_failed', 'ui_discovery_failed',
                    'encoding_failed', 'encoded_ok', 'diagnostic_failed', 'transport_failed'})
TOP = ('ok', 'session', 'player_id', 'turn', 'active_turn', 'category', 'supported',
       'items', 'engine_activity', 'popup_keys', 'turn_blockers')
ITEM = ('scope', 'owner_id', 'id', 'name', 'description', 'value', 'action')
ACTION = ('type', 'emergency', 'choice')
FIELDS = frozenset(TOP) | frozenset('item.' + k for k in ITEM) | frozenset('action.' + k for k in ACTION)
TYPES = frozenset({'nil', 'boolean', 'number', 'string', 'table', 'function', 'userdata', 'thread', 'mixed'})

_DIAGNOSTIC_SUFFIX = r'''
    return out
end)
local final_stage=diagnostic_stage..'_failed'
if diagnostic_stage=='ui' then final_stage='ui_discovery_failed' end
if success then
    -- This is the ORIGINAL serializer and ORIGINAL complete query result.
    local encoded=pcall(encode,result,{},0)
    final_stage=encoded and 'encoded_ok' or 'encoding_failed'
end
local types,encodable={},{}
local function inspect_field(path,value)
    local observed=type(value)
    if types[path]~=nil and types[path]~=observed then types[path]='mixed'
    else types[path]=observed end
    local ok=pcall(encode,value,{},0)
    if encodable[path]==nil then encodable[path]=ok else encodable[path]=encodable[path] and ok end
end
if diagnostic_out then
    for _,key in ipairs({'ok','session','player_id','turn','active_turn','category','supported',
        'items','engine_activity','popup_keys','turn_blockers'}) do
        inspect_field(key,diagnostic_out[key])
    end
    if type(diagnostic_out.items)=='table' then
        for index,item in ipairs(diagnostic_out.items) do
            if index>2048 then break end
            if type(item)=='table' then
                for _,key in ipairs({'scope','owner_id','id','name','description','value','action'}) do
                    inspect_field('item.'..key,item[key])
                end
                if type(item.action)=='table' then
                    for _,key in ipairs({'type','emergency','choice'}) do inspect_field('action.'..key,item.action[key]) end
                end
            end
        end
    end
end
local diagnostic={stage=final_stage,field_types=types,encodable=encodable}
local ok,encoded=pcall(encode,diagnostic,{},0)
if not ok then encoded='{"stage":"diagnostic_failed","field_types":{},"encodable":{}}' end
print('CIV6FAIR_JSON:'..encoded)
print('---END---')
end
'''


def build_probe() -> str:
    script = build_inspection_query(secrets.token_hex(16), 'emergencies', {})
    replacements = [
        ('local success, result = pcall(function()',
         "local diagnostic_stage='prefix';local diagnostic_out=nil\nlocal success, result = pcall(function()"),
        ('out.category="emergencies"', 'diagnostic_out=out\nout.category="emergencies"'),
        ('\nend\ncollect()\n', "\nend\ndiagnostic_stage='collect'\ncollect()\ndiagnostic_stage='ui'\n"),
        (_SUFFIX, _DIAGNOSTIC_SUFFIX),
    ]
    for old, new in replacements:
        if script.count(old) != 1:
            raise ValueError('fixed query/serializer changed; review diagnostic')
        script = script.replace(old, new, 1)
    return script


def project(raw: dict) -> dict:
    if type(raw) is not dict or set(raw) != {'stage', 'field_types', 'encodable'}:
        raise ValueError('invalid diagnostic')
    stage, types, encodable = raw['stage'], raw['field_types'], raw['encodable']
    if (type(stage) is not str or stage not in STAGES or type(types) is not dict
            or type(encodable) is not dict or types.keys() - FIELDS or encodable.keys() - FIELDS
            or any(type(v) is not str or v not in TYPES for v in types.values())
            or any(type(v) is not bool for v in encodable.values())):
        raise ValueError('invalid diagnostic')
    return {'stage': stage, 'field_types': types, 'encodable': encodable}


async def run() -> dict:
    script = build_probe()
    client = FireTunerTransport()
    try:
        text = await client.execute(script)
        if type(text) is not str or len(text.encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise ValueError
        lines = [line[14:] for line in text.split('\n') if line.startswith('CIV6FAIR_JSON:')]
        if len(lines) != 1:
            raise ValueError
        return project(json.loads(lines[0], parse_constant=_reject_constant, object_pairs_hook=_unique_object))
    except Exception:
        return {'stage': 'transport_failed', 'field_types': {}, 'encodable': {}}
    finally:
        try:
            await client.close()
        except Exception:
            pass


if __name__ == '__main__':
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, sort_keys=True))
