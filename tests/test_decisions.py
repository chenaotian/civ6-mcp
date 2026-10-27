"""End-turn availability follows real submission guards, not the raw UI flag."""

import pytest

from civ6_fair_mcp.extensions import build_inspection_query
from civ6_fair_mcp.extensions.popups import POPUP_PATHS
from civ6_fair_mcp.inspection_policy import public_inspection
from test_actions import action_script as _action_script, engine


_SESSION = "pending_decisions_test_session"


def action_script(action):
    return _action_script(action, nonce=_SESSION, expected_session=_SESSION)


@pytest.fixture
def pending_engine(engine):
    vm, run = engine
    vm.execute('''
UIManager = {GetModalContexts=function() return {} end}
ContextPtr = {LookUpControl=function() return nil end}
NotificationManager.GetAllEndTurnBlocking = function(who)
    assert(who == 0)
    return {controls.blocker}
end
EndTurnBlockingTypes.RESEARCH = 10
EndTurnBlockingTypes.CIVIC = 11
EndTurnBlockingTypes.COMMEMORATION_AVAILABLE = 12
EndTurnBlockingTypes.GOVERNOR_OPPORTUNITY = 13
GameInfo.Notifications = definitions("NotificationType", {
    {NotificationType="NOTIFICATION_TEST", Hash=800}
})
notification = {
        GetPlayerID=function() return 0 end,
        GetID=function() return 81 end,
        IsDismissed=function() return controls.dismissed == true end,
        GetEndTurnBlocking=function() return 0 end,
        IsIconDisplayable=function() return true end,
        GetMessage=function() return "Visible own notification" end,
        GetSummary=function() return "Notification remains available" end,
        CanUserDismiss=function() return true end,
}
NotificationManager.FindType = function(hash, who)
    assert(hash == 800 and who == 0)
    return notification
end
NotificationManager.Find = function(who, id)
    assert(who == 0 and id == 81)
    return notification
end
NotificationManager.Dismiss = function(who, id)
    assert(who == 0 and id == 81)
    table.insert(calls,{kind="dismiss",player=who,id=id})
    controls.dismissed=true
end
LuaEvents={ActionPanel_ActivateNotification=function(n)
    assert(n==notification);table.insert(calls,{kind="activate",id=n:GetID()}) end}
''')

    def pending():
        result = public_inspection(run(build_inspection_query(
            _SESSION, "pending_decisions", {})), "pending_decisions")
        return {item["id"]: item for item in result["items"]}

    return vm, run, pending


def test_ready_observation_is_read_only_and_normal_end_turn_can_submit(pending_engine):
    vm, run, pending = pending_engine
    items = pending()
    assert items["can_end_turn"]["value"] is True
    assert "rechecks" in items["can_end_turn"]["description"]
    assert items["notification:81"]["action"]["type"] == "activate_notification"
    assert items["dismiss:81"]["action"]["type"] == "dismiss_notification"
    assert len(vm.globals().calls) == 0
    assert run(action_script({"type": "end_turn"}))["accepted"] is True
    assert len(vm.globals().calls) == 1


