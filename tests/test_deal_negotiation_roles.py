"""Real Lua regressions for work-copy versus current negotiated-offer roles.

Source: GS DiplomacyDealView OnShow/OnDiplomacyIncomingDeal/OnRefuseDeal;
Base DiplomacyActionView MakeDeal_ApplyStatement publishes DealUpdated/HideDeal.
No tests connect to a running game.
"""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.diplomacy_actions import ACTIONS, QUERIES, DIPLOMACY_HOOK
from test_extension_diplomacy_actions import ENGINE, execute


OWN_DRAFT = """
DiplomacyManager.GetSessionInfo=function() return {FromPlayer=0,ToPlayer=1} end
_CIV6FAIR_V1.deal_roles_v2[5].initiator=0;_CIV6FAIR_V1.deal_roles_v2[5].action=4
"""
ENUMS = """
DealProposalAction.PENDING=4;DealProposalAction.ADJUSTED=5
DealProposalAction.EQUALIZE_FAILED=6;DealProposalAction.INSPECT=7
DealProposalAction.CLOSED=8;DealProposalAction.REJECTED_PERMANENT=9
DealProposalAction.DEMANDED=10
"""
HOOK_FIXTURE = """
state={session='test',player_id=0};_CIV6FAIR_V1=state
sid=5;initiator=0
DiplomacyManager.FindOpenSessionID=function() return sid end
DiplomacyManager.GetSessionInfo=function() return {FromPlayer=initiator,ToPlayer=1-initiator} end
Game.GetLocalPlayer=function() return 0 end;Game.GetLocalObserver=function() return 0 end
player.IsHuman=function() return true end;player.IsAlive=function() return true end
local function event()
    local callbacks={}
    return {Add=function(fn) callbacks[#callbacks+1]=fn end,
        Fire=function(...) for _,fn in ipairs(callbacks) do fn(...) end end,
        Count=function() return #callbacks end}
end
Events={DiplomacyIncomingDeal=event(),DiplomacySessionClosed=event()}
LuaEvents={DiploPopup_ShowMakeDeal=event(),DiploPopup_ShowMakeDemand=event(),
    DiploPopup_DealUpdated=event(),DiploPopup_HideDeal=event()}
"""


def records(out):
    return {v['id']: v for v in out['items'].values()}


def response(out, accept=True):
    value = dict(records(out)['accept' if accept else 'reject']['action'].items())
    value.pop('type')
    return value


def run(vm, name, params, query=False):
    spec = (QUERIES if query else ACTIONS)[name]
    body = spec.body(params if query else dict(params, type=name))
    return vm.execute('out={items={},supported=false,accepted=false}\n' +
                      'local function run()\n' + body + '\nend\nrun()\nreturn out')


def hooked(extra=''):
    vm = LuaRuntime(unpack_returned_tuples=True)
    # Keep the fixture's local action/visibility helpers in the same closure
    # as authored queries; return a runner instead of relying on Lua globals.
    body = ENGINE + '\n' + LUA_HELPERS + ENUMS + HOOK_FIXTURE + extra + DIPLOMACY_HOOK
    vm.execute(body + '''
function authored(body)
    -- Compiled test bodies use exported references to fixture-local helpers.
    return assert(load(body))()
end
__attempt=attempt;__known=known_player;__add=add_item
''')
    vm.execute('attempt=__attempt;known_player=__known;add_item=__add')
    return vm


def test_self_authored_peace_draft_never_becomes_an_incoming_offer():
    peace = '''
local give=make_item(2,DealItemTypes.AGREEMENTS,0,1)
local receive=make_item(3,DealItemTypes.AGREEMENTS,0,1)
give.GetFromPlayerID=function() return 0 end
for _,v in ipairs({give,receive}) do
    v.GetSubType=function() return DealAgreementTypes.MAKE_PEACE end
    v.IsLocked=function() return true end
end
dealItems={give,receive}
'''
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=OWN_DRAFT + ENUMS + peace)
    rows = records(out)
    assert rows['incoming_response_status']['value'] == 'outgoing_draft'
    assert 'OUTGOING_2' in rows and 'OUTGOING_3' in rows
    assert 'turns=0' in rows['OUTGOING_2']['description']
    assert not any(k.startswith('INCOMING_') for k in rows)
    assert 'accept' not in rows and 'reject' not in rows


