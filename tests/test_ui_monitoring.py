"""Production-style observations must surface already-open popup content/actions."""
import json
import pytest

from civ6_fair_mcp.service import FairGameService
from civ6_fair_mcp.ui_policy import public_popup
from civ6_fair_mcp.status import build_status_query, public_status
from test_service import FakeTransport, raw
from test_actions import engine


class UITransport(FakeTransport):
    supports_ui_contexts = True
    def __init__(self, *responses):
        super().__init__(*responses)
        self.contexts=[]
    async def execute(self, script, context="InGame", *, expected_generation=None):
        self.contexts.append(context)
        return await super().execute(script, context, expected_generation=expected_generation)


def observed(**extra):
    return raw(popup_keys=["boost"],ui_monitor_available=True,turn_blockers=[],**extra)


def popup(**extra):
    return raw(popup={"id":"boost","visible":True,"interactive":True,"modal":False,"revision":"POPUP_TEST_1",
        "content":["鼓舞！", "和其他城邦的交流让您对如何管理国民有了更明确的看法。", "您在政治哲学方面取得了很大进展。", "已获提升"],
        "buttons":[{"id":1,"label":"继续","enabled":True,"supported":True}],"private_queue":"SECRET"},**extra)


@pytest.mark.parametrize("method,args,extra", [
    ("get_player_state",(),{}),
    ("get_diplomacy",(),{"civilization_count":1,"civilizations":[]}),
    ("observe_area",(0,0),{"tiles":[]}),
    ("list_options",("research",),{"kind":"research","options":[]}),
    ("inspect_game",("pending_decisions",),{"category":"pending_decisions","supported":True,"items":[]}),
    ("get_game_status",(),{"status":"playing"}),
])
async def test_every_read_automatically_returns_popup_contents_and_working_action(method,args,extra):
    transport=UITransport(observed(**extra),popup(),raw(accepted=True))
    service=FairGameService(transport)
    result=await getattr(service,method)(*args)
    assert result["ui"]["status"]=="popup"
    p=result["ui"]["popups"][0]
    assert "您在政治哲学方面取得了很大进展。" in p["content"]
    assert "private_queue" not in p
    assert p["buttons"][0]["label"]=="继续"
    action=p["buttons"][0]["action"]
    assert (await service.act(result["observation_token"],action))["accepted"] is True
    assert transport.contexts==["InGame","BoostUnlockedPopup","BoostUnlockedPopup"]


async def test_inactive_popup_grants_only_ui_and_can_continue():
    service=FairGameService(UITransport(observed(active_turn=False),popup(active_turn=False),raw(accepted=True,active_turn=False)))
    result=await service.get_player_state()
    assert result["token_scope"]=="ui"
    action=result["ui"]["popups"][0]["buttons"][0]["action"]
    assert (await service.act(result["observation_token"],action))["accepted"] is True


async def test_world_read_failure_still_reports_visible_popup():
    service=FairGameService(UITransport(ValueError("bad world getter"),observed(),popup()))
    result=await service.get_player_state()
    assert result["ok"] is True and result["game_state_available"] is False
    assert result["ui"]["status"]=="popup"
    assert result["ui"]["popups"][0]["buttons"][0]["action"]["type"]=="popup_action"


async def test_cross_context_reload_never_combines_old_world_with_new_popup():
    other=popup(session="b"*32)
    recovery=observed(session="b"*32)
    service=FairGameService(UITransport(observed(),other,recovery,other))
    result=await service.get_player_state()
    assert result["game_state_available"] is False
    assert "player" not in result
    assert service._observation.session=="b"*32


async def test_popup_that_closed_between_discovery_and_read_returns_no_stale_content():
    hidden=raw(popup={"id":"boost","visible":False,"content":{"secret":True}})
    result=await FairGameService(UITransport(observed(),hidden)).get_player_state()
    assert result["ui"]["popups"]==[]


async def test_terminal_status_never_issues_capability_or_queries_world():
    service=FairGameService(UITransport(raw(status="defeated")))
    result=await service.get_game_status()
    assert result["status"]=="defeated" and "observation_token" not in result
    assert len(service.transport.calls)==1


