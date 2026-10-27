"""Own governor reminder acknowledgment follows the stock explicit-close path."""

import pytest

from civ6_fair_mcp.inspection_policy import public_inspection
from test_extension_empire import engine


def rows(result):
    return {row['id']: row for row in result['items'].values()}


@pytest.mark.parametrize('considered', [False, True])
def test_query_reports_only_real_boolean_and_offers_unconfirmed_state(engine, considered):
    vm, run = engine
    vm.globals().controls.considered = considered
    result = run('governors', {}, True)
    items = rows(result)
    assert items['title_considered']['value'] is considered
    assert items['title_considered']['scope'] == 'self'
    assert items['title_considered']['owner_id'] == 0
    assert ('governor_defer' in items) is (not considered)
    assert len(vm.globals().calls) == 0
    if not considered:
        offer = items['governor_defer']
        assert offer['name'] == '确认已查看总督选择'
        assert '原版总督面板' in offer['description']
        assert offer['action']['type'] == 'governor_defer'


@pytest.mark.parametrize('mutation', [
    'governors.HasTitleBeenConsidered=nil',
    'governors.HasTitleBeenConsidered=0',
    "governors.HasTitleBeenConsidered=function() error('unavailable') end",
    'controls.considered=nil',
    'controls.considered=0',
    'controls.considered=1',
    "controls.considered='false'",
    'controls.considered={}',
])
def test_unknown_consideration_omits_only_optional_state_and_never_submits(engine, mutation):
    vm, run = engine
    vm.execute(mutation)
    result = run('governors', {}, True)
    items = rows(result)
    assert result['supported'] is True
    assert items['titles']['value'] == 2
    assert 'title_considered' not in items and 'governor_defer' not in items
    assert not run('governor_defer', {})['accepted']
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize('setter', ['nil', '0'])
def test_unavailable_setter_keeps_readable_state_but_omits_action(engine, setter):
    vm, run = engine
    vm.execute('governors.SetTitleConsidered=' + setter)
    items = rows(run('governors', {}, True))
    assert items['title_considered']['value'] is False
    assert 'governor_defer' not in items
    assert not run('governor_defer', {})['accepted']
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize('mutation', [
    'controls.considered=true',
    'controls.considered=nil',
    'controls.considered=0',
    'governors.HasTitleBeenConsidered=nil',
    "governors.HasTitleBeenConsidered=function() error('unavailable') end",
    'governors.SetTitleConsidered=nil',
    'controls.strategic=false',
])
def test_action_rechecks_when_previous_offer_becomes_stale(engine, mutation):
    vm, run = engine
    assert 'governor_defer' in rows(run('governors', {}, True))
    vm.execute(mutation)
    assert not run('governor_defer', {})['accepted']
    assert len(vm.globals().calls) == 0


def test_confirmation_works_with_no_titles_and_changes_only_own_considered_flag(engine):
    vm, run = engine
    vm.execute('''
governors.GetGovernorPoints=function() return 1 end
governors.GetGovernorPointsSpent=function() return 1 end
governors.SetTitleConsidered=function(self,value)
    assert(self==governors and value==true)
    controls.considered=value
    record(32,{value=value})
end
Players[1]=setmetatable({}, {__index=function() error('foreign read') end})
UI.RequestPlayerOperation=function() error('no assignment request allowed') end
''')
    items = rows(run('governors', {}, True))
    assert items['titles']['value'] == 0 and 'governor_defer' in items
    assert run('governor_defer', {})['accepted'] is True
    items = rows(run('governors', {}, True))
    assert items['title_considered']['value'] is True
    assert 'governor_defer' not in items and items['titles']['value'] == 0
    assert len(vm.globals().calls) == 1 and vm.globals().calls[1]['op'] == 32
    assert vm.globals().controls.foreign_reads == 0


def test_public_projection_preserves_false_state_and_fixed_action(engine):
    _, run = engine
    items = rows(run('governors', {}, True))
    records = []
    for key in ('title_considered', 'governor_defer'):
        row = dict(items[key])
        if 'action' in row:
            row['action'] = dict(row['action'])
        records.append(row)
    result = public_inspection({
        'ok': True, 'session': 'test-governor-consideration', 'player_id': 0,
        'turn': 111, 'active_turn': True, 'category': 'governors',
        'supported': True, 'items': records,
    }, 'governors')
    public = {row['id']: row for row in result['items']}
    assert public['title_considered']['value'] is False
    assert public['governor_defer']['action'] == {'type': 'governor_defer'}