@pytest.mark.parametrize('accept', [True, False])
def test_forged_or_old_offer_action_cannot_respond_to_self_draft(accept):
    _, offered = execute('deal_state', {'target_player': 1}, query=True)
    vm, out = execute('deal_respond', response(offered, accept), setup=OWN_DRAFT + ENUMS)
    assert out['accepted'] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize('old', [
    "state.deal_actions={[1]={session='test',action=1}}",
    "state.deal_roles_v2={[5]={session='old',sid=5,player=0,other=1,initiator=0,action=1,active=true}}",
    "state.deal_roles_v2={[4]={session='test',sid=4,player=0,other=1,initiator=0,action=1,active=true}}",
    "state.deal_roles_v2={[5]={session='test',sid=5,player=0,other=9,initiator=0,action=1,active=true}}",
    "state.deal_roles_v2={[5]={session='test',sid=5,player=9,other=1,initiator=0,action=1,active=true}}",
])
def test_old_or_mismatched_action_proof_cannot_upgrade_own_draft(old):
    setup = OWN_DRAFT + ENUMS + '\nstate={};_CIV6FAIR_V1=state\n' + old
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    assert records(out)['incoming_response_status']['value'] == 'phase_unavailable'
    assert 'accept' not in records(out)


@pytest.mark.parametrize('action', ['ACCEPTED', 'PROPOSED', 'ADJUSTED'])
@pytest.mark.parametrize('event', ['statement_update', 'native_incoming'])
def test_current_session_real_proposal_event_allows_response(action, event):
    vm = hooked()
    vm.execute('LuaEvents.DiploPopup_ShowMakeDeal.Fire(1)')
    if event == 'statement_update':
        vm.execute(f'LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.{action},"IGNORED TEXT")')
    else:
        vm.execute(f'Events.DiplomacyIncomingDeal.Fire(1,0,DealProposalAction.{action})')
    out = run(vm, 'deal_state', {'target_player': 1}, True)
    assert records(out)['incoming_response_status']['value'] == 'ready'
    args = response(out)
    accepted = run(vm, 'deal_respond', args)
    assert accepted['accepted'] is True and len(vm.globals().calls) == 2
    repeated = run(vm, 'deal_respond', args)
    assert repeated['accepted'] is False and len(vm.globals().calls) == 2


@pytest.mark.parametrize('action', ['REJECTED', 'EQUALIZE_FAILED', 'PENDING', 'INSPECT', 'CLOSED', 'REJECTED_PERMANENT'])
def test_non_offer_stage_never_exposes_response(action):
    vm = hooked()
    vm.execute(f'LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.{action})')
    out = run(vm, 'deal_state', {'target_player': 1}, True)
    assert 'accept' not in records(out) and 'reject' not in records(out)
    assert not any(k.startswith('INCOMING_') for k in records(out))


@pytest.mark.parametrize('close', [
    'LuaEvents.DiploPopup_HideDeal.Fire()',
    'Events.DiplomacySessionClosed.Fire(5)',
])
def test_normal_panel_close_or_session_close_retires_offer(close):
    vm = hooked('initiator=1\n')
    vm.execute('LuaEvents.DiploPopup_ShowMakeDeal.Fire(1)')
    out = run(vm, 'deal_state', {'target_player': 1}, True)
    args = response(out)
    vm.execute(close)
    assert run(vm, 'deal_respond', args)['accepted'] is False
    assert records(run(vm, 'deal_state', {'target_player': 1}, True))['incoming_response_status']['value'] == 'conversation_closed'


def test_old_negotiation_event_does_not_authorize_new_sid_same_opponent():
    vm = hooked()
    vm.execute('LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.ACCEPTED);sid=6')
    out = run(vm, 'deal_state', {'target_player': 1}, True)
    assert records(out)['incoming_response_status']['value'] == 'phase_unavailable'
    assert 'accept' not in records(out)


def test_foreign_greeting_session_with_residual_work_copy_is_not_an_offer():
    vm = hooked('initiator=1\n')
    # Session ownership alone is also true for greetings and denunciations.
    out = run(vm, 'deal_state', {'target_player': 1}, True)
    assert records(out)['incoming_response_status']['value'] == 'phase_unavailable'
    assert 'accept' not in records(out) and 'reject' not in records(out)
    vm.execute('Events.DiplomacyIncomingDeal.Fire(1,0,DealProposalAction.ACCEPTED)')
    assert 'accept' not in records(run(vm, 'deal_state', {'target_player': 1}, True))


@pytest.mark.parametrize('change', [
    'dealItems={make_item(4,1,0,250)}',
    'LuaEvents.DiploPopup_HideDeal.Fire()',
    'LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.ADJUSTED)',
])
def test_terms_or_phase_changed_during_normal_copy_cannot_be_accepted(change):
    vm = hooked('initiator=1\n')
    vm.execute('LuaEvents.DiploPopup_ShowMakeDeal.Fire(1)')
    out = run(vm, 'deal_state', {'target_player': 1}, True)
    vm.execute('DealManager.CopyIncomingToOutgoingWorkingDeal=function() '+change+' end')
    result = run(vm, 'deal_respond', response(out))
    assert result['accepted'] is False and len(vm.globals().calls) == 0


def test_missing_action_constants_do_not_pass_nil_equality_as_an_offer():
    _, out = execute('deal_state', {'target_player': 1}, query=True,
                     setup=OWN_DRAFT + ';DealProposalAction={} ')
    assert 'accept' not in records(out) and 'reject' not in records(out)