def test_defeated_status_builder_does_not_enter_world_getters(engine):
    vm,run=engine
    vm.execute('Players[0].IsAlive=function() return false end; Players[0].GetUnits=forbid; Players[0].GetCities=forbid; Game.GetWinningTeam=forbid')
    result=run(build_status_query("a"*32))
    assert public_status(result)["status"]=="defeated"
    assert "units" not in result and "winner" not in result


def test_victory_status_hides_other_team_identity(engine):
    vm,run=engine
    vm.execute('Players[0].GetTeam=function() return 0 end; Game.GetWinningTeam=function() return 7, 99 end')
    result=public_status(run(build_status_query("a"*32)))
    assert result["status"]=="finished"
    assert "winning_team" not in result and "victory_type" not in result


async def test_active_game_token_cannot_reuse_unobserved_popup_revision():
    service=FairGameService(UITransport(raw(popup_keys=[],ui_monitor_available=True)))
    result=await service.get_player_state()
    action={"type":"popup_action","popup":"boost","button_id":1,"revision":"POPUP_OLD_1"}
    assert (await service.act(result["observation_token"],action))["error"]=="fresh_observation_required"
    assert len(service.transport.calls)==1


async def test_native_modal_restricts_even_active_turn_token():
    modal=popup()
    modal["popup"]["modal"]=True
    service=FairGameService(UITransport(observed(),modal))
    result=await service.get_player_state()
    assert result["active_turn"] is True and result["token_scope"]=="ui"
    assert (await service.act(result["observation_token"],{"type":"end_turn"}))["error"]=="fresh_observation_required"


def test_unsupported_or_occluded_ui_button_is_never_rebuilt_as_action():
    data=popup()
    data["popup"]["buttons"][0]["supported"]=False
    assert "action" not in public_popup(data,"boost")["buttons"][0]
    data["popup"]["buttons"][0]["supported"]=True
    data["popup"]["interactive"]=False
    assert "action" not in public_popup(data,"boost")["buttons"][0]


@pytest.mark.parametrize("popup_path", [
    "/InGame/InGamePopup/PopupRoot",
    "/InGame/Diplomacy/DiplomacyActionView/PopupRoot",
    "/InGame/Diplomacy/DiplomacyDealView/PopupRoot",
    "/InGame/Diplomacy/WorldCongressPopup/PopupRoot",
])
def test_new_confirmation_blocks_old_gameplay_request_before_world_getters(engine,popup_path):
    from test_actions import action_script, MOVE
    vm,run=engine
    vm.globals().blocking_path=popup_path
    vm.execute('''ContextPtr={LookUpControl=function(self,path)
        if path==blocking_path then return {IsVisible=function() return true end} end
    end}''')
    assert run(action_script(MOVE))["accepted"] is False
    assert vm.globals().reads.units==0


def test_native_modal_opened_after_observation_blocks_turn_action_before_getters(engine):
    from test_actions import action_script, MOVE
    vm,run=engine
    vm.execute('UIManager={GetModalContexts=function() return {"BoostUnlockedPopup"} end}')
    assert run(action_script(MOVE))["accepted"] is False
    assert vm.globals().reads.units==0


async def test_one_bad_popup_does_not_conceal_an_actionable_good_popup():
    initial=observed()
    initial["popup_keys"]=["artifact","boost"]
    service=FairGameService(UITransport(initial,ValueError("private engine detail"),popup()))
    result=await service.get_player_state()
    assert result["player"]["gold"]==25
    assert result["ui"]["status"]=="partial"
    assert result["ui"]["unavailable_popups"]==["artifact"]
    assert result["ui"]["popups"][0]["buttons"][0]["action"]["popup"]=="boost"
    assert "private engine detail" not in json.dumps(result)


