"""Own queued-goal observation never reads a path or hidden plot contents."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS, own_unit
from civ6_fair_mcp.extensions.queued_destination import QUEUED_DESTINATION_OBSERVATION
from civ6_fair_mcp.inspection_policy import public_inspection
from test_extension_units import engine


@pytest.fixture
def queued_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
rawget=nil;table.unpack=nil;unpack=nil
settings={owner=0,busy=false,goal=12,visible=true,revealed=true,valid=true,x=2,y=1}
reads={secret=0,goal=0,plot=0,coordinate=0,visibility=0,revealed=0}
function secret() reads.secret=reads.secret+1;error("SECRET_OR_UNSUPPORTED") end
unit=setmetatable({GetOwner=function() return settings.owner end,
    GetID=function() assert(settings.owner==0);return 10 end,
    GetUnitType=function() assert(settings.owner==0);return 7 end},{__index=secret})
foreign=setmetatable({GetOwner=function() return 1 end},{__index=secret})
player={GetUnits=function() return {Members=function()
    local rows={foreign,unit};local i=0
    return function() i=i+1;if rows[i] then return i,rows[i] end end
end} end}
UI={IsGameCoreBusy=function() return settings.busy end}
GameInfo={Units={[7]={IgnoreMoves=false}}}
UnitManager={GetQueuedDestination=function(actor)
    assert(actor==unit and settings.owner==0);reads.goal=reads.goal+1;return settings.goal
end,GetMoveToPathEx=secret,GetMovementPath=secret,RequestOperation=secret,RequestCommand=secret}
vis={IsVisible=function(self,id,y)
    assert(id==settings.goal and y==nil);reads.visibility=reads.visibility+1;return settings.visible
end,IsRevealed=function(self,id,y)
    assert(id==settings.goal and y==nil);reads.revealed=reads.revealed+1;return settings.revealed
end}
plot=setmetatable({GetX=function() reads.coordinate=reads.coordinate+1;return settings.x end,
    GetY=function() reads.coordinate=reads.coordinate+1;return settings.y end},{__index=secret})
Map={IsPlot=function(id) assert(id==settings.goal);return settings.valid end,
    GetGridSize=function() return 10,8 end,
    GetPlotByIndex=function(id)
        assert(id==settings.goal and settings.visible==true and settings.revealed==true)
        reads.plot=reads.plot+1;return plot
    end,GetPlot=secret,GetPlotDistance=secret}
''')

    def run(unit_id=10):
        result = vm.execute("local me=0;local out={items={},supported=true};\n" + LUA_HELPERS
            + "\nlocal function collect()\n" + own_unit(unit_id) + QUEUED_DESTINATION_OBSERVATION
            + "\nend\ncollect()\nreturn out")
        raw = {"ok": True, "session": "queued_destination_tests", "player_id": 0, "turn": 95,
            "active_turn": True, "category": "unit_details", "supported": True,
            "items": [dict(item) for item in result["items"].values()]}
        public = public_inspection(raw, "unit_details")
        assert vm.globals().reads.secret == 0
        assert all("action" not in item for item in public["items"])
        return {item["id"]: item["value"] for item in public["items"]}

    return vm, run


def test_visible_goal_returns_only_status_and_coordinates(queued_engine):
    vm, run = queued_engine
    assert run() == {"queued_destination": "visible", "queued_destination_x": 2, "queued_destination_y": 1}
    assert vm.globals().reads.goal == 1
    assert vm.globals().reads.plot == 1 and vm.globals().reads.coordinate == 2


@pytest.mark.parametrize("change", ["settings.visible=false", "settings.revealed=false"])
def test_fog_goal_is_present_but_never_constructs_a_plot_or_reads_path(queued_engine, change):
    vm, run = queued_engine
    vm.execute(change + ";Map.GetPlotByIndex=secret;Map.GetGridSize=secret")
    assert run() == {"queued_destination": "hidden"}
    assert vm.globals().reads.goal == 1
    assert vm.globals().reads.plot == 0 and vm.globals().reads.coordinate == 0


@pytest.mark.parametrize("goal", ["nil", "false", "-1", "-99", "'12'", "12.5", "0/0", "math.huge", "{}"])
def test_unproven_empty_or_invalid_native_goal_is_unknown_not_no_queue(queued_engine, goal):
    vm, run = queued_engine
    vm.execute(f"settings.goal={goal};Map.IsPlot=secret;vis.IsVisible=secret")
    assert run() == {"queued_destination": "unknown"}
    assert vm.globals().reads.plot == 0


@pytest.mark.parametrize("change", [
    "settings.busy=true", "settings.busy=nil", "settings.busy=0", "UI=nil",
    "UI.IsGameCoreBusy=nil", "UI.IsGameCoreBusy=function() error('UNPUBLIC_ERROR') end",
    "GameInfo.Units[7].IgnoreMoves=true", "GameInfo.Units[7].IgnoreMoves=1",
    "GameInfo.Units[7].IgnoreMoves='unknown'", "GameInfo.Units[7]=nil", "GameInfo=nil",
])
def test_busy_missing_capability_and_ignore_moves_are_unknown_before_goal_read(queued_engine, change):
    vm, run = queued_engine
    vm.execute(change + ";UnitManager.GetQueuedDestination=secret")
    assert run() == {"queued_destination": "unknown"}
    assert vm.globals().reads.goal == 0 and vm.globals().reads.plot == 0


@pytest.mark.parametrize("change", [
    "UnitManager=nil", "UnitManager.GetQueuedDestination=nil",
    "UnitManager.GetQueuedDestination=function() error('UNPUBLIC_ERROR') end",
    "Map.IsPlot=nil", "Map.IsPlot=function() error('UNPUBLIC_ERROR') end",
    "settings.valid=false", "settings.valid=nil", "settings.valid=1",
    "vis=nil", "vis.IsVisible=nil", "vis.IsRevealed=nil",
    "settings.visible=nil", "settings.visible=1", "settings.revealed=nil", "settings.revealed=1",
    "Map.GetPlotByIndex=nil", "Map.GetGridSize=nil",
    "Map.GetPlotByIndex=function() return nil end",
    "Map.GetGridSize=function() return 0,8 end",
    "settings.x=-1", "settings.x=10", "settings.x=2.5", "settings.y=8", "settings.y=nil",
])
def test_optional_failures_do_not_claim_no_goal_or_return_partial_coordinates(queued_engine, change):
    vm, run = queued_engine
    vm.execute(change)
    assert run() == {"queued_destination": "unknown"}


@pytest.mark.parametrize("ignore", ["nil", "false", "0"])
def test_stock_default_ignore_moves_keeps_normal_goal_observation(queued_engine, ignore):
    vm, run = queued_engine
    vm.execute(f"GameInfo.Units[7].IgnoreMoves={ignore}")
    assert run()["queued_destination"] == "visible"


@pytest.mark.parametrize("change,unit_id", [("settings.owner=1", 10), ("", 11)])
def test_foreign_or_missing_actor_never_reads_its_id_location_or_queued_goal(queued_engine, change, unit_id):
    vm, run = queued_engine
    vm.execute(change + ";UnitManager.GetQueuedDestination=secret")
    assert run(unit_id) == {}
    assert vm.globals().reads.goal == 0 and vm.globals().reads.plot == 0


def test_zero_plot_id_is_a_valid_goal_not_a_false_empty_sentinel(queued_engine):
    vm, run = queued_engine
    vm.execute("settings.goal=0;settings.x=0;settings.y=0")
    assert run() == {"queued_destination": "visible", "queued_destination_x": 0, "queued_destination_y": 0}


@pytest.mark.parametrize("activity", ["ACTIVITY_AWAKE", "ACTIVITY_HOLD", "ACTIVITY_OPERATION", "ACTIVITY_SLEEP"])
def test_registered_unit_details_keeps_activity_separate_from_queued_goal(engine, activity):
    vm, run = engine
    vm.execute(f'ActivityTypes={{ {activity}=4 }};UnitManager.GetActivityType=function() return 4 end')
    vm.execute('''
UI.IsGameCoreBusy=function() return false end
UnitManager.GetQueuedDestination=function(actor) assert(actor==unit);return 203 end
Map.IsPlot=function(id) assert(id==203);return true end
Map.GetPlotByIndex=function(id) assert(id==203);return {GetX=function() return 3 end,GetY=function() return 2 end} end
UnitManager.GetMoveToPathEx=forbidden
''')
    values = {item["id"]: item["value"] for item in run("unit_details", {"unit_id": 10}, True)["items"]}
    assert values["activity"] == activity and values["activity_type"] == 4
    assert values["queued_destination"] == "visible"
    assert values["queued_destination_x"] == 3 and values["queued_destination_y"] == 2
    assert not {"is_auto_exploring", "autoexploring", "current_operation", "needs_orders"} & values.keys()
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("change", [
    "",  # The older native fixture has no busy/queued-goal API.
    "UI.IsGameCoreBusy=function() return true end;UnitManager.GetQueuedDestination=forbidden",
    "UI.IsGameCoreBusy=function() return false end;Map.IsPlot=function() return true end;"
    "UnitManager.GetQueuedDestination=function() error('UNPUBLIC_ERROR') end",
])
def test_new_optional_failure_preserves_existing_unit_details(engine, change):
    vm, run = engine
    vm.execute(change)
    values = {item["id"]: item["value"] for item in run("unit_details", {"unit_id": 10}, True)["items"]}
    assert values["queued_destination"] == "unknown"
    assert values["combat"] == 20
