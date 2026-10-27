"""Actual-control qualification and one-shot ordinary EQUALIZE requests."""
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.actions import action_context, build_action_query
from civ6_fair_mcp.extensions import build_inspection_query, validate_extension_action
from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.deal_equalize import ACTIONS, QUERIES, CATEGORY, CONTEXT
from civ6_fair_mcp.extensions.diplomacy_actions import DIPLOMACY_HOOK
from civ6_fair_mcp.service import FairGameService
from test_extension_diplomacy_actions import ENGINE
from test_service import FakeTransport, raw


SETUP = r'''
state=_CIV6FAIR_V1;state.session=session;state.player_id=me
state.deal_role_session_v2=session
flags={visible=true,enabled=true,parent_visible=true,context_visible=true,
    panel_other=1,human=false,major=true,alive=true,pending=false,valid=true,unacceptable=false}
DealProposalAction.EQUALIZE=19;DealProposalAction.PENDING=4
DealProposalAction.ADJUSTED=5;DealProposalAction.EQUALIZE_FAILED=6
DealProposalAction.DEMANDED=7
player.GetID=function() return 0 end
player.IsHuman=function() return true end
player.IsAlive=function() return true end
Players[1].GetID=function() return flags.panel_other end
Players[1].IsHuman=function() return flags.human end
Players[1].IsMajor=function() return flags.major end
Players[1].IsAlive=function() return flags.alive end
g_LocalPlayer=player;g_OtherPlayer=Players[1]
ContextPtr={GetID=function() return 'DiplomacyDealView' end,
    IsVisible=function() return flags.context_visible end,GetParent=function() return nil end}
panel_parent={IsVisible=function() return flags.parent_visible end,GetParent=function() return ContextPtr end}
caption_reads=0;hidden_ui_reads=0
equalize_button={IsVisible=function() return flags.visible end,
    IsDisabled=function() return not flags.enabled end,GetParent=function() return panel_parent end,
    GetText=function() caption_reads=caption_reads+1;return '让这笔交易公平' end,
    GetChildren=function() hidden_ui_reads=hidden_ui_reads+1;error('INVENTORY') end}
Controls=setmetatable({EqualizeDeal=equalize_button}, {__index=function()
    hidden_ui_reads=hidden_ui_reads+1;error('HIDDEN_UI') end})
modals={}
UIManager={GetModalContexts=function() return modals end,IsModal=function() return false end}
DealManager.HasPendingDeal=function() return flags.pending end
draft.IsValid=function() return flags.valid end
draft.HasUnacceptableItems=function() return flags.unacceptable end
Game.GetLocalPlayer=function() return me end
Game.GetLocalObserver=function() return me end
local function event()
    local callbacks={}
    return {Add=function(fn) callbacks[#callbacks+1]=fn end,
        Fire=function(...) for _,fn in ipairs(callbacks) do fn(...) end end}
end
Events={DiplomacyIncomingDeal=event(),DiplomacySessionClosed=event()}
LuaEvents={DiploPopup_ShowMakeDeal=event(),DiploPopup_ShowMakeDemand=event(),
    DiploPopup_DealUpdated=event(),DiploPopup_HideDeal=event()}
'''


def vm(setup=""):
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(ENGINE + LUA_HELPERS + SETUP + setup + DIPLOMACY_HOOK + '''
__attempt=attempt;__known=known_player;__add=add_item
''')
    runtime.execute("attempt=__attempt;known_player=__known;add_item=__add")
    return runtime


def run(runtime, action=None, target=1):
    spec = ACTIONS["deal_equalize"] if action else QUERIES[CATEGORY]
    args = action or {"target_player": target}
    return runtime.execute('out={items={},supported=false,accepted=false}\nlocal function collect()\n'
                           + spec.body(args) + '\nend\ncollect()\nreturn out')


def choice(result):
    items = list(result["items"].values())
    assert len(items) == 1
    return dict(items[0]["action"].items())


def test_visible_fixed_button_requests_equalize_only_for_bound_safe_draft():
    runtime = vm()
    result = run(runtime)
    action = choice(result)
    assert action == validate_extension_action(action)
    assert action["session_id"] == 5 and action["target_player"] == 1
    assert result["items"][1]["name"] == "让这笔交易公平"
    assert run(runtime, action)["accepted"] is True
    assert list(runtime.globals().calls[1].values()) == [19, 0, 1]
    assert len(runtime.globals().calls) == 1
    assert runtime.globals().hidden_ui_reads == 0
    assert runtime.globals().state.deal_roles_v2[5]["active"] is True