@pytest.mark.parametrize("blockers", [[], ["ENDTURN_BLOCKING_CIVIC"]])
async def test_unknown_modal_cannot_be_reported_ready_or_only_decision_or_grant_token(blockers):
    initial=raw(popup_keys=[],ui_monitor_available=True,turn_blockers=blockers,
                native_modal_keys=[],native_modal_present=True,unknown_modal_present=True,
                modal_monitor_available=True)
    service=FairGameService(UITransport(initial))
    result=await service.get_player_state()
    assert result["ok"] is True and result["active_turn"] is True
    assert result["ui"]["status"] == "unavailable"
    assert result["ui"]["unknown_modal_present"] is True
    assert result["ui"]["modal_unavailable_reason"] == "unknown_native_modal"
    assert result["ui"]["turn_blockers"] == blockers
    assert "observation_token" not in result and service._observation is None
    assert service.transport.contexts == ["InGame"]


async def test_known_readable_native_modal_still_grants_its_normal_ui_response():
    initial=observed(native_modal_keys=["boost"],native_modal_present=True,
                     unknown_modal_present=False,modal_monitor_available=True)
    modal=popup()
    modal["popup"]["modal"]=True
    service=FairGameService(UITransport(initial,modal,raw(accepted=True)))
    result=await service.get_player_state()
    assert result["ui"]["status"] == "popup"
    assert result["token_scope"] == "ui"
    assert "modal_unavailable_reason" not in result["ui"]
    action=result["ui"]["popups"][0]["buttons"][0]["action"]
    assert (await service.act(result["observation_token"],action))["accepted"] is True


async def test_unknown_modal_preserves_readable_content_but_not_a_capability_through_the_stack():
    initial=observed(native_modal_keys=["boost"],native_modal_present=True,
                     unknown_modal_present=True,modal_monitor_available=True)
    service=FairGameService(UITransport(initial,popup()))
    result=await service.get_player_state()
    assert result["ui"]["status"] == "partial"
    assert "鼓舞！" in result["ui"]["popups"][0]["content"]
    assert result["ui"]["modal_unavailable_reason"] == "unknown_native_modal"
    assert "observation_token" not in result and service._observation is None


@pytest.mark.parametrize("discovered", [False, True])
async def test_known_native_modal_missing_from_collector_is_explicitly_unreadable(discovered):
    initial=raw(popup_keys=["generic"] if discovered else [],ui_monitor_available=True,
                native_modal_keys=["generic"],native_modal_present=True,
                unknown_modal_present=False,modal_monitor_available=True)
    replies=[initial]
    if discovered:
        replies.append(raw(popup={"id":"generic","visible":False,"content":{"hidden":"SECRET"}}))
    service=FairGameService(UITransport(*replies))
    result=await service.get_player_state()
    assert result["ui"]["status"] == "unavailable"
    assert result["ui"]["modal_unavailable_reason"] == "native_modal_unreadable"
    assert result["ui"]["unavailable_popups"] == ["generic"]
    assert "observation_token" not in result and service._observation is None
    assert "SECRET" not in json.dumps(result)


@pytest.mark.parametrize("metadata,reason", [
    ({"modal_monitor_available":False}, "native_modal_state_unavailable"),
    ({"modal_monitor_available":True,"native_modal_present":True,"native_modal_keys":[]}, "native_modal_unreadable"),
])
async def test_missing_modal_capability_or_hidden_known_stack_is_not_a_false_ready(metadata,reason):
    service=FairGameService(UITransport(raw(popup_keys=[],ui_monitor_available=True,**metadata)))
    result=await service.get_player_state()
    assert result["ui"]["status"] == "unavailable"
    assert result["ui"]["modal_unavailable_reason"] == reason
    assert "observation_token" not in result and service._observation is None


async def test_fresh_empty_native_stack_clears_previous_unknown_modal_block():
    blocked=raw(popup_keys=[],ui_monitor_available=True,native_modal_keys=[],
                native_modal_present=True,unknown_modal_present=True,modal_monitor_available=True)
    ready=raw(popup_keys=[],ui_monitor_available=True,native_modal_keys=[],
              native_modal_present=False,unknown_modal_present=False,modal_monitor_available=True)
    service=FairGameService(UITransport(blocked,ready))
    assert "observation_token" not in await service.get_player_state()
    result=await service.get_player_state()
    assert result["ui"]["status"] == "ready" and "observation_token" in result
    assert "unknown_modal_present" not in result["ui"]
