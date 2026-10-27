"""Only fixed phases/booleans escape the standalone read-only diagnostic."""
import pytest
from lupa import LuaRuntime

from scripts.live_diplomacy_stage_check import build_probe, emergency_body, deal_body, project
from test_extension_diplomacy_actions import ENGINE
from test_emergency_menu import SETUP


def run_body(body, setup=''):
    vm = LuaRuntime(unpack_returned_tuples=True)
    out = vm.execute(ENGINE + SETUP + setup + body + '\nreturn out')
    assert out['items'] is None
    raw = {'session': 'diplomacy_probe_tests', 'player_id': 0, 'turn': 122, 'active_turn': True,
           'supported': out['supported'], 'probe_stage': out['probe_stage'],
           'probe_checks': dict(out['probe_checks'].items())}
    return vm, project(raw)


def test_activity_probe_retains_query_guards_but_erases_records():
    vm, out = run_body(emergency_body())
    assert out == {'ok': True, 'stage': 'query_done', 'supported': True,
                   'checks': {'ran': True, 'public_action_integer_encoding': True}}
    assert vm.globals().reads == 0 and len(vm.globals().calls) == 0


@pytest.mark.parametrize('setup,stage', [
    ("Game.GetEmergencyManager=function() error('SECRET') end", 'manager_lookup'),
    ("Game.GetEmergencyManager=function() return {GetEmergencyInfoTable=function() error('SECRET') end} end", 'menu_read'),
    ("Locale.Lookup=function() error('SECRET') end", 'name_lookup'),
])
def test_native_failures_expose_stage_only(setup, stage):
    _, out = run_body(emergency_body(), setup)
    assert out['stage'] == stage and out['checks']['ran'] is False
    assert 'SECRET' not in repr(out)


@pytest.mark.parametrize('category,target', [('emergencies', None), ('deal-phase', 2)])
def test_fixed_diagnostic_lua_compiles(category, target):
    LuaRuntime().compile(build_probe(category, target))


def test_deal_probe_reads_only_bound_role_not_terms():
    setup = "DealManager.GetWorkingDeal=function() error('NO TERMS') end"
    vm, out = run_body(deal_body(1), setup)
    assert out['stage'] == 'proposed'
    assert out['checks'] == {'ran': True, 'self_initiated': False, 'observed': True,
                             'active': True, 'updated': False, 'native_pending': False}
    assert len(vm.globals().calls) == 0


def test_projector_never_returns_metadata_or_arbitrary_error_data():
    raw = {'session': 'diplomacy_probe_tests', 'player_id': 0, 'turn': 122, 'active_turn': True,
           'supported': True, 'probe_stage': 'query_done', 'probe_checks': {'ran': True},
           'items': [{'id': 'not exported'}], 'raw_error': 'not exported'}
    assert set(project(raw)) == {'ok', 'stage', 'supported', 'checks'}
    raw['probe_checks']['unexpected'] = True
    with pytest.raises(ValueError):
        project(raw)
