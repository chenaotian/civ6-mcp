import json

import pytest

from scripts.live_emergency_pipeline_check import decode_and_project, safe_result
from test_emergency_menu import encoded_activity


def wire(raw):
    return 'CIV6FAIR_JSON:' + json.dumps(raw) + '\n---END---\n'


@pytest.mark.parametrize('original,stage,number_type', [
    (True, 'inspection_failed', 'float'), (False, 'inspection_passed', 'int'),
])
def test_full_production_pipeline_identifies_ordinal_encoding(original, stage, number_type):
    raw = encoded_activity('true', original=original)
    result, _, _ = decode_and_project(wire(raw))
    assert result['stage'] == stage
    assert result['field_types']['action.emergency'] == number_type
    assert 'Aid request' not in json.dumps(result)
    assert 'emergency_0' not in json.dumps(result)
    assert set(result) == {'stage', 'field_types'}


@pytest.mark.parametrize('field,value', [('player_id', 0.0), ('turn', 122.0), ('active_turn', 1)])
def test_strict_envelope_failure_has_only_schema_types(field, value):
    raw = encoded_activity('true')
    raw[field] = value
    result, r, p = decode_and_project(wire(raw))
    assert result['stage'] == 'envelope_failed' and r is None and p is None
    assert result['field_types'][field] in {'float', 'int'}


def test_native_exception_text_is_never_returned():
    result, _, _ = decode_and_project(wire({'ok': False, 'error': 'secret native text'}))
    assert result['stage'] == 'native_query_failed'
    assert 'secret' not in json.dumps(result)


def test_invalid_wire_and_injected_field_paths_fail_closed():
    result, _, _ = decode_and_project('not json SECRET')
    assert result == {'stage': 'json_failed', 'field_types': {}}
    with pytest.raises(ValueError):
        safe_result('complete', {'arbitrary label': 'int'})
