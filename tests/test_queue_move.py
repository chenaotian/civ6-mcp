"""Fixed long-range orders cannot probe hidden targets or silently replay."""
import pytest

from civ6_fair_mcp.actions import validate_action
from civ6_fair_mcp.extensions import registries
from test_actions import action_script, engine


GOAL = {"type": "queue_move", "unit_id": 70001, "x": 90, "y": 70}


@pytest.fixture
def queue_engine(engine):
    vm, run = engine
    vm.execute('''
rawget=nil;table.unpack=nil;unpack=nil
controls.core_busy=false;controls.target_x=90;controls.target_y=70
local _,actor=Players[0]:GetUnits():Members()()
queue_actor=actor
actor.GetUnitType=function() assert(controls.owner==0);return 7 end
GameInfo.Units[7]={Domain="DOMAIN_LAND",IgnoreMoves=false}
UI.IsGameCoreBusy=function() return controls.core_busy end
PlayersVisibility[0].IsVisible=forbid
PlayersVisibility[0].IsRevealed=function(self,x,y)
    assert(x==controls.target_x and y==controls.target_y);return controls.revealed
end
Map.GetPlotDistance=forbid
UnitManager.CanStartOperation=forbid
UnitManager.GetMoveToPathEx=forbid
UnitManager.GetMovementPath=forbid
UnitManager.GetQueuedDestination=forbid
UnitManager.RequestCommand=forbid
''')
    return vm, run


@pytest.mark.parametrize("request_result", [True, False, "error"])
def test_revealed_fog_long_goal_has_identical_submission_result_without_target_probe(queue_engine, request_result):
    vm, run = queue_engine
    vm.globals().controls.visible = False
    vm.globals().controls.request_result = request_result
    result = run(action_script(GOAL))
    assert result == {"ok": True, "session": "test_nonce", "player_id": 0,
        "turn": 7, "active_turn": True, "accepted": True}
    assert vm.globals().reads.can_unit == 0 and len(vm.globals().calls) == 1
    request = vm.globals().calls[1]
    assert request.operation == 100 and request.entity == 70001
    assert dict(request.params) == {"x": 90, "y": 70, "modifiers": 16}


@pytest.mark.parametrize("domain", ["DOMAIN_LAND", "DOMAIN_SEA"])
@pytest.mark.parametrize("ignore", ["nil", "false", "0"])
def test_normal_land_and_naval_units_use_native_goal_request(queue_engine, domain, ignore):
    vm, run = queue_engine
    vm.execute(f'GameInfo.Units[7]={{Domain="{domain}",IgnoreMoves={ignore}}}')
    assert run(action_script(GOAL))["accepted"] is True
    assert len(vm.globals().calls) == 1


@pytest.mark.parametrize("revealed", [False, None, 1, "true"])
def test_unexplored_or_unknown_revelation_rejects_before_native_request(queue_engine, revealed):
    vm, run = queue_engine
    vm.globals().controls.revealed = revealed
    assert run(action_script(GOAL))["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_foreign_actor_is_rejected_before_any_own_actor_field(queue_engine):
    vm, run = queue_engine
    vm.globals().controls.owner = 1
    vm.execute("queue_actor.GetUnitType=forbid")
    assert run(action_script(GOAL))["accepted"] is False
    assert vm.globals().reads.unit_fields == 0 and len(vm.globals().calls) == 0


@pytest.mark.parametrize("change", [
    "controls.unit_exists=false", "controls.moves=0", "controls.moves=-1", "controls.moves=0/0",
    "controls.moves=math.huge", "controls.tactical=false", "controls.core_busy=true",
    "controls.core_busy=nil", "controls.busy=true", "controls.active=false", "controls.complete=false",
    "UI.IsGameCoreBusy=nil", "UnitManager.RequestOperation=nil", "Map.GetGridSize=nil",
    "GameInfo.Units[7]=nil",
    "GameInfo.Units[7].Domain='DOMAIN_AIR'", "GameInfo.Units[7].Domain='UNKNOWN'",
    "GameInfo.Units[7].IgnoreMoves=true", "GameInfo.Units[7].IgnoreMoves=1",
    "GameInfo.Units[7].IgnoreMoves='unknown'", "UnitOperationTypes.MOVE_TO=nil",
    "UnitOperationTypes.PARAM_MODIFIERS=nil", "UnitOperationMoveModifiers.NONE=1",
    "UnitOperationMoveModifiers.MOVE_IGNORE_UNEXPLORED_DESTINATION=nil",
    "UnitOperationMoveModifiers.MOVE_IGNORE_UNEXPLORED_DESTINATION=-1",
    "Map.GetGridSize=function() return 4097,80 end",
    "queue_actor.GetX=function() return -1 end",
    "UIManager={GetModalContexts=function() return {true} end}",
])
def test_public_readiness_and_capability_failures_never_dispatch(queue_engine, change):
    vm, run = queue_engine
    vm.execute(change)
    assert run(action_script(GOAL))["accepted"] is False
    assert len(vm.globals().calls) == 0


def test_missing_visibility_capability_is_rejected_by_the_shared_player_envelope(queue_engine):
    vm, run = queue_engine
    vm.execute("PlayersVisibility[0].IsRevealed=nil")
    result = run(action_script(GOAL))
    assert result["ok"] is False and "accepted" not in result
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("target", [{"x": 2, "y": 2}, {"x": 100, "y": 70}, {"x": 90, "y": 80}])
def test_same_plot_and_out_of_bounds_goal_reject_before_visibility_probe(queue_engine, target):
    vm, run = queue_engine
    vm.execute("PlayersVisibility[0].IsRevealed=forbid")
    assert run(action_script({**GOAL, **target}))["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("metadata", [{"expected_session": "stale"}, {"expected_player": 1}, {"expected_turn": 6}])
def test_current_session_player_and_turn_are_required(queue_engine, metadata):
    vm, run = queue_engine
    assert run(action_script(GOAL, **metadata))["accepted"] is False
    assert len(vm.globals().calls) == 0 and vm.globals().reads.unit_fields == 0


def test_neighbor_goal_is_allowed_but_old_move_still_has_its_own_distance_limit(queue_engine):
    vm, run = queue_engine
    vm.globals().controls.target_x = 3
    vm.globals().controls.target_y = 2
    assert run(action_script({**GOAL, "x": 3, "y": 2}))["accepted"] is True
    assert len(vm.globals().calls) == 1
    vm.execute("Map.GetPlotDistance=function() return 20 end")
    assert run(action_script({**GOAL, "type": "move"}))["accepted"] is False
    assert len(vm.globals().calls) == 1


@pytest.mark.parametrize("change", [
    {"x": True}, {"x": -1}, {"x": 4096}, {"y": 1.5}, {"unit_id": "70001"},
    {"player_id": 0}, {"modifiers": 1}, {"path": []}, {"force": True},
])
def test_fixed_action_schema_rejects_coercions_flags_paths_and_extra_fields(change):
    with pytest.raises(ValueError):
        validate_action({**GOAL, **change})


def test_queue_move_is_registered_as_an_ordinary_turn_action():
    actions, _ = registries()
    assert actions["queue_move"].turn_mode == "turn"
    assert validate_action(GOAL) == GOAL
