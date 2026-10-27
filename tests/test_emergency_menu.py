"""Local-only WorldCrisis menu reads; never expand participant/target details."""
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.diplomacy_actions import QUERIES
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.lua_common import _PREFIX
from civ6_fair_mcp.policy import PolicyError

from test_extension_diplomacy_actions import ENGINE, execute


SETUP = '''
emergencies={{TargetID=9,EmergencyType=7,HasBegun=true,TurnsLeft=29}}
Game.GetEmergencyManager=function()
    return {GetEmergencyInfoTable=function(_,id) assert(id==0);return emergencies end}
end
GameInfo.EmergencyAlliances={[7]={Name='LOC_AID_REQUEST'}}
setmetatable(GameInfo,{__index=function(_,key)
    if key=='Emergencies' then error('nonexistent native GameInfo table') end
end})
Locale.Lookup=function(key) return key=='LOC_AID_REQUEST' and 'Aid request' or key end
'''


def rows(out):
    return {v['id']: v for v in out['items'].values()}


def test_real_local_activity_uses_emergency_alliances_and_public_duration():
    vm, out = execute('emergencies', query=True, setup=SETUP)
    values = rows(out)
    assert out['supported'] is True
    assert values['emergency_0']['name'] == 'Aid request'
    assert values['emergency_0']['value'] == 'in_progress'
    assert values['emergency_0:turns_left']['value'] == 29
    action = dict(values['emergency_0_acknowledge']['action'].items())
    assert action == {'type': 'emergency_respond', 'emergency': 0, 'choice': 'acknowledge'}
    assert vm.globals().reads == 0


@pytest.mark.parametrize('begun,choices', [
    ('false', {'join', 'reject'}), ('true', {'acknowledge'}),
    ('nil', set()), ('0', set()), ('1', set()), ('"false"', set()),
])
def test_buttons_follow_strict_normal_input_required(begun, choices):
    vm, out = execute('emergencies', query=True,
                      setup=SETUP + '\nemergencies[1].HasBegun=' + begun)
    offered = {v['action']['choice'] for v in out['items'].values() if v['action']}
    assert offered == choices and vm.globals().reads == 0
    for choice in ['join', 'reject', 'acknowledge']:
        _, action = execute('emergency_respond', {'emergency': 0, 'choice': choice},
                            setup=SETUP + '\nemergencies[1].HasBegun=' + begun)
        assert action['accepted'] is (choice in choices)


def test_unknown_target_and_participant_details_are_never_read_or_returned():
    setup = SETUP + '''
setmetatable(emergencies[1],{__index=function(_,key)
    error('private/dynamic activity field: '..key)
end})
'''
    vm, out = execute('emergencies', query=True, setup=setup)
    assert vm.globals().reads == 0
    for item in out['items'].values():
        assert item['target_player'] is None and item['x'] is None and item['y'] is None
        if item['action']:
            assert set(dict(item['action'].items())) == {'type', 'emergency', 'choice'}
    vm, result = execute('emergency_respond', {'emergency': 0, 'choice': 'acknowledge'}, setup=setup)
    assert result['accepted'] is True and vm.globals().reads == 0
    params = vm.globals().calls[1][3]
    # The target is only an internal parameter in the normal native request,
    # never present in the public choice object or result.
    assert params[vm.globals().PlayerOperations.PARAM_OTHER_PLAYER] == 9


@pytest.mark.parametrize('turns,stage,shown', [
    ('-1', 'completed', False), ('0', 'in_progress', True),
    ('nil', 'in_progress', False), ('"29"', 'in_progress', False),
])
def test_finished_or_unknown_duration_is_not_exposed_as_negative_turns(turns, stage, shown):
    _, out = execute('emergencies', query=True, setup=SETUP + '\nemergencies[1].TurnsLeft=' + turns)
    values = rows(out)
    assert values['emergency_0']['value'] == stage
    assert ('emergency_0:turns_left' in values) is shown


@pytest.mark.parametrize('mutation', [
    'emergencies[1].TargetID=nil', 'emergencies[1].TargetID=-2',
    'emergencies[1].TargetID=64', 'emergencies[1].EmergencyType=nil',
    'emergencies[1].EmergencyType="7"', 'GameInfo.EmergencyAlliances={}',
])
def test_invalid_or_unknown_rule_entry_is_not_an_action(mutation):
    vm, out = execute('emergencies', query=True, setup=SETUP + '\n' + mutation)
    assert len(out['items']) == 0 and vm.globals().reads == 0
    vm, result = execute('emergency_respond', {'emergency': 0, 'choice': 'acknowledge'},
                         setup=SETUP + '\n' + mutation)
    assert result['accepted'] is False and len(vm.globals().calls) == 0


def test_no_target_competition_keeps_normal_acknowledge():
    vm, out = execute('emergency_respond', {'emergency': 0, 'choice': 'acknowledge'},
                      setup=SETUP + '\nemergencies[1].TargetID=-1')
    assert out['accepted'] is True and vm.globals().reads == 0


def test_missing_rule_table_fails_closed_even_native_proxy_throws():
    _, out = execute('emergencies', query=True, setup=SETUP + '''
GameInfo.EmergencyAlliances=nil
setmetatable(GameInfo,{__index=function() error('table unavailable') end})
''')
    assert out['supported'] is False and len(out['items']) == 0