def test_pending_offer_cannot_respond_or_edit():
    _, offered = execute('deal_state', {'target_player': 1}, query=True)
    setup = 'DealManager.HasPendingDeal=function() return true end'
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    assert records(out)['incoming_response_status']['value'] == 'pending'
    assert not any(row['action'] for row in out['items'].values())
    for accept in [True, False]:
        vm, result = execute('deal_respond', response(offered, accept), setup=setup)
        assert result['accepted'] is False and len(vm.globals().calls) == 0


def test_self_draft_can_be_edited_despite_nonempty_incoming_work_copy():
    vm, out = execute('deal_clear', {'target_player': 1}, setup=OWN_DRAFT + ENUMS)
    assert out['accepted'] is True
    assert vm.globals().calls[1][1] == 0  # normal OUTGOING ClearWorkingDeal


def test_explicit_sending_of_own_draft_proposes_and_never_accepts_work_copy():
    vm, out = execute('deal_send', {'target_player': 1}, setup=OWN_DRAFT + ENUMS)
    assert out['accepted'] is True
    assert list(vm.globals().calls[1].values()) == [3, 0, 1]  # PROPOSED, not ACCEPTED


def test_normal_ai_initiated_refusal_is_negative_response():
    _, offer = execute('deal_state', {'target_player': 1}, query=True)
    vm, out = execute('deal_respond', response(offer, False))
    assert out['accepted'] is True
    assert list(vm.globals().calls[1].values()) == [5, 0, 'NEGATIVE']


@pytest.mark.parametrize('owned,expected', [(True, [9, 0, 1]), (False, [5, 0, 'NEGATIVE'])])
def test_normal_refusal_preserves_unacceptable_local_item_branch(owned, expected):
    setup = ENUMS + '''
draft.HasUnacceptableItems=function() return true end
dealItems[1].IsUnacceptable=function() return true end
'''
    if owned:
        setup += 'dealItems[1].GetFromPlayerID=function() return 0 end'
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    vm, result = execute('deal_respond', response(out, False), setup=setup)
    assert result['accepted'] is True
    assert list(vm.globals().calls[1].values()) == expected


def test_refusing_counteroffer_to_self_initiated_session_closes_session():
    vm = hooked()
    vm.execute('LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.ACCEPTED)')
    offer = run(vm, 'deal_state', {'target_player': 1}, True)
    out = run(vm, 'deal_respond', response(offer, False))
    assert out['accepted'] is True and list(vm.globals().calls[1].values()) == [5]


def test_v2_hot_install_ignores_legacy_hooks_and_is_idempotent():
    vm = hooked('state.deal_hooks=true;state.diplomacy_hooks=true;state.deal_actions={[1]={session="test",action=1}}\n')
    assert records(run(vm, 'deal_state', {'target_player': 1}, True))['incoming_response_status']['value'] == 'phase_unavailable'
    assert vm.globals().Events.DiplomacyIncomingDeal.Count() == 1
    vm.execute(DIPLOMACY_HOOK)
    assert vm.globals().Events.DiplomacyIncomingDeal.Count() == 1
    assert vm.globals().LuaEvents.DiploPopup_DealUpdated.Count() == 1
    vm.execute('LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.ACCEPTED)')
    assert 'accept' in records(run(vm, 'deal_state', {'target_player': 1}, True))


def test_show_callback_does_not_overwrite_synchronous_inspection_result():
    vm = hooked('LuaEvents.DiploPopup_ShowMakeDeal.Add(function(other) LuaEvents.DiploPopup_DealUpdated.Fire(other,DealProposalAction.REJECTED) end)\n')
    vm.execute('LuaEvents.DiploPopup_ShowMakeDeal.Fire(1)')
    out = run(vm, 'deal_state', {'target_player': 1}, True)
    assert records(out)['incoming_response_status']['value'] == 'response_unavailable'
    assert vm.globals().state.deal_roles_v2[5]['action'] == 2


def test_unknown_or_nonparticipant_event_never_reads_or_caches_foreign_data():
    vm = hooked()
    vm.execute('LuaEvents.DiploPopup_DealUpdated.Fire(9,1);Events.DiplomacyIncomingDeal.Fire(9,8,1)')
    assert vm.globals().reads == 0
    assert len(vm.globals().state.deal_roles_v2) == 0


def test_unacceptable_native_terms_cannot_be_accepted_or_sent():
    _, offer = execute('deal_state', {'target_player': 1}, query=True)
    setup = 'draft.HasUnacceptableItems=function() return true end'
    _, out = execute('deal_state', {'target_player': 1}, query=True, setup=setup)
    assert 'accept' not in records(out)
    vm, result = execute('deal_respond', response(offer), setup=setup)
    assert result['accepted'] is False and len(vm.globals().calls) == 0
    vm, result = execute('deal_send', {'target_player': 1}, setup=setup + ENUMS)
    assert result['accepted'] is False and len(vm.globals().calls) == 0
