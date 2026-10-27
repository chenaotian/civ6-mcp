"""Public-only, non-causal turn feedback and fixed read suggestions."""
import copy
import json

import pytest

from civ6_fair_mcp.interaction_feedback import MAX_EVENTS, changes, next_steps, snapshot
from civ6_fair_mcp.service import FairGameService
from test_service import FakeTransport, raw
from test_ui_monitoring import UITransport


def unit(unit_id=1, **extra):
    return {"owner_id": 0, "id": unit_id, "type": "UNIT_WARRIOR", "x": 2, "y": 3,
            "damage": 0, **extra}


def city(city_id=1, **extra):
    return {"owner_id": 0, "id": city_id, "x": 1, "y": 1,
            "population": 2, "production": "BUILDING_MONUMENT", **extra}


async def test_wait_reports_own_changes_after_end_turn_without_completion_claim():
    before = raw(units=[unit()], cities=[city()], player={"gold": 25, "research": "TECH_MINING"})
    after = raw(turn=11, units=[unit(damage=20, x=3)],
                cities=[city(population=3, production="UNIT_SCOUT")], player={"gold": 30})
    transport = FakeTransport(before, raw(accepted=True), after)
    service = FairGameService(transport)
    initial = await service.get_player_state()
    assert (await service.act(initial["observation_token"], {"type": "end_turn"}))["status"] == "submitted"
    result = await service.wait_for_change(500)
    report = result["wait"]["changes"]
    assert (report["from_turn"], report["to_turn"]) == (10, 11)
    events = report["events"]
    assert any(e.get("field") == "damage" and e["after"] == 20 for e in events)
    assert any(e.get("field") == "production" and e["after"] == "UNIT_SCOUT" for e in events)
    research = next(e for e in events if e.get("field") == "research")
    assert research["before_known"] is True and research["after_known"] is False
    assert "after" not in research
    assert "completed" not in json.dumps(report) and "killed" not in json.dumps(report)
    assert len(transport.calls) == 3  # No hidden reads or automatic end-turn replay.


async def test_unit_replacement_does_not_claim_death_or_spawn_cause():
    service = FairGameService(FakeTransport(raw(units=[unit(1)]), raw(units=[unit(2)])))
    await service.get_player_state()
    report = (await service.wait_for_change(500))["wait"]["changes"]
    assert report["events"] == [
        {"kind": "no_longer_observed", "entity": "units", "id": 1, "cause": "unknown"},
        {"kind": "now_observed", "entity": "units", "id": 2, "cause": "unknown"},
    ]


async def test_returned_result_mutation_cannot_corrupt_snapshot():
    service = FairGameService(FakeTransport(raw(), raw(player={"gold": 30})))
    before = await service.get_player_state()
    before["player"]["gold"] = 999
    events = (await service.wait_for_change(500))["wait"]["changes"]["events"]
    assert next(e for e in events if e.get("field") == "gold")["before"] == 25


@pytest.mark.parametrize("extra", [{"session": "b" * 32}, {"player_id": 1}])
async def test_session_change_never_exports_cross_save_difference(extra):
    service = FairGameService(FakeTransport(raw(), raw(player={"gold": 999}, **extra)))
    await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["wait"]["reason"] == "session_changed"
    assert "changes" not in result["wait"] and "observation_token" not in result


async def test_generation_change_never_exports_cross_connection_difference():
    service = FairGameService(FakeTransport(raw()))
    await service.get_player_state()
    service.transport.connection_generation += 1
    result = await service.wait_for_change(500)
    assert "changes" not in result["wait"] and len(service.transport.calls) == 1


async def test_turn_rollback_with_unchanged_session_is_not_compared_and_clears_history():
    service = FairGameService(FakeTransport(raw(turn=10, player={"gold": 999}),
                                           raw(turn=9, player={"gold": 10})))
    await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["wait"]["reason"] == "session_changed"
    assert "changes" not in result["wait"] and "observation_token" not in result
    assert service._observation is None and service._last_read is None
    assert (await service.get_session_history())["entries"] == []


