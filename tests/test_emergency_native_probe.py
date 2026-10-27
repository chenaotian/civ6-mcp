import pytest
from lupa import LuaRuntime

from scripts.live_emergency_native_check import build_probe, project
from test_actions import engine
from test_emergency_menu import SETUP

SETUP = 'Locale={}\n' + SETUP


def test_native_probe_preserves_complete_query_and_serializer(engine):
    vm, run = engine
    vm.execute(SETUP)
    result = project(run(build_probe()))
    assert result['stage'] == 'encoded_ok'
    assert result['encodable']['items'] is True
    assert result['field_types']['item.name'] == 'string'
    assert result['field_types']['action.emergency'] == 'number'
    assert len(vm.globals().calls) == 0


def test_collect_exception_is_distinguished_without_error_text(engine):
    vm, run = engine
    vm.execute(SETUP + "\nGame.GetEmergencyManager=function() error('SECRET_NATIVE') end")
    result = project(run(build_probe()))
    assert result['stage'] == 'collect_failed'
    assert 'SECRET' not in repr(result)


def test_unsupported_output_value_is_identified_without_returning_it(engine):
    vm, run = engine
    vm.execute(SETUP)
    script = build_probe().replace("diagnostic_stage='ui'", "out.items[1].description=function() return 'SECRET_VALUE' end\ndiagnostic_stage='ui'", 1)
    result = project(run(script))
    assert result['stage'] == 'encoding_failed'
    assert result['encodable']['items'] is False
    assert result['encodable']['item.description'] is False
    assert result['field_types']['item.description'] in {'function', 'mixed'}
    assert 'SECRET' not in repr(result)


def test_prefix_rejection_does_not_collect_any_fields(engine):
    vm, run = engine
    vm.execute('controls.player=-1')
    result = project(run(build_probe()))
    assert result == {'stage': 'prefix_failed', 'field_types': {}, 'encodable': {}}


def test_script_compiles_and_output_whitelist_rejects_arbitrary_field():
    LuaRuntime().compile(build_probe())
    with pytest.raises(ValueError):
        project({'stage': 'encoded_ok', 'field_types': {'SECRET_FIELD': 'string'}, 'encodable': {}})
