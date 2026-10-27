"""Waiting observes projected changes without replay, stale capability or raw leaks."""
import asyncio
import copy
import json

import pytest

from civ6_fair_mcp.service import FairGameService
from civ6_fair_mcp.waiting import fingerprint
from test_service import FakeTransport, raw
from test_ui_monitoring import UITransport, observed, popup


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr("civ6_fair_mcp.waiting.POLL_SECONDS", 0.003)


class RepeatingTransport(FakeTransport):
    async def execute(self, script, context="InGame", *, expected_generation=None):
        if len(self.responses) == 1:
            self.responses.append(copy.deepcopy(self.responses[0]))
        return await super().execute(script, context, expected_generation=expected_generation)


async def test_submitted_action_waits_through_old_public_state_and_never_replays():
    transport = FakeTransport(raw(), raw(accepted=True), raw(), raw(), raw(player={"gold": 75}),
                              raw(accepted=True))
    service = FairGameService(transport)
    first = await service.get_player_state()
    await service.act(first["observation_token"], {"type": "end_turn"})
    result = await service.wait_for_change(500)
    assert result["wait"]["reason"] == "observation_changed" and result["wait"]["changed"] is True
    assert result["player"]["gold"] == 75
    assert len(transport.calls) == 5
    assert sum("out.accepted" in script for script in transport.calls) == 1
    assert (await service.act(result["observation_token"], {"type": "end_turn"}))["accepted"] is True


async def test_unchanged_state_times_out_with_new_completed_observation_not_old_token():
    transport = RepeatingTransport(raw())
    service = FairGameService(transport)
    first = await service.get_player_state()
    result = await service.wait_for_change(25)
    assert result["wait"]["reason"] == "timeout" and result["wait"]["changed"] is False
    assert result["observation_token"] != first["observation_token"]
    assert service._observation.token == result["observation_token"]
    assert len(transport.calls) >= 2
    assert (await service.act(first["observation_token"], {"type": "end_turn"}))["error"] == "fresh_observation_required"


async def test_hidden_raw_updates_do_not_trigger_wait_or_enter_reference():
    baseline = raw(tiles=[{"secret": "OLD_HIDDEN"}], unknown="OLD_HIDDEN")
    changed = raw(tiles=[{"secret": "NEW_HIDDEN"}], unknown="NEW_HIDDEN")
    transport = RepeatingTransport(baseline, changed)
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.wait_for_change(20)
    assert result["wait"]["changed"] is False
    assert "HIDDEN" not in json.dumps(result)
    assert "HIDDEN" not in repr(service._last_read)
    assert not hasattr(service._last_read, "raw")


async def test_only_fog_details_change_does_not_wake_map_wait():
    tile = {"x": 1, "y": 1, "visible": False, "revealed": True, "resource": "SECRET"}
    transport = RepeatingTransport(raw(tiles=[tile]), raw(tiles=[{**tile, "resource": "CHANGED_SECRET"}]))
    service = FairGameService(transport)
    await service.observe_area(1, 1, 0)
    result = await service.wait_for_change(20)
    assert result["wait"]["changed"] is False
    assert result["tiles"] == [{"x": 1, "y": 1, "revealed": True, "visible": False}]


async def test_turn_change_keeps_legitimate_fresh_token():
    service = FairGameService(FakeTransport(raw(), raw(turn=11)))
    await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["turn"] == 11 and result["wait"]["reason"] == "turn_changed"
    assert result["wait"]["changed"] is True and service._observation.turn == 11
    assert "observation_token" in result


@pytest.mark.parametrize("change", [{"session": "b" * 32}, {"player_id": 1}])
async def test_new_session_or_player_does_not_inherit_wait_capability(change):
    service = FairGameService(FakeTransport(raw(), raw(**change)))
    await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["wait"]["reason"] == "session_changed"
    assert "observation_token" not in result and "token_scope" not in result
    assert "read_incomplete" not in result["wait"]
    assert service._observation is None and service._last_read is None
    assert (await service.wait_for_change(10))["error"] == "observation_required"


async def test_changed_generation_before_wait_never_dispatches():
    transport = FakeTransport(raw())
    service = FairGameService(transport)
    await service.get_player_state()
    transport.connection_generation += 1
    result = await service.wait_for_change(10)
    assert result["wait"]["reason"] == "connection_changed"
    assert len(transport.calls) == 1 and service._observation is None


async def test_popup_revision_rotation_is_not_public_ui_change_but_text_is():
    p1 = popup()
    p2 = copy.deepcopy(p1)
    p2["popup"]["revision"] = "POPUP_TEST_2"
    p3 = copy.deepcopy(p2)
    p3["popup"]["revision"] = "POPUP_TEST_3"
    p3["popup"]["content"] = ["另一个真实公开弹窗。"]
    transport = UITransport(observed(), p1, observed(), p2, observed(), p3)
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["wait"]["reason"] == "ui_changed" and len(transport.calls) == 6
    assert result["ui"]["popups"][0]["content"] == ["另一个真实公开弹窗。"]
    assert result["ui"]["popups"][0]["buttons"][0]["action"]["revision"] == "POPUP_TEST_3"


