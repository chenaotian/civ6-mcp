"""Draft edits preserve native UI refresh/INSPECT and existing action guards."""
import pytest

from civ6_fair_mcp.actions import action_context, build_action_query
from civ6_fair_mcp.extensions.deal_ui_refresh import CONTEXT, DRAFT_ACTIONS, wrap_draft_edit
from civ6_fair_mcp.extensions.diplomacy_actions import ACTIONS
from civ6_fair_mcp.service import FairGameService
from test_deal_equalize import vm, ContextTransport
from test_deal_negotiation_roles import run as run_deal, response, records
from test_service import raw


SETUP = r'''
ui_calls={};edited_items={}
DealProposalAction.INSPECT=18
UpdateDealPanel=function(panel_player)
    assert(panel_player==g_LocalPlayer)
    table.insert(ui_calls,'UpdateDealPanel')
end
UpdateProposedWorkingDeal=function()
    table.insert(ui_calls,'UpdateProposedWorkingDeal')
end
DealManager.ClearWorkingDeal=function(direction,from,to)
    table.insert(calls,{direction,from,to})
    dealItems={}
end
draft.RemoveItemByID=function(_,id)
    table.insert(calls,{'remove',id});dealItems={};return true
end
draft.AddItemOfType=function(_,kind,from)
    local term=make_item(10,kind,1,1)
    term.SetDuration=function(_,value) edited_items.duration=value end
    term.SetValueType=function(_,value) edited_items.value=value end
    term.SetAmount=function(_,value) edited_items.amount=value end
    term.GetMaxAmount=function() return 100 end
    table.insert(dealItems,term)
    return term
end
'''


def run(runtime, action, *, body=None):
    source = wrap_draft_edit(action, body if body is not None else ACTIONS[action["type"]].body(action))
    return runtime.execute('out={items={},supported=false,accepted=false}\nlocal function perform()\n'
                           + source + '\nend\nperform()\nreturn out')


CLEAR = {"type": "deal_clear", "target_player": 1}
REMOVE = {"type": "deal_remove_item", "target_player": 1, "item_id": 4}
ADD = {"type": "deal_add_item", "target_player": 1, "side": "receive", "kind": "resource",
       "value": 1, "amount": 10, "duration": 0, "agreement": "NONE"}


@pytest.mark.parametrize("action", [CLEAR, REMOVE, ADD])
def test_submitted_draft_edit_calls_exact_normal_refresh_in_order(action):
    runtime = vm(SETUP)
    assert run(runtime, action)["accepted"] is True
    assert list(runtime.globals().ui_calls.values()) == ["UpdateDealPanel", "UpdateProposedWorkingDeal"]


def test_only_stock_callback_decides_whether_to_inspect_the_changed_draft():
    runtime = vm(SETUP + '''
UpdateProposedWorkingDeal=function()
    table.insert(ui_calls,'UpdateProposedWorkingDeal')
    if draft:GetItemCount()>0 then
        DealManager.SendWorkingDeal(DealProposalAction.INSPECT,me,1)
        LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.REJECTED)
    end
end
''')
    assert run(runtime, ADD)["accepted"] is True
    assert list(runtime.globals().calls[1].values()) == [18, 0, 1]
    assert runtime.globals().state.deal_roles_v2[5]["action"] == 2
    assert runtime.globals().state.deal_roles_v2[5]["active"] is True
    assert runtime.eval("state.deal_edited_wait_v1.phase~=state.deal_roles_v2[5]") is True
    assert "accept" not in records(run_deal(runtime, "deal_state", {"target_player": 1}, True))
    assert len(runtime.globals().calls) == 1
    # Emptying the draft calls the same stock function but does not itself
    # invent another INSPECT, proposal, EQUALIZE, or acceptance request.
    assert run(runtime, CLEAR)["accepted"] is True
    assert len(runtime.globals().calls) == 2
    assert list(runtime.globals().calls[2].values()) == [0, 0, 1]


def test_draft_refresh_blocks_old_incoming_response_until_real_public_event():
    runtime = vm(SETUP + '''
local old_items={dealItems[1]}
local incoming={GetItemCount=function() return #old_items end,
    IsValid=function() return true end,IsGift=function() return false end,
    Items=function() local i=0;return function() i=i+1;return old_items[i] end end}
DealManager.GetWorkingDeal=function(direction) return direction==DealDirection.INCOMING and incoming or draft end
''')
    before = run_deal(runtime, "deal_state", {"target_player": 1}, True)
    old_accept = response(before)
    assert run(runtime, CLEAR)["accepted"] is True
    after = records(run_deal(runtime, "deal_state", {"target_player": 1}, True))
    assert "accept" not in after and "reject" not in after
    assert run_deal(runtime, "deal_respond", old_accept)["accepted"] is False
    # The cache is not retired, so subsequent ordinary editing and the native
    # public reply still work; no fabricated proposal action is written.
    assert runtime.globals().state.deal_roles_v2[5]["active"] is True
    assert run(runtime, ADD)["accepted"] is True
    runtime.execute("LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.ADJUSTED)")
    assert "accept" in records(run_deal(runtime, "deal_state", {"target_player": 1}, True))