@pytest.mark.parametrize("change", [
    "flags.visible=false", "flags.enabled=false", "flags.parent_visible=false",
    "flags.context_visible=false", "flags.panel_other=9", "flags.human=true",
    "flags.major=false", "flags.alive=false", "flags.pending=true", "flags.valid=false",
    "flags.unacceptable=true", "modals={{}}", "dealItems={}",
    "state.deal_roles_v2[5].active=false", "state.deal_roles_v2[5].demand=true",
    "state.deal_roles_v2[5].action=DealProposalAction.EQUALIZE_FAILED",
    "state.deal_roles_v2[5].action=DealProposalAction.DEMANDED",
    "state.deal_roles_v2[5].session='stale'", "state.deal_roles_v2[5].player=1",
    "state.deal_roles_v2[5].other=9", "state.deal_roles_v2[5].initiator=0",
    "state.deal_roles_v2[5]=nil", "DiplomacyManager.IsSessionIDOpen=function() return false end",
    "PopupDialog={Controls={PopupRoot={IsVisible=function() return true end}}}",
])
def test_hidden_disabled_obscured_or_stale_offer_never_returns_or_executes_request(change):
    runtime = vm()
    action = choice(run(runtime))
    runtime.execute(change)
    result = run(runtime)
    assert len(result["items"]) == 0
    assert run(runtime, action)["accepted"] is False
    assert len(runtime.globals().calls) == 0


@pytest.mark.parametrize("change", [
    "ContextPtr=nil", "Controls=nil", "Controls.EqualizeDeal=nil",
    "equalize_button.IsDisabled=nil", "equalize_button.IsVisible=nil",
    "equalize_button.GetParent=nil", "ContextPtr.GetParent=nil",
    "panel_parent.GetParent=nil",
    "ContextPtr.GetID=function() return 'UnrelatedPanel' end",
    "g_OtherPlayer=nil", "Players[1].IsHuman=nil", "UIManager.GetModalContexts=nil",
    "UIManager.GetModalContexts=function() return nil end",
    "UIManager.GetModalContexts=function() error('SECRET MODAL') end",
    "DealManager.HasPendingDeal=nil", "DealManager.SendWorkingDeal=nil",
    "DealProposalAction.EQUALIZE=nil", "draft.HasUnacceptableItems=nil",
    "DB.MakeHash=nil", "equalize_button.IsVisible=function() error('SECRET UI') end",
])
def test_missing_or_throwing_capability_is_fail_closed(change):
    runtime = vm()
    action = choice(run(runtime))
    runtime.execute(change)
    result = run(runtime)
    assert result["supported"] is False and len(result["items"]) == 0
    assert run(runtime, action)["accepted"] is False and len(runtime.globals().calls) == 0


def test_modal_ancestor_of_panel_does_not_hide_a_usable_child_button():
    runtime = vm("modal_parent={GetParent=function() return nil end,IsVisible=function() return true end};"
                 "ContextPtr.GetParent=function() return modal_parent end;modals={modal_parent}")
    assert choice(run(runtime))["type"] == "deal_equalize"


def test_control_outside_fixed_panel_cannot_supply_visibility_proof():
    runtime = vm("panel_parent.GetParent=function() return nil end")
    assert len(run(runtime)["items"]) == 0


def test_unknown_target_is_checked_before_panel_or_foreign_player_access():
    runtime = vm("Controls=setmetatable({}, {__index=function() error('HIDDEN PANEL') end})")
    result = run(runtime, target=9)
    assert result["supported"] is False and len(result["items"]) == 0
    assert runtime.globals().reads == 0


def test_filtered_draft_has_no_signature_caption_or_action_and_does_not_read_private_values():
    runtime = vm('''
dealItems={make_item(4,DealItemTypes.RESOURCES,2,1)}
dealItems[1].GetAmount=function() error('UNREVEALED_AMOUNT') end
dealItems[1].GetDuration=function() error('UNREVEALED_DURATION') end
DB.MakeHash=function() error('FILTERED_SIGNATURE') end
''')
    result = run(runtime)
    assert len(result["items"]) == 0
    assert runtime.globals().caption_reads == 0 and runtime.globals().hidden_ui_reads == 0


def test_changed_outgoing_terms_or_wrong_sid_cannot_submit_old_action():
    runtime = vm()
    action = choice(run(runtime))
    runtime.execute("dealItems={make_item(4,1,0,26)}")
    assert run(runtime, action)["accepted"] is False
    action = choice(run(runtime))
    action["session_id"] = 6
    assert run(runtime, action)["accepted"] is False
    assert len(runtime.globals().calls) == 0


def test_waiting_request_never_replays_and_new_public_event_releases_wait():
    runtime = vm()
    action = choice(run(runtime))
    assert run(runtime, action)["accepted"] is True
    assert len(run(runtime)["items"]) == 0
    assert run(runtime, action)["accepted"] is False
    assert len(runtime.globals().calls) == 1
    runtime.execute("LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.ADJUSTED)")
    assert choice(run(runtime))["type"] == "deal_equalize"