@pytest.mark.parametrize("blocker", [10, 11, 12, 13])
def test_engine_can_end_turn_true_does_not_override_required_decision(pending_engine, blocker):
    vm, run, pending = pending_engine
    vm.globals().controls.blocker = blocker
    assert vm.globals().UI.CanEndTurn() is True
    items = pending()
    assert items["can_end_turn"]["value"] is False
    assert items[f"blocker:{blocker}"]["name"] != "UNKNOWN_BLOCKER"
    assert run(action_script({"type": "end_turn"}))["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("control,value", [
    ("active", False), ("complete", False), ("busy", True), ("end_turn", False),
])
def test_turn_phase_is_part_of_observed_availability(pending_engine, control, value):
    vm, run, pending = pending_engine
    vm.globals().controls[control] = value
    assert pending()["can_end_turn"]["value"] is False
    assert run(action_script({"type": "end_turn"}))["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("modal_result", ['{"VisibleModal"}', 'nil', 'false', 'error("private modal error")'])
def test_native_modal_or_failed_modal_check_is_not_ready(pending_engine, modal_result):
    vm, run, pending = pending_engine
    vm.execute(f'UIManager.GetModalContexts=function() return {modal_result} end')
    assert pending()["can_end_turn"]["value"] is False
    assert run(action_script({"type": "end_turn"}))["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("popup", ["generic", "diplomacy", "deal", "world_congress"])
def test_visible_inline_confirmation_prevents_observed_end_turn(pending_engine, popup):
    vm, run, pending = pending_engine
    vm.globals().blocking_path = POPUP_PATHS[popup][0] + "/PopupRoot"
    vm.execute('''ContextPtr.LookUpControl=function(self,path)
        if path==blocking_path then return {IsVisible=function() return true end} end
    end''')
    assert pending()["can_end_turn"]["value"] is False
    assert run(action_script({"type": "end_turn"}))["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_hidden_inline_confirmation_does_not_prevent_end_turn(pending_engine):
    vm, run, pending = pending_engine
    vm.globals().blocking_path = POPUP_PATHS["generic"][0] + "/PopupRoot"
    vm.execute('''ContextPtr.LookUpControl=function(self,path)
        if path==blocking_path then return {IsVisible=function() return false end} end
    end''')
    assert pending()["can_end_turn"]["value"] is True
    assert run(action_script({"type": "end_turn"}))["accepted"] is True


@pytest.mark.parametrize("missing", [
    "UI.CanEndTurn=nil", "UI.RequestAction=nil", "ActionTypes=nil",
    "ActionTypes.ACTION_ENDTURN=nil", "NotificationManager.GetFirstEndTurnBlocking=nil",
    "UIManager=nil", "UIManager.GetModalContexts=nil", "ContextPtr=nil",
    "ContextPtr.LookUpControl=nil",
])
def test_missing_readiness_capability_is_false_without_losing_notifications(pending_engine, missing):
    vm, _, pending = pending_engine
    vm.execute(missing)
    items = pending()
    assert items["can_end_turn"]["value"] is False
    assert items["notification:81"]["name"] == "Visible own notification"
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("mutation", [
    "NotificationManager=nil", "EndTurnBlockingTypes=nil",
    "EndTurnBlockingTypes.NO_ENDTURN_BLOCKING=nil",
])
def test_missing_blocker_capability_is_false_and_end_turn_rejects(pending_engine, mutation):
    vm, run, pending = pending_engine
    vm.execute(mutation)
    assert pending()["can_end_turn"]["value"] is False
    assert run(action_script({"type": "end_turn"}))["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("visibility", ["{}", "{IsVisible=function() return nil end}"])
def test_unknown_confirmation_visibility_fails_closed(pending_engine, visibility):
    vm, _, pending = pending_engine
    vm.globals().blocking_path = POPUP_PATHS["generic"][0] + "/PopupRoot"
    vm.execute(f'''ContextPtr.LookUpControl=function(self,path)
        if path==blocking_path then return {visibility} end
    end''')
    assert pending()["can_end_turn"]["value"] is False


@pytest.mark.parametrize("getter", ["UI.CanEndTurn", "NotificationManager.GetFirstEndTurnBlocking"])
def test_readiness_getter_failure_does_not_remove_other_decisions(pending_engine, getter):
    vm, _, pending = pending_engine
    vm.execute(f'{getter}=function() error("private readiness failure") end')
    items = pending()
    assert items["can_end_turn"]["value"] is False
    assert "notification:81" in items
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("new_state", [
    "controls.blocker=10", "controls.busy=true", "controls.active=false",
    "UIManager.GetModalContexts=function() return {'NewModal'} end",
])
def test_end_turn_revalidates_after_ready_observation(pending_engine, new_state):
    vm, run, pending = pending_engine
    assert pending()["can_end_turn"]["value"] is True
    vm.execute(new_state)
    assert run(action_script({"type": "end_turn"}))["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_dismiss_normal_signature_hides_retained_findtype_result_on_next_read(pending_engine):
    vm, run, pending = pending_engine
    offered = pending()["dismiss:81"]["action"]
    assert run(action_script(offered))["accepted"] is True
    assert dict(vm.globals().calls[1].items()) == {"kind": "dismiss", "player": 0, "id": 81}
    # Native core may keep the object after the panel removes its UI entry.
    assert vm.globals().NotificationManager.FindType(800, 0) is not None
    items = pending()
    assert "notification:81" not in items and "dismiss:81" not in items
    assert items["can_end_turn"]["value"] is True
    assert len(vm.globals().calls) == 1


@pytest.mark.parametrize("kind", ["dismiss_notification", "activate_notification"])
def test_notification_action_rechecks_dismissed_state_after_observation(pending_engine, kind):
    vm, run, pending = pending_engine
    assert "notification:81" in pending()
    vm.execute("controls.dismissed=true")
    assert run(action_script({"type": kind, "notification_id": 81}))["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("change", [
    "notification.IsDismissed=nil",
    "notification.IsDismissed=function() error('SECRET_STATE') end",
    "notification.IsDismissed=function() return nil end",
    "notification.IsDismissed=function() return 0 end",
])
def test_unknown_dismissed_state_omits_only_notification_and_rejects_response(pending_engine, change):
    vm, run, pending = pending_engine
    assert "notification:81" in pending()
    vm.execute(change)
    items = pending()
    assert "notification:81" not in items and "dismiss:81" not in items
    assert items["can_end_turn"]["value"] is True
    for kind in ("activate_notification", "dismiss_notification"):
        assert run(action_script({"type": kind, "notification_id": 81}))["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_dismissed_notification_text_is_not_read(pending_engine):
    vm, _, pending = pending_engine
    vm.execute('''controls.dismissed=true
        notification.GetMessage=forbid;notification.GetSummary=forbid
        notification.IsIconDisplayable=forbid;notification.CanUserDismiss=forbid''')
    items = pending()
    assert items["can_end_turn"]["value"] is True
    assert "notification:81" not in items


def test_foreign_notification_owner_precedes_dismissed_check_or_text(pending_engine):
    vm, run, pending = pending_engine
    vm.execute('''notification.GetPlayerID=function() return 1 end
        notification.IsDismissed=forbid;notification.GetID=forbid
        notification.GetMessage=forbid;notification.GetSummary=forbid''')
    assert "notification:81" not in pending()
    assert run(action_script({"type": "dismiss_notification", "notification_id": 81}))["accepted"] is False
    assert len(vm.globals().calls) == 0