@pytest.mark.parametrize("change", [
    "ContextPtr=nil", "flags.context_visible=false", "flags.panel_other=9",
    "ContextPtr.GetID=function() return 'WrongPanel' end", "ContextPtr.GetParent=nil",
    "UpdateDealPanel=nil", "UpdateProposedWorkingDeal=nil",
    "modals={{}}", "UIManager.GetModalContexts=nil",
    "UIManager.GetModalContexts=function() error('SECRET MODAL') end",
    "PopupDialog={Controls={PopupRoot={IsVisible=function() return true end}}}",
])
def test_hidden_wrong_or_unsupported_panel_cannot_edit_or_refresh(change):
    runtime = vm(SETUP + change)
    assert run(runtime, CLEAR)["accepted"] is False
    assert len(runtime.globals().calls) == len(runtime.globals().ui_calls) == 0


@pytest.mark.parametrize("change", [
    "flags.pending=true", "state.deal_roles_v2[5].active=false",
    "state.deal_roles_v2[5].demand=true",
    "draft.IsGift=function() return true end",
    "DiplomacyManager.IsSessionIDOpen=function() return false end",
])
def test_original_deal_permissions_remain_required(change):
    runtime = vm(SETUP + change)
    assert run(runtime, CLEAR)["accepted"] is False
    assert len(runtime.globals().calls) == len(runtime.globals().ui_calls) == 0


def test_rejected_authored_edit_does_not_trigger_ui_or_ai_request():
    runtime = vm(SETUP)
    assert run(runtime, {**ADD, "amount": 999})["accepted"] is False
    assert len(runtime.globals().calls) == len(runtime.globals().ui_calls) == 0


@pytest.mark.parametrize("change", [
    "flags.context_visible=false", "flags.panel_other=9", "modals={{}}",
    "DiplomacyManager.FindOpenSessionID=function() return 6 end",
])
def test_panel_or_session_change_during_edit_prevents_refreshing_another_conversation(change):
    runtime = vm(SETUP + "DealManager.ClearWorkingDeal=function() " + change + ";table.insert(calls,{'edit'}) end")
    assert run(runtime, CLEAR)["accepted"] is True
    assert len(runtime.globals().calls) == 1
    assert len(runtime.globals().ui_calls) == 0


def test_refresh_error_does_not_replay_the_edit_or_run_later_callback():
    runtime = vm(SETUP + "UpdateDealPanel=function() table.insert(ui_calls,'failed');error('PRIVATE') end")
    assert run(runtime, CLEAR)["accepted"] is True
    assert len(runtime.globals().calls) == 1
    assert list(runtime.globals().ui_calls.values()) == ["failed"]


def test_unmet_target_is_rejected_before_panel_or_player_details():
    runtime = vm(SETUP)
    assert run(runtime, {**CLEAR, "target_player": 9})["accepted"] is False
    assert runtime.globals().reads == 0
    assert len(runtime.globals().calls) == len(runtime.globals().ui_calls) == 0


@pytest.mark.parametrize("kind", sorted(DRAFT_ACTIONS))
def test_only_fixed_draft_actions_use_the_shared_stock_context(kind):
    assert action_context({"type": kind}) == CONTEXT
    if kind == "deal_add_war":
        action = {"type": kind, "target_player": 1, "side": "give", "agreement": "JOINT_WAR",
                  "enemy": 2, "war": "FORMAL_WAR", "duration": 30}
    else:
        action = {"deal_clear": CLEAR, "deal_remove_item": REMOVE, "deal_add_item": ADD}[kind]
    source = build_action_query("c" * 32, action, "b" * 32, 0, 20)
    assert "ExposedMembers.Civ6FairState" in source
    assert 'session ~= "' + "b" * 32 + '"' in source
    assert "or turn ~= 20" in source
    assert "UpdateDealPanel(g_LocalPlayer)" in source
    assert "UpdateProposedWorkingDeal()" in source
    assert "state.deal_role_hooks_v2=true" not in source


def test_other_diplomacy_actions_do_not_gain_a_ui_edit_wrapper():
    action = {"type": "deal_send", "target_player": 1}
    assert action_context(action) == "InGame"
    assert "UpdateDealPanel(g_LocalPlayer)" not in build_action_query("c" * 32, action, "b" * 32, 0, 20)


async def test_service_routes_normal_edit_and_still_rejects_reconnected_capability():
    transport = ContextTransport(raw(), raw(accepted=True), raw())
    service = FairGameService(transport)
    observed = await service.get_player_state()
    result = await service.act(observed["observation_token"], CLEAR)
    assert result["status"] == "submitted" and transport.contexts[-1] == (CONTEXT, 1)
    observed = await service.get_player_state()
    transport.connection_generation += 1
    result = await service.act(observed["observation_token"], CLEAR)
    assert result["error"] == "fresh_observation_required"
    assert len(transport.calls) == 3