def test_synchronous_public_result_is_not_overwritten_by_waiting_marker():
    runtime = vm('''
DealManager.SendWorkingDeal=function(...)
    table.insert(calls,{...})
    Events.DiplomacyIncomingDeal.Fire(1,0,DealProposalAction.ADJUSTED)
end
''')
    action = choice(run(runtime))
    assert run(runtime, action)["accepted"] is True
    assert choice(run(runtime))["type"] == "deal_equalize"
    assert len(runtime.globals().calls) == 1


@pytest.mark.parametrize("event", [
    "LuaEvents.DiploPopup_HideDeal.Fire()",
    "Events.DiplomacySessionClosed.Fire(5)",
    "LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.EQUALIZE_FAILED)",
])
def test_result_failure_or_close_does_not_offer_another_request(event):
    runtime = vm()
    assert run(runtime, choice(run(runtime)))["accepted"] is True
    runtime.execute(event)
    assert len(run(runtime)["items"]) == 0


def test_result_with_hidden_resource_stays_filtered_without_hash_or_button_caption():
    runtime = vm()
    assert run(runtime, choice(run(runtime)))["accepted"] is True
    before = runtime.globals().caption_reads
    runtime.execute('''
dealItems={make_item(4,DealItemTypes.RESOURCES,2,1)}
DB.MakeHash=function() error('FILTERED_SIGNATURE') end
LuaEvents.DiploPopup_DealUpdated.Fire(1,DealProposalAction.ADJUSTED)
''')
    assert len(run(runtime)["items"]) == 0
    assert runtime.globals().caption_reads == before


def test_fixed_builders_use_shared_context_without_installing_duplicate_hooks():
    action = choice(run(vm()))
    query = build_inspection_query("a" * 32, CATEGORY, {"target_player": 1})
    script = build_action_query("a" * 32, action, "b" * 32, 0, 20)
    assert action_context(action) == CONTEXT
    for source in [query, script]:
        assert "ExposedMembers.Civ6FairState" in source
        assert "Controls.EqualizeDeal" in source
        assert "state.deal_role_hooks_v2=true" not in source
    assert "DealManager.SendWorkingDeal,DealProposalAction.EQUALIZE" in script


class ContextTransport(FakeTransport):
    def __init__(self, *responses, reconnect_after=None):
        super().__init__(*responses)
        self.contexts = []
        self.reconnect_after = reconnect_after

    async def execute(self, script, context="InGame", *, expected_generation=None):
        self.contexts.append((context, expected_generation))
        reply = await super().execute(script, context, expected_generation=expected_generation)
        if len(self.calls) == self.reconnect_after:
            self.connection_generation += 1
        return reply


def negotiation_raw(**extra):
    return raw(category=CATEGORY, supported=True, decision_mode="diplomacy", items=[{
        "id": "equalize", "name": "公平报价", "scope": "self", "owner_id": 0,
        "action": {"type": "deal_equalize", "target_player": 1, "session_id": 5,
                   "signature": "DEAL_1_2"},
    }], **extra)


async def test_service_double_read_binds_context_session_and_inactive_diplomacy_token():
    transport = ContextTransport(raw(active_turn=False), negotiation_raw(active_turn=False), raw(accepted=True))
    service = FairGameService(transport)
    result = await service.inspect_game(CATEGORY, {"target_player": 1})
    assert result["token_scope"] == "diplomacy"
    assert transport.contexts == [("InGame", None), (CONTEXT, 1)]
    response = await service.act(result["observation_token"], result["items"][0]["action"])
    assert response["status"] == "submitted"
    assert transport.contexts[-1] == (CONTEXT, 1)
    assert len(transport.calls) == 3


@pytest.mark.parametrize("change", [
    {"session": "b" * 32}, {"player_id": 1}, {"turn": 11},
])
async def test_service_mixed_identity_never_issues_token(change):
    transport = ContextTransport(raw(), negotiation_raw(**change))
    service = FairGameService(transport)
    result = await service.inspect_game(CATEGORY, {"target_player": 1})
    assert "observation_token" not in result
    assert result.get("ok") is False


async def test_service_generation_change_during_fixed_context_read_never_issues_token():
    transport = ContextTransport(raw(), negotiation_raw(), reconnect_after=2)
    service = FairGameService(transport)
    result = await service.inspect_game(CATEGORY, {"target_player": 1})
    assert "observation_token" not in result and result.get("ok") is False


async def test_service_read_failure_never_leaks_text_or_dispatches_equalize():
    transport = ContextTransport(raw(), RuntimeError("SECRET DEAL TEXT"))
    service = FairGameService(transport)
    result = await service.inspect_game(CATEGORY, {"target_player": 1})
    assert "observation_token" not in result
    assert "SECRET" not in json.dumps(result)


async def test_other_queries_keep_their_existing_ingame_route():
    transport = ContextTransport(raw(category="deal_state", supported=True, items=[]))
    result = await FairGameService(transport).inspect_game("deal_state", {"target_player": 1})
    assert result["ok"] is True and transport.contexts == [("InGame", None)]