async def test_new_read_kind_replaces_baseline_instead_of_comparing_player_to_map():
    service = FairGameService(FakeTransport(raw(units=[unit()]), raw(tiles=[]), raw(turn=11, tiles=[])))
    await service.get_player_state()
    await service.observe_area(1, 1, 0)
    result = await service.wait_for_change(500)
    assert result["wait"]["changes"]["events"] == []
    assert "units" not in service._last_read.feedback


@pytest.mark.parametrize("kind", ["map", "diplomacy", "inspection", "options"])
def test_summary_never_retains_map_foreign_entities_or_executable_proofs(kind):
    data = {"player_id": 0, "turn": 10, "active_turn": True,
            "units": [unit(name="PRIVATE")], "tiles": [{"secret": "PRIVATE"}],
            "civilizations": [{"secret": "PRIVATE"}], "items": [{"action": {"signature": "PRIVATE"}}],
            "observation_token": "PRIVATE", "ui": {"status": "popup", "popups": [
                {"id": "boost", "content": ["PRIVATE"], "buttons": [{"action": {"revision": "PRIVATE"}}]}]}}
    result = snapshot(kind, data)
    assert "PRIVATE" not in repr(result)
    assert result["ui"]["popup_ids"] == ["boost"]


def test_own_snapshot_drops_foreign_entity_before_details():
    data = {"player_id": 0, "turn": 10, "active_turn": True,
            "units": [unit(), {"owner_id": 1, "damage": "PRIVATE"}], "cities": []}
    assert list(snapshot("player", data)["units"]) == [1]


def test_failed_world_read_is_not_reported_as_mass_loss():
    old = snapshot("player", {**raw(), "units": [unit()], "cities": [city()]})
    new = snapshot("player", {"turn": 11, "active_turn": True, "game_state_available": False})
    assert not any(e["kind"] == "no_longer_observed" for e in changes(old, new)["events"])


def test_change_report_is_bounded_and_detached_from_internal_snapshots():
    old = snapshot("player", {**raw(), "units": [unit(i) for i in range(200)]})
    new = copy.deepcopy(old)
    new["units"] = {}
    report = changes(old, new)
    assert len(report["events"]) == MAX_EVENTS and report["truncated"] is True
    report["events"][0]["id"] = 999
    assert 999 not in old["units"]


async def test_blocker_guidance_stays_read_only_and_preserves_unknown_blocker():
    transport = UITransport(raw(popup_keys=[], ui_monitor_available=True,
        turn_blockers=["ENDTURN_BLOCKING_RESEARCH", "UNKNOWN_BLOCKER"], engine_activity="busy"))
    result = await FairGameService(transport).get_player_state()
    steps = result["ui"]["next_steps"]
    assert steps == [
        {"reason": "turn_blocker", "blocker": "ENDTURN_BLOCKING_RESEARCH",
         "tool": "list_options", "args": {"kind": "research"}},
        {"reason": "turn_blocker", "blocker": "UNKNOWN_BLOCKER", "tool": "get_pending_decisions", "args": {}},
        {"reason": "engine_busy", "tool": "wait_for_change", "args": {}},
    ]
    assert len(transport.calls) == 1 and all("action" not in s for s in steps)


def test_unreadable_modal_and_unactionable_popup_never_invent_close():
    result = next_steps({"status": "partial", "popups": [{"id": "boost", "buttons": []}],
                         "turn_blockers": [], "engine_activity": "unknown"})
    assert result == [
        {"reason": "ui_incomplete", "tool": "get_game_status", "args": {}},
        {"reason": "visible_popup", "popup": "boost", "guidance": "refresh_before_response"},
    ]


async def test_terminal_transition_during_player_wait_returns_no_capability_or_mass_loss():
    service = FairGameService(FakeTransport(raw(units=[unit()]),
        raw(game_status="finished", status_reason="winning_team_confirmed", units=[unit()])))
    await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["status"] == "finished" and "units" not in result
    assert "observation_token" not in result and service._observation is None
    assert any(e.get("field") == "status" and e["after"] == "finished" for e in result["wait"]["changes"]["events"])
    assert not any(e["kind"] == "no_longer_observed" for e in result["wait"]["changes"]["events"])
