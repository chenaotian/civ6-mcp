"""Offer captions and response availability must not hide incomplete terms."""

import pytest

from test_extension_diplomacy_actions import execute, deal_terms


def records(out):
    return {row['id']: row for row in out['items'].values()}


WORKS = r'''
GameInfo.GreatWorks=setmetatable({}, {__index=function() error('STATIC SUBTYPE IS NOT AN INSTANCE TITLE') end})
Game.GetGreatWorkDataFromIndex=function() error('PRIVATE INSTANCE DETAILS') end
Game.GetGreatWorkTypeFromIndex=function() error('NO UNNEEDED MAPPING') end
Players[1].GetCities=function() error('PRIVATE FOREIGN CITY') end
Players[1].GetUnits=function() error('PRIVATE FOREIGN UNIT') end
local a=make_item(4,DealItemTypes.GREATWORK,30,0)
local b=make_item(5,DealItemTypes.GREATWORK,26,0)
a.GetValueTypeNameID=function() return 'LOC_OFFERED_WORK_30' end
b.GetValueTypeNameID=function() return 'LOC_OFFERED_WORK_26' end
Locale.Lookup=function(key)
    if key=='LOC_OFFERED_WORK_30' then return 'Offered painting' end
    if key=='LOC_OFFERED_WORK_26' then return 'Offered writing' end
    return key
end
dealItems={a,b}
'''


def test_distinct_offered_instances_with_default_subtype_get_actual_menu_titles():
    vm, out = execute('deal_state', {'target_player': 1}, query=True, setup=WORKS)
    terms = deal_terms(out)
    assert terms['INCOMING_4']['name'] == 'receive Offered painting amount=0 turns=0'
    assert terms['INCOMING_5']['name'] == 'receive Offered writing amount=0 turns=0'
    assert 'value=30' in terms['INCOMING_4']['description']
    assert 'value=26' in terms['INCOMING_5']['description']
    assert 'subtype=0' in terms['INCOMING_4']['description']
    assert records(out)['incoming_response_status']['value'] == 'ready'
    assert len(vm.globals().calls) == 0 and vm.globals().reads == 0


@pytest.mark.parametrize('getter', [
    'nil', '0', 'function() return nil end', 'function() return false end',
    'function() return 0 end', "function() return '' end",
    'function() return {} end', "function() error('caption unavailable') end",
])
def test_missing_or_invalid_work_caption_is_generic_without_guessing_subtype(getter):
    setup = WORKS + '\na.GetValueTypeNameID=' + getter + '\ndealItems={a}\n'
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    assert deal_terms(out)['INCOMING_4']['name'] == 'receive GREATWORK amount=0 turns=0'
    assert records(out)['incoming_response_status']['value'] == 'ready'


def test_work_caption_changes_do_not_change_exact_offer_fingerprint():
    _, first = execute('deal_state', {'target_player': 1}, query=True, setup=WORKS)
    _, second = execute('deal_state', {'target_player': 1}, query=True,
                        setup=WORKS + "\na.GetValueTypeNameID=function() return 'Localized title' end")
    assert dict(records(first)['accept']['action']) == dict(records(second)['accept']['action'])


def test_unrelated_participant_work_is_filtered_before_caption_and_signature():
    setup = WORKS + '''
a.GetFromPlayerID=function() return 9 end
a.GetValueTypeNameID=function() error('HIDDEN WORK NAME') end
a.GetAmount=function() error('HIDDEN WORK VALUE') end
DB.MakeHash=function() error('HIDDEN TERMS SIGNATURE') end
dealItems={a}
'''
    vm, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    items = records(out)
    assert set(items) == {'incoming_response_status'}
    assert items['incoming_response_status']['value'] == 'filtered_terms'
    assert len(vm.globals().calls) == 0 and vm.globals().reads == 0