def test_fingerprint_ignores_collection_order_and_ephemeral_fields_only():
    a = {"items": [{"id": "B", "value": 1}, {"id": "A", "value": 2}],
         "observation_token": "first"}
    b = {"items": list(reversed(a["items"])), "observation_token": "second",
         "wait": {"elapsed_ms": 999}}
    assert fingerprint(a) == fingerprint(b)
    b["items"][0] = {"id": "A", "value": 3}
    assert fingerprint(a) != fingerprint(b)
    assert fingerprint({"content": ["A", "B"]}) != fingerprint({"content": ["B", "A"]})
    assert a["items"][0]["id"] == "B"  # no mutation of returned data


@pytest.mark.parametrize("method,args,extra", [
    ("get_player_state", (), {}),
    ("get_diplomacy", (), {"civilization_count": 1, "civilizations": []}),
    ("observe_area", (3, 4, 1), {"tiles": []}),
    ("list_options", ("research",), {"kind": "research", "options": []}),
    ("inspect_game", ("unit_details", {"unit_id": 7}), {"category": "unit_details", "supported": True, "items": []}),
    ("get_game_status", (), {"status": "playing"}),
])
async def test_wait_reuses_same_read_kind_and_schema(method, args, extra):
    service = FairGameService(FakeTransport(raw(**extra), raw(turn=11, **extra)))
    initial = await getattr(service, method)(*args)
    result = await service.wait_for_change(500)
    assert result.keys() - {"wait"} == initial.keys()
    assert result["turn"] == 11 and result["wait"]["reason"] == "turn_changed"
    assert service._last_read.request.args == (() if method in {"get_player_state", "get_diplomacy", "get_game_status"}
                                              else ("research", None) if method == "list_options" else args)


@pytest.mark.parametrize("timeout", [True, 0, -1, 10001, 1.5, "100", None])
async def test_invalid_budget_has_no_game_access(timeout):
    transport = FakeTransport()
    assert await FairGameService(transport).wait_for_change(timeout) == {"ok": False, "error": "invalid_input"}
    assert not transport.calls


async def test_no_observation_cannot_start_a_new_query_implicitly():
    transport = FakeTransport()
    result = await FairGameService(transport).wait_for_change(10)
    assert result["error"] == "observation_required" and not transport.calls


class BlockingTransport(FakeTransport):
    def __init__(self, *responses, block_at=2):
        super().__init__(*responses)
        self.block_at = block_at
        self.started = asyncio.Event()

    async def execute(self, script, context="InGame", *, expected_generation=None):
        if len(self.calls) + 1 == self.block_at:
            self.calls.append(script)
            self.started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await self.close()
                raise
        return await super().execute(script, context, expected_generation=expected_generation)


async def test_deadline_interrupts_in_flight_read_and_drops_capability():
    transport = BlockingTransport(raw())
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.wait_for_change(15)
    assert result["wait"]["reason"] == "timeout" and result["wait"]["read_incomplete"] is True
    assert "observation_token" not in result and service._observation is None
    assert service._last_read is None and transport.closed
    assert len(transport.calls) == 2


async def test_external_cancellation_during_read_clears_every_capability():
    transport = BlockingTransport(raw())
    service = FairGameService(transport)
    await service.get_player_state()
    task = asyncio.create_task(service.wait_for_change(10000))
    await transport.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service._observation is None and service._last_read is None
    assert transport.closed and not service._lock.locked()


async def test_cancellation_during_interval_does_not_leave_an_unreturned_token(monkeypatch):
    monkeypatch.setattr("civ6_fair_mcp.waiting.POLL_SECONDS", 1)
    transport = RepeatingTransport(raw())
    service = FairGameService(transport)
    await service.get_player_state()
    task = asyncio.create_task(service.wait_for_change(10000))
    while len(transport.calls) < 2:
        await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service._observation is None and service._last_read is None
    assert not transport.closed


@pytest.mark.parametrize("cancel", [False, True])
async def test_waiting_for_service_lock_cannot_invalidate_another_read(cancel):
    service = FairGameService(FakeTransport(raw()))
    first = await service.get_player_state()
    await service._lock.acquire()
    task = asyncio.create_task(service.wait_for_change(10))
    await asyncio.sleep(0)
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert (await task)["wait"]["reason"] == "timeout"
    assert service._observation.token == first["observation_token"]
    service._lock.release()


async def test_concurrent_old_action_cannot_slip_between_polls():
    transport = RepeatingTransport(raw())
    service = FairGameService(transport)
    old = (await service.get_player_state())["observation_token"]
    task = asyncio.create_task(service.wait_for_change(20))
    while len(transport.calls) < 2:
        await asyncio.sleep(0)
    action_task = asyncio.create_task(service.act(old, {"type": "end_turn"}))
    result = await task
    assert result["wait"]["reason"] == "timeout"
    assert (await action_task)["error"] == "fresh_observation_required"
    assert not any("out.accepted" in script for script in transport.calls)


