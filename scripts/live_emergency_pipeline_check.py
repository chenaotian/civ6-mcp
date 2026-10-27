"""Run the exact emergency read pipeline, printing only stages/schema types.

Close the ordinary MCP client before running. This does not submit an action.
Python keeps the ordinary transport response in memory and does not print or
save it. Script output excludes values, identifiers, names, entry counts and
error text; the query uses the unchanged ordinary game transport protocol.
"""
from __future__ import annotations

import asyncio
import json
import secrets

from civ6_fair_mcp.extensions import build_inspection_query
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import (MAX_RESPONSE_BYTES, _reject_constant,
                                _unique_object, parse_response)
from civ6_fair_mcp.service import FairGameService
from civ6_fair_mcp.transport import FireTunerTransport


STAGES = frozenset({'transport_failed', 'json_failed', 'native_query_failed',
                    'envelope_failed', 'inspection_failed', 'inspection_passed',
                    'ui_finish_failed', 'complete'})
TYPES = frozenset({'missing', 'null', 'bool', 'int', 'float', 'str', 'list',
                   'dict', 'other', 'mixed'})
TOP_FIELDS = ('session', 'player_id', 'turn', 'active_turn', 'category', 'supported',
              'items', 'popup_keys', 'turn_blockers', 'engine_activity')
RECORD_FIELDS = ('scope', 'owner_id', 'id', 'name', 'description', 'value', 'action')
ACTION_FIELDS = ('type', 'emergency', 'choice')
FIELDS = frozenset(TOP_FIELDS) | frozenset('item.' + k for k in RECORD_FIELDS) | frozenset(
    'action.' + k for k in ACTION_FIELDS)
MISSING = object()


def kind(value) -> str:
    if value is MISSING:
        return 'missing'
    if value is None:
        return 'null'
    return {bool: 'bool', int: 'int', float: 'float', str: 'str', list: 'list',
            dict: 'dict'}.get(type(value), 'other')


def field_types(raw: dict) -> dict[str, str]:
    # Fixed field paths only. Do not include record IDs/indices, extra keys or
    # observed counts; aggregation reports only a type or the fixed word mixed.
    result = {k: kind(raw.get(k, MISSING)) for k in TOP_FIELDS}

    def add(key, value):
        observed = kind(value)
        previous = result.get(key)
        result[key] = observed if previous is None or previous == observed else 'mixed'

    records = raw.get('items')
    if type(records) is list:
        for record in records[:2048]:
            if type(record) is not dict:
                continue
            for key in RECORD_FIELDS:
                add('item.' + key, record.get(key, MISSING))
            action = record.get('action')
            if type(action) is dict:
                for key in ACTION_FIELDS:
                    add('action.' + key, action.get(key, MISSING))
    return result


def safe_result(stage: str, types: dict[str, str]) -> dict:
    if (stage not in STAGES or type(types) is not dict or types.keys() - FIELDS
            or any(type(v) is not str or v not in TYPES for v in types.values())):
        raise ValueError('invalid fixed diagnostic')
    return {'stage': stage, 'field_types': types}


def decode_and_project(text: str):
    # A separate bounded decode is used only to diagnose which strict envelope
    # field failed. The production parser/projector still decide pass/fail.
    try:
        if type(text) is not str or len(text.encode('utf-8')) > MAX_RESPONSE_BYTES:
            raise ValueError
        lines = [s[len('CIV6FAIR_JSON:'):] for s in text.split('\n') if s.startswith('CIV6FAIR_JSON:')]
        if len(lines) != 1:
            raise ValueError
        decoded = json.loads(lines[0], parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        if type(decoded) is not dict:
            raise ValueError
    except Exception:
        return safe_result('json_failed', {}), None, None
    types = field_types(decoded)
    if decoded.get('ok') is not True:
        return safe_result('native_query_failed', types), None, None
    try:
        raw = parse_response(text)
    except Exception:
        return safe_result('envelope_failed', types), None, None
    try:
        public = public_inspection(raw, 'emergencies', {})
    except Exception:
        return safe_result('inspection_failed', types), None, None
    return safe_result('inspection_passed', types), raw, public


async def run() -> dict:
    script = build_inspection_query(secrets.token_hex(16), 'emergencies', {})
    client = FireTunerTransport()
    try:
        try:
            response = await client.execute(script)
        except Exception:
            return safe_result('transport_failed', {})
        diagnostic, raw, public = decode_and_project(response)
        if raw is None:
            return diagnostic
        # Match the normal read's UI completion using the same connection. Any
        # observation token or public UI result remains internal and is dropped.
        try:
            service = FairGameService(client)
            await service._finish_read(raw, public)
        except Exception:
            return safe_result('ui_finish_failed', diagnostic['field_types'])
        return safe_result('complete', diagnostic['field_types'])
    finally:
        try:
            await client.close()
        except Exception:
            pass


if __name__ == '__main__':
    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0)