@pytest.mark.parametrize('duration', [0, 8, 30])
def test_ordinary_peace_duration_is_not_a_response_restriction(duration):
    setup = f'''
local a=make_item(2,DealItemTypes.AGREEMENTS,-1,0)
local b=make_item(3,DealItemTypes.AGREEMENTS,-1,0)
a.GetSubType=function() return DealAgreementTypes.MAKE_PEACE end
b.GetSubType=a.GetSubType
b.GetFromPlayerID=function() return me end
a.GetDuration=function() return {duration} end
b.GetDuration=a.GetDuration
dealItems={{a,b}}
'''
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    items = records(out)
    assert items['incoming_response_status']['value'] == 'ready'
    assert {'accept', 'reject'} <= set(items)
    params = dict(items['accept']['action'])
    params.pop('type')
    vm, result = execute('deal_respond', params, setup=setup)
    assert result['accepted'] is True and len(vm.globals().calls) == 2


HIDDEN = r'''
local hidden=make_item(90,DealItemTypes.RESOURCES,2,77)
hidden.GetAmount=function() error('HIDDEN AMOUNT') end
hidden.GetDuration=function() error('HIDDEN DURATION') end
hidden.GetSubType=function() error('HIDDEN SUBTYPE') end
hidden.GetValueTypeNameID=function() error('HIDDEN RESOURCE NAME') end
hidden.GetSubTypeNameID=function() error('HIDDEN CAPTION') end
GameInfo.Resources[2]=setmetatable({Hash=999},{__index=function() error('HIDDEN RESOURCE DEFINITION') end})
DB.MakeHash=function() error('NO FILTERED FINGERPRINT') end
dealItems={hidden}
'''


def test_filtered_offer_has_only_generic_status_and_never_fingerprint_or_actions():
    vm, out = execute('deal_state', {'target_player': 1}, query=True, setup=HIDDEN)
    items = records(out)
    assert set(items) == {'incoming_response_status'}
    status = dict(items['incoming_response_status'])
    assert status['value'] == 'filtered_terms'
    assert set(status) == {'id', 'name', 'value', 'scope', 'owner_id'}
    assert not any(text in status['name'] for text in ('uranium', 'URANIUM', '77', '90', 'resource'))
    assert len(vm.globals().calls) == 0 and vm.globals().reads == 0


def test_visible_subset_never_suggests_whole_offer_can_be_accepted():
    setup = HIDDEN + '\ndealItems={make_item(4,DealItemTypes.GOLD,-1,25),hidden}\n'
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    items = records(out)
    assert items['incoming_response_status']['value'] == 'filtered_terms'
    assert {'OUTGOING_4', 'INCOMING_4'} <= set(items)
    assert 'accept' not in items and 'reject' not in items
    assert not any(row['action'] and row['action']['type'] == 'deal_respond' for row in items.values())


@pytest.mark.parametrize('accept', [False, True])
def test_hidden_terms_added_after_observation_block_response_before_signature_or_copy(accept):
    _, offered = execute('deal_state', {'target_player': 1}, query=True)
    params = dict(records(offered)['accept' if accept else 'reject']['action'])
    params.pop('type')
    vm, result = execute('deal_respond', params, setup=HIDDEN)
    assert result['accepted'] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize('mutation,expected,respond', [
    ('DiplomacyManager.FindOpenSessionID=function() return -1 end', 'session_unavailable', False),
    ('DB.MakeHash=nil', 'signature_unavailable', False),
    ('draft.IsValid=function() return false end', 'invalid_offer', True),
    ('dealItems={}', 'invalid_offer', True),
    ('DealManager.GetWorkingDeal=function(direction) if direction==0 then return draft end end', 'no_incoming_offer', False),
])
def test_response_status_distinguishes_only_preexisting_public_eligibility(mutation, expected, respond):
    vm, out = execute('deal_state', {'target_player': 1}, query=True, setup=mutation)
    items = records(out)
    assert items['incoming_response_status']['value'] == expected
    assert 'accept' not in items
    assert ('reject' in items) is respond
    assert len(vm.globals().calls) == 0


def test_filtered_status_takes_priority_and_still_does_not_create_signature_without_session():
    _, out = execute('deal_state', {'target_player': 1}, query=True,
                     setup=HIDDEN + '\nDiplomacyManager.FindOpenSessionID=function() return -1 end')
    assert set(records(out)) == {'incoming_response_status'}
    assert records(out)['incoming_response_status']['value'] == 'filtered_terms'