def test_action_rechecks_current_local_menu_and_state():
    _, out = execute('emergencies', query=True, setup=SETUP)
    action = dict(rows(out)['emergency_0_acknowledge']['action'].items())
    action.pop('type')
    for mutation in ['emergencies={}', 'emergencies[1].HasBegun=false']:
        vm, result = execute('emergency_respond', action, setup=SETUP + '\n' + mutation)
        assert result['accepted'] is False and len(vm.globals().calls) == 0


FLOAT_ITERATOR = '''
local native_ipairs=ipairs
ipairs=function(t)
    local iterator,state,index=native_ipairs(t)
    if t~=emergencies then return iterator,state,index end
    return function(s,i)
        local next_index,value=iterator(s,i)
        if next_index~=nil then return next_index+0.0,value end
    end,state,index
end
'''


def encoded_activity(begun, *, original=False, iterator=FLOAT_ITERATOR):
    # Use the production JSON encoder, not Python coercion of a Lua table.
    # A deliberately injected integral float must still be rejected by the
    # strict Python action schema. This is a regression case, not evidence that
    # the live failure was necessarily fractional encoding rather than -1.
    encoder = _PREFIX.split('local success, result = pcall(function()', 1)[0]
    body = QUERIES['emergencies'].body({})
    if original:
        body = body.replace('local ordinal=0', 'local ordinal=0.0')
    code = (ENGINE + SETUP + '\nemergencies[1].HasBegun=' + begun + '\n' + iterator
            + encoder + LUA_HELPERS + '''
out={ok=true,session='emergency_float_tests',player_id=0,turn=122,active_turn=true,
    category='emergencies',items=array({}),supported=false}
local function collect()
''' + body + '\nend\ncollect()\nreturn encode(out,{},0)\nend')
    return json.loads(LuaRuntime().execute(code))


@pytest.mark.parametrize('begun', ['true', 'false'])
def test_native_float_ordinals_survive_real_json_and_python_projection(begun):
    raw = encoded_activity(begun)
    public = public_inspection(raw, 'emergencies', {})
    actions = [v['action'] for v in public['items'] if 'action' in v]
    assert len(actions) == (1 if begun == 'true' else 2)
    assert all(type(a['emergency']) is int and a['emergency'] == 0 for a in actions)
    assert all(not v['id'].startswith('emergency_0.0') for v in public['items'])


def test_injected_float_ordinal_still_causes_strict_inspection_rejection():
    raw = encoded_activity('true', original=True)
    action = next(v['action'] for v in raw['items'] if 'action' in v)
    assert type(action['emergency']) is float and action['emergency'] == 0.0
    with pytest.raises(PolicyError):
        public_inspection(raw, 'emergencies', {})


def native_key_menu(first_key, second_key):
    return f'''
local original_ipairs=ipairs
local entries={{emergencies[1],{{TargetID=10,EmergencyType=7,HasBegun=true,TurnsLeft=7}}}}
local keys={{{first_key},{second_key}}}
emergencies={{[keys[1]]=entries[1],[keys[2]]=entries[2]}}
ipairs=function(t)
    if t~=emergencies then return original_ipairs(t) end
    local position=0
    return function()
        position=position+1
        if entries[position] then return keys[position],entries[position] end
    end
end
'''


@pytest.mark.parametrize('keys', [('0', '7'), ('0.0', '7.0'), ("'first_native'", "'second_native'")])
def test_public_ordinals_ignore_native_keys_for_json_and_action_selection(keys):
    iterator = native_key_menu(*keys)
    public = public_inspection(encoded_activity('true', iterator=iterator), 'emergencies', {})
    actions = [v['action'] for v in public['items'] if 'action' in v]
    assert [a['emergency'] for a in actions] == [0, 1]
    assert all(type(a['emergency']) is int for a in actions)
    assert [v['id'] for v in public['items'] if 'action' in v] == [
        'emergency_0_acknowledge', 'emergency_1_acknowledge']
    for ordinal, target in [(0, 9), (1, 10)]:
        vm, result = execute('emergency_respond', {'emergency': ordinal, 'choice': 'acknowledge'},
                             setup=SETUP + iterator)
        assert result['accepted'] is True and vm.globals().reads == 0
        params = vm.globals().calls[1][3]
        assert params[vm.globals().PlayerOperations.PARAM_OTHER_PLAYER] == target


def test_action_and_query_skip_same_invalid_native_entry():
    iterator = native_key_menu('0', '7') + '\nemergencies[0].EmergencyType=999\n'
    public = public_inspection(encoded_activity('true', iterator=iterator), 'emergencies', {})
    actions = [v['action'] for v in public['items'] if 'action' in v]
    assert len(actions) == 1 and actions[0]['emergency'] == 0
    vm, result = execute('emergency_respond', {'emergency': 0, 'choice': 'acknowledge'},
                         setup=SETUP + iterator)
    assert result['accepted'] is True
    assert vm.globals().calls[1][3][vm.globals().PlayerOperations.PARAM_OTHER_PLAYER] == 10
