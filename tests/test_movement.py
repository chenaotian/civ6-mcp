"""Native MOVE_TO preview: owned actor, visible route, no hidden plot inspection."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.movement import ACTIONS, QUERIES, unit_move_preview
from civ6_fair_mcp.inspection_policy import public_inspection


@pytest.fixture
def movement_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
-- The live Civ VI Lua runtime does not expose this standard Lua helper.
rawget=nil
reads={secret=0,path=0,plot=0,coordinate=0}
function secret() reads.secret=reads.secret+1;error("SECRET_PLOT_OR_FOREIGN") end
settings={owner=0,x=1,y=1,width=10,height=8,busy=false,distance=1}
hidden={};unrevealed={}
unit=setmetatable({GetOwner=function() return settings.owner end,
    GetID=function() assert(settings.owner==0);return 12 end,
    GetUnitType=function() assert(settings.owner==0);return 7 end,
    GetX=function() assert(settings.owner==0);return settings.x end,
    GetY=function() assert(settings.owner==0);return settings.y end},{__index=secret})
foreign=setmetatable({GetOwner=function() return 1 end},{__index=secret})
player=setmetatable({GetUnits=function() return {Members=function()
    local rows={foreign,unit};local i=0;return function() i=i+1;if rows[i] then return i,rows[i] end end
end} end},{__index=secret})
vis={IsVisible=function(self,x,y)
    local id=y and y*settings.width+x or x;return not hidden[id]
end,IsRevealed=function(self,x,y)
    local id=y and y*settings.width+x or x;return not unrevealed[id]
end}
function plot(id)
    assert(not hidden[id] and not unrevealed[id],"hidden plot object")
    reads.plot=reads.plot+1
    return setmetatable({GetIndex=function() return id end,
        GetX=function() reads.coordinate=reads.coordinate+1;return id%settings.width end,
        GetY=function() reads.coordinate=reads.coordinate+1;return math.floor(id/settings.width) end},
        {__index=secret})
end
Map=setmetatable({GetGridSize=function() return settings.width,settings.height end,
    GetPlotDistance=function() return settings.distance end,
    GetPlot=function(x,y) return plot(y*settings.width+x) end,
    GetPlotByIndex=function(id) return plot(id) end},{__index=secret})
path={plots={11,12},turns={0,1},entrancePortals={},exitPortals={}}
UnitManager=setmetatable({GetMoveToPathEx=function(actor,target_id)
    assert(actor==unit and settings.owner==0);assert(target_id==12)
    reads.path=reads.path+1;return path
end},{__index=secret})
UI={IsGameCoreBusy=function() return settings.busy end}
GameInfo=setmetatable({Units={[7]={IgnoreMoves=false}}},{__index=secret})
''')

    def run(unit_id=12, x=2, y=1):
        params=validate({"unit_id":unit_id,"x":x,"y":y},QUERIES["unit_move_preview"].fields)
        result=vm.execute("local me=0;local out={items={}};\n"+LUA_HELPERS
            +"\nlocal function collect()\n"+unit_move_preview(params)
            +"\nend\ncollect()\nreturn out")
        raw={"ok":True,"session":"movement_tests_own","player_id":0,"turn":80,
            "active_turn":True,"category":"unit_move_preview","supported":result["supported"],
            "items":[dict(item) for item in result["items"].values()]}
        projected=public_inspection(raw,"unit_move_preview")
        assert vm.globals().reads.secret==0
        return projected,{item["id"]:item["value"] for item in projected["items"]}
    return vm,run


def test_direct_visible_path_reports_native_first_step_and_turn_without_action(movement_engine):
    vm,run=movement_engine
    result,values=run()
    assert result["supported"] is True
    assert values=={"status":"direct","first_step_x":2,"first_step_y":1,"arrival_turn":1}
    assert all("action" not in row for row in result["items"])
    assert vm.globals().reads.path==1 and vm.globals().reads.coordinate==2


def test_adjacent_target_can_have_a_visible_reverse_first_step_and_detour(movement_engine):
    vm,run=movement_engine
    vm.execute("path.plots={11,10,20,21,22,12};path.turns={0,1,1,2,2,3}")
    result,values=run()
    assert result["supported"] is True
    assert values=={"status":"detour","first_step_x":0,"first_step_y":1,"arrival_turn":3}
    assert vm.globals().reads.coordinate==2
    assert not any(key in values for key in ("plots","steps","length","path"))


@pytest.mark.parametrize("route,turns,status",[
    ("{11,12}","{0,1}","direct"),
    ("{11,21,22,12}","{0,1,2,2}","detour"),
])
def test_real_game_lua_without_rawget_still_validates_dense_paths(movement_engine,route,turns,status):
    vm,run=movement_engine
    vm.execute(f"rawget=nil;path.plots={route};path.turns={turns}")
    result,values=run()
    assert result["supported"] is True and values["status"]==status
    assert "arrival_turn" in values


def test_sparse_array_detection_does_not_invoke_missing_index_metamethod(movement_engine):
    vm,run=movement_engine
    vm.execute("rawget=nil;path.plots=setmetatable({[1]=11,[3]=12},{__index=secret})")
    result,values=run()
    assert result["supported"] is False and values=={}
    assert vm.globals().reads.coordinate==0


@pytest.mark.parametrize("plots",["{}","{11}"])
def test_empty_or_origin_only_native_path_is_no_path(movement_engine,plots):
    vm,run=movement_engine
    vm.execute(f"path.plots={plots};path.turns={{}}")
    result,values=run()
    assert result["supported"] is True and values=={"status":"no_path"}
    assert vm.globals().reads.coordinate==0


@pytest.mark.parametrize("change",[
    "hidden[12]=true", "unrevealed[12]=true", "hidden[11]=true", "unrevealed[11]=true",
    "settings.distance=0", "settings.busy=true",
])
def test_target_visibility_same_tile_and_busy_gates_precede_pathfinder(movement_engine,change):
    vm,run=movement_engine
    vm.execute(change)
    result,values=run()
    assert result["supported"] is True and values=={"status":"unknown"}
    assert vm.globals().reads.path==0 and vm.globals().reads.plot==0


def long_route(vm):
    vm.execute('''
Map.GetPlotDistance=function(x,y,tx,ty) return math.abs(x-tx)+math.abs(y-ty) end
UnitManager.GetMoveToPathEx=function(actor,target_id)
 assert(actor==unit and settings.owner==0 and target_id==14)
 reads.path=reads.path+1;return path
end
path={plots={11,12,13,14},turns={0,1,2,2},entrancePortals={},exitPortals={}}
''')


def test_distant_visible_route_uses_native_turns_and_only_first_step(movement_engine):
    vm,run=movement_engine
    long_route(vm)
    result,values=run(x=4)
    assert result["supported"] is True
    assert values=={"status":"route","first_step_x":2,"first_step_y":1,"arrival_turn":2}
    assert vm.globals().reads.coordinate==2
    assert not any("action" in row for row in result["items"])


@pytest.mark.parametrize("gate", ["hidden[13]=true", "unrevealed[13]=true"])
def test_distant_path_with_fog_hides_even_visible_prefix_and_turns(movement_engine,gate):
    vm,run=movement_engine
    long_route(vm)
    vm.execute("path={plots={11,12,13,14}};setmetatable(path,{__index=secret});"+gate)
    result,values=run(x=4)
    assert result["supported"] is True and values=={"status":"unknown"}
    assert vm.globals().reads.coordinate==0


@pytest.mark.parametrize("plots", ["{}", "{11}", "{11,12}"])
def test_distant_missing_or_partial_route_never_reports_hidden_reachability(movement_engine,plots):
    vm,run=movement_engine
    long_route(vm)
    vm.execute("path.plots="+plots)
    result,values=run(x=4)
    assert result["supported"] is True and values=={"status":"unknown"}
    assert vm.globals().reads.coordinate==0


def test_shorter_than_native_geometric_distance_is_invalid_not_teleport(movement_engine):
    vm,run=movement_engine
    long_route(vm)
    vm.execute("path.plots={11,14}")
    result,values=run(x=4)
    assert result["supported"] is False and values=={}


@pytest.mark.parametrize("distance", ["nil", "false", "-1", "0/0", "1.5", "8193"])
def test_invalid_native_distance_does_not_probe_pathfinder(movement_engine,distance):
    vm,run=movement_engine
    vm.execute("settings.distance="+distance)
    result,values=run()
    assert result["supported"] is False and values=={}
    assert vm.globals().reads.path==0


@pytest.mark.parametrize("change",[
    "settings.owner=1;unit.GetID=secret;unit.GetX=secret;unit.GetY=secret",
    "unit.GetID=function() return 99 end;unit.GetX=secret;unit.GetY=secret",
])
def test_other_or_missing_unit_is_rejected_before_location_read(movement_engine,change):
    vm,run=movement_engine
    vm.execute(change)
    result,values=run()
    assert result["supported"] is False and values=={}
    assert vm.globals().reads.path==0 and vm.globals().reads.plot==0


@pytest.mark.parametrize("ignore",["true","1"])
def test_stock_ignore_moves_units_never_probe_the_pathfinder(movement_engine,ignore):
    vm,run=movement_engine
    vm.execute(f"GameInfo.Units[7].IgnoreMoves={ignore};unit.GetX=secret;unit.GetY=secret")
    result,values=run()
    assert result["supported"] is True and values=={"status":"unknown"}
    assert vm.globals().reads.path==0 and vm.globals().reads.plot==0


@pytest.mark.parametrize("ignore",["false","0","nil"])
def test_static_ignore_moves_false_or_default_allows_normal_preview(movement_engine,ignore):
    vm,run=movement_engine
    vm.execute(f"GameInfo.Units[7].IgnoreMoves={ignore}")
    _,values=run()
    assert values["status"]=="direct"


@pytest.mark.parametrize("change",[
    "GameInfo=nil", "GameInfo.Units=nil", "GameInfo.Units[7]=nil",
    "GameInfo.Units[7].IgnoreMoves='unknown'", "unit.GetUnitType=nil",
])
def test_missing_or_invalid_static_unit_capability_fails_closed(movement_engine,change):
    vm,run=movement_engine
    vm.execute("setmetatable(GameInfo,nil);setmetatable(unit,nil)")
    vm.execute(change)
    result,values=run()
    assert result["supported"] is False and values=={}
    assert vm.globals().reads.path==0 and vm.globals().reads.plot==0


@pytest.mark.parametrize("route",["{11,21,12}","{11,21,31,41,42,32,22,12}"])
@pytest.mark.parametrize("gate",["hidden[21]=true","unrevealed[21]=true"])
def test_any_fogged_path_is_unknown_without_geometry_length_or_estimate(movement_engine,route,gate):
    vm,run=movement_engine
    vm.execute(f"path={{plots={route}}};{gate}")
    # If the privacy gate fails, optional metadata must not even be inspected.
    vm.execute('setmetatable(path,{__index=secret})')
    result,values=run()
    assert result["supported"] is True and values=={"status":"unknown"}
    assert vm.globals().reads.plot==2 and vm.globals().reads.coordinate==0


def test_hidden_tail_does_not_leak_the_otherwise_visible_first_step(movement_engine):
    vm,run=movement_engine
    vm.execute("path.plots={11,21,22,12};hidden[22]=true")
    _,values=run()
    assert values=={"status":"unknown"}
    assert vm.globals().reads.coordinate==0


@pytest.mark.parametrize("side",["entrancePortals","exitPortals"])
def test_portal_transition_stays_unknown_without_inspecting_portal_plot(movement_engine,side):
    vm,run=movement_engine
    vm.execute(f"path.{side}={{[1]=50}};hidden[50]=true")
    result,values=run()
    assert result["supported"] is True and values=={"status":"unknown"}
    assert vm.globals().reads.plot==2 and vm.globals().reads.coordinate==0


@pytest.mark.parametrize("marker",["false","-1","-2","-2147483648","-0.5"])
def test_stock_false_or_negative_portal_markers_are_not_portal_transitions(movement_engine,marker):
    vm,run=movement_engine
    vm.execute(f"path.entrancePortals={{{marker},{marker}}};path.exitPortals={{{marker},{marker}}}")
    _,values=run()
    assert values["status"]=="direct"


@pytest.mark.parametrize("turns",["nil","{}","{0}","{0,-1}","{0,1.5}","{2,1}","{0,0}","{0,0/0}"])
def test_unavailable_or_malformed_optional_estimate_is_omitted(movement_engine,turns):
    vm,run=movement_engine
    vm.execute(f"path.turns={turns}")
    result,values=run()
    assert result["supported"] is True and values["status"]=="direct"
    assert "arrival_turn" not in values


@pytest.mark.parametrize("change",[
    "path=nil", "path.plots=nil", "path.plots={{11,1},{12,1}}", "path.plots={[1]=11,[3]=12}",
    "path.plots={11,80,12}", "path.plots={11,1.5,12}", "path.plots={11,0/0,12}",
    "path.plots={12,11}", "path.plots={11,21,11,12}", "path.plots={[0]=11,[1]=12}",
    "path.plots={};for i=1,4097 do path.plots[i]=11 end",
    "path.entrancePortals=nil", "path.exitPortals={[3]=-1}", "path.exitPortals={[1]='invalid'}",
    "path.exitPortals={[1]=true}", "path.exitPortals={[1]=-math.huge}", "path.exitPortals={[1]=0/0}",
    "settings.width=0", "settings.height=4097", "settings.x=-1", "settings.busy=nil",
    "Map.GetPlotByIndex=function() return {GetX=function() return 10 end,GetY=function() return 1 end} end",
])
def test_unknown_native_shapes_discard_all_partial_results(movement_engine,change):
    vm,run=movement_engine
    vm.execute(change)
    result,values=run()
    assert result["supported"] is False and values=={}


@pytest.mark.parametrize("change",[
    "Map.GetPlot=nil", "Map.GetPlotByIndex=nil", "Map.GetGridSize=nil", "Map.GetPlotDistance=nil",
    "UnitManager.GetMoveToPathEx=nil", "UI.IsGameCoreBusy=nil", "vis.IsVisible=nil", "vis.IsRevealed=nil",
    "UnitManager.GetMoveToPathEx=function() error('PRIVATE_NATIVE_FAILURE') end",
])
def test_required_api_missing_or_throwing_fails_closed(movement_engine,change):
    vm,run=movement_engine
    vm.execute("setmetatable(Map,nil);setmetatable(UnitManager,nil)")
    vm.execute(change)
    result,values=run()
    assert result["supported"] is False and values=={}


def test_native_partial_route_to_a_different_destination_is_unknown(movement_engine):
    vm,run=movement_engine
    vm.execute("path.plots={11,21};path.turns={0,1}")
    result,values=run()
    assert result["supported"] is True and values=={"status":"unknown"}
    assert vm.globals().reads.coordinate==0


def test_geometry_is_native_including_wrapped_first_step(movement_engine):
    vm,run=movement_engine
    vm.execute("settings.x=0;path.plots={10,19,29,28,18,12};path.turns={0,1,1,2,2,3}")
    _,values=run()
    assert values=={"status":"detour","first_step_x":9,"first_step_y":1,"arrival_turn":3}


@pytest.mark.parametrize("params",[
    {}, {"unit_id":12,"x":2}, {"unit_id":12,"x":True,"y":1},
    {"unit_id":12,"x":-1,"y":1}, {"unit_id":12,"x":4096,"y":1},
    {"unit_id":12,"x":2,"y":1,"player_id":1},
])
def test_fixed_preview_query_schema_is_not_an_action(params):
    assert "unit_move_preview" not in ACTIONS
    with pytest.raises(ValueError):
        validate(params,QUERIES["unit_move_preview"].fields)