async def test_cancelled_popup_read_never_returns_partially_combined_world_ui():
    class PopupBlock(BlockingTransport):
        supports_ui_contexts = True

    base = observed()
    base["popup_keys"] = ["boost", "secret_society"]
    second = popup()
    second["popup"]["id"] = "secret_society"
    changed = copy.deepcopy(base)
    changed["player"]["gold"] = 75
    # Baseline has both dialogs. During the poll, world and first dialog
    # complete but the second dialog never replies.
    transport = PopupBlock(base, popup(), second, changed, popup(), block_at=6)
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.wait_for_change(15)
    assert result["wait"]["read_incomplete"] is True
    assert "player" not in result and "ui" not in result and "observation_token" not in result
    assert service._last_read is None and transport.closed


async def test_read_interrupted_after_an_earlier_complete_poll_strips_that_token():
    transport = BlockingTransport(raw(), raw(), block_at=3)
    service = FairGameService(transport)
    await service.get_player_state()
    # Leave enough room for a second read based on the first fast sample.
    # Its unexpected stall must still hit the original hard deadline.
    result = await service.wait_for_change(150)
    assert result["ok"] is True and result["player"]["gold"] == 25
    assert result["wait"]["reason"] == "timeout" and result["wait"]["read_incomplete"] is True
    assert "observation_token" not in result
    assert service._observation is None and service._last_read is None


async def test_read_failure_recovery_cannot_reconnect_during_wait():
    class Disconnected(UITransport):
        def __init__(self):
            super().__init__(raw(popup_keys=[], ui_monitor_available=True))
            self.generations = []
            self.failed = False

        async def execute(self, script, context="InGame", *, expected_generation=None):
            self.generations.append(expected_generation)
            if len(self.generations) == 2:
                self.connection_generation += 1
                self.failed = True
                raise ConnectionError("SECRET_CONNECTION_DETAILS")
            if self.failed:
                assert expected_generation == 1
                raise ConnectionError("no reconnect permitted")
            return await super().execute(script, context, expected_generation=expected_generation)

    transport = Disconnected()
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.wait_for_change(500)
    assert result["ok"] is False and result["wait"]["reason"] == "unavailable"
    assert transport.generations == [None, 1, 1, 1]
    assert len(transport.calls) == 1 and service._observation is None
    assert "SECRET" not in json.dumps(result)


async def test_caller_mutating_returned_public_result_cannot_change_wait_baseline():
    transport = RepeatingTransport(raw())
    service = FairGameService(transport)
    initial = await service.get_player_state()
    initial["player"]["gold"] = 999
    result = await service.wait_for_change(15)
    assert result["wait"]["changed"] is False and result["player"]["gold"] == 25


async def test_low_tail_budget_keeps_last_complete_observation_without_opening_new_read():
    transport = BlockingTransport(raw(), raw(), block_at=3)
    service = FairGameService(transport)
    initial = await service.get_player_state()
    result = await service.wait_for_change(25)
    assert result["wait"]["reason"] == "timeout" and result["wait"]["changed"] is False
    assert "read_incomplete" not in result["wait"]
    assert result["observation_token"] != initial["observation_token"]
    assert service._observation.token == result["observation_token"]
    assert len(transport.calls) == 2 and not transport.started.is_set()
    assert not transport.closed


async def test_tail_budget_uses_measured_whole_read_cost():
    class SlowComplete(BlockingTransport):
        async def execute(self, script, context="InGame", *, expected_generation=None):
            if len(self.calls) == 1:
                await asyncio.sleep(0.04)
            return await super().execute(script, context, expected_generation=expected_generation)

    # After a 40ms observation there are about 60ms left: more than the fixed
    # 50ms margin, but less than 1.5 * measured read + 50ms. Do not start read 3.
    transport = SlowComplete(raw(), raw(), block_at=3)
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.wait_for_change(100)
    assert result["wait"]["reason"] == "timeout"
    assert "read_incomplete" not in result["wait"] and "observation_token" in result
    assert len(transport.calls) == 2 and not transport.closed


async def test_budget_rechecked_after_interval_before_new_read(monkeypatch):
    monkeypatch.setattr("civ6_fair_mcp.waiting.POLL_SECONDS", 0.04)
    transport = BlockingTransport(raw(), raw(), block_at=3)
    service = FairGameService(transport)
    await service.get_player_state()
    result = await service.wait_for_change(75)
    # Immediately after a fast observation 75ms is enough; after the 40ms
    # interval it is not. A check only before sleeping would open read 3.
    assert result["wait"]["reason"] == "timeout"
    assert "read_incomplete" not in result["wait"]
    assert len(transport.calls) == 2 and not transport.closed


async def test_tail_pause_cancellation_still_invalidates_completed_token():
    transport = BlockingTransport(raw(), raw(), block_at=3)
    service = FairGameService(transport)
    await service.get_player_state()
    task = asyncio.create_task(service.wait_for_change(45))
    while len(transport.calls) < 2:
        await asyncio.sleep(0)
    await asyncio.sleep(0.008)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service._observation is None and service._last_read is None
    assert len(transport.calls) == 2 and not transport.closed
