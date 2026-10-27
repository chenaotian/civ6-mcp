"""Exploration pages depend on visibility labels, never hidden map contents."""
import copy
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions import build_inspection_query
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import PolicyError


@pytest.fixture
def engine():
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(r'''
reads={forbidden=0,adjacency=0,visibility=0}
settings={width=4,height=2,busy=false,all_revealed=false}
function forbidden() reads.forbidden=reads.forbidden+1;error('SECRET CONTENT') end
GameConfiguration={IsAnyMultiplayer=function() return false end,IsHotseat=function() return false end,
 IsWorldBuilderEditor=function() return false end}
Automation={IsActive=function() return false end}
Events={LoadGameViewStateDone={Add=function() end},LocalPlayerChanged={Add=function() end}}
UI={IsProcessingMessages=function() return false end,IsGameCoreBusy=function() return settings.busy end}
local player={IsAlive=function() return true end,IsHuman=function() return true end,
 IsTurnActive=function() return true end,IsTurnActiveComplete=function() return true end}
Players=setmetatable({[0]=player},{__index=forbidden})
Game={GetLocalPlayer=function() return 0 end,GetLocalObserver=function() return 0 end,
 GetCurrentGameTurn=function() return 30 end}
vis={IsRevealed=function(self,x,y) reads.visibility=reads.visibility+1
 return settings.all_revealed or x<2 end,
 IsVisible=function(self,x,y) return x==0 end}
PlayersVisibility={[0]=vis}
Map=setmetatable({GetGridSize=function() return settings.width,settings.height end,
 GetAdjacentPlot=function(x,y,d)
  reads.adjacency=reads.adjacency+1
  -- Fixture has a horizontal seam, with duplicate geometry on two hex edges.
  local dx=({1,1,0,-1,-1,0})[d+1]
  local dy=({0,1,1,0,-1,-1})[d+1]
  local ax=(x+dx)%settings.width;local ay=y+dy
  if ay<0 or ay>=settings.height then return nil end
  return setmetatable({GetX=function() return ax end,GetY=function() return ay end},{__index=forbidden})
 end},{__index=forbidden})
''')

    def run(offset=0):
        output = []
        runtime.globals().print = output.append
        runtime.execute(build_inspection_query("frontier_query_test", "exploration_frontier", {"offset": offset}))
        raw = json.loads(next(row.removeprefix("CIV6FAIR_JSON:") for row in output
                             if row.startswith("CIV6FAIR_JSON:")))
        assert raw["ok"] is True
        return raw, public_inspection(raw, "exploration_frontier", {"offset": offset})

    return runtime, run


def values(public):
    return {row["id"]: row["value"] for row in public["items"]}


def test_visible_and_fogged_explored_edges_keep_only_coordinates(engine):
    runtime, run = engine
    raw, public = run()
    assert raw["supported"] is True
    assert {(row["x"], row["y"], row["visible"]) for row in raw["items"]} == {
        (0, 0, True), (1, 0, False), (0, 1, True), (1, 1, False)}
    assert values(public)["next_offset"] == -1
    assert runtime.globals().reads.forbidden == 0
    assert runtime.globals().reads.adjacency == 24
    assert "SECRET" not in json.dumps(public)


def test_pagination_advances_even_without_any_boundary(engine):
    runtime, run = engine
    runtime.execute("settings.width=40;settings.height=30;settings.all_revealed=true")
    for start, next_offset in ((0, 512), (512, 1024), (1024, -1), (1200, -1)):
        raw, public = run(start)
        assert raw["supported"] is True and raw["items"] == []
        assert values(public) == {"next_offset": next_offset}
    assert runtime.globals().reads.adjacency == 1200 * 6


@pytest.mark.parametrize("setup,offset", [
    ("settings.busy=true", 0), ("Map.GetAdjacentPlot=false", 0),
    ("settings.width=4096;settings.height=4096", 0),
    ("settings.width=0", 0), ("settings.height=2.5", 0), ("", 9),
    ("vis.IsRevealed=function() return 1 end", 0),
    ("vis.IsVisible=function() return nil end", 0),
])
def test_unknown_or_unsupported_geometry_never_claims_empty_supported_result(engine, setup, offset):
    runtime, run = engine
    runtime.execute(setup)
    _, public = run(offset)
    assert public["supported"] is False and public["items"] == []


def test_ui_busy_transition_discards_partial_page(engine):
    runtime, run = engine
    runtime.execute("local old=Map.GetAdjacentPlot;Map.GetAdjacentPlot=function(...) settings.busy=true;return old(...) end")
    _, public = run()
    assert public["supported"] is False and public["items"] == []


@pytest.mark.parametrize("patch", [
    {"owner_id": True}, {"owner_id": 1}, {"source": "global_map"},
    {"offset": 1}, {"offset": False},
])
def test_invalid_proof_precedes_secret_record_validation(engine, patch):
    _, run = engine
    raw, _ = run()
    raw["frontier"].update(patch)
    raw["items"] = object()
    assert public_inspection(raw, "exploration_frontier", {"offset": 0})["items"] == []


def test_hidden_rows_are_dropped_before_content_validation(engine):
    _, run = engine
    raw, _ = run()
    raw["items"] = [{"revealed": False, "x": object()},
                    {"revealed": True, "adjacent_unrevealed": False, "y": object()}]
    assert values(public_inspection(raw, "exploration_frontier", {"offset": 0})) == {"next_offset": -1}


@pytest.mark.parametrize("mutation", [
    lambda r: r["frontier"].update(next_offset=0),
    lambda r: r["frontier"].update(width=True),
    lambda r: r["items"].append(copy.deepcopy(r["items"][0])),
    lambda r: r["items"][0].update(x=4),
    lambda r: r["items"][0].update(visible=1),
    lambda r: r["items"].extend([r["items"][0]] * 513),
])
def test_malformed_authorized_page_fails_closed(engine, mutation):
    _, run = engine
    raw, _ = run()
    mutation(raw)
    with pytest.raises(PolicyError):
        public_inspection(raw, "exploration_frontier", {"offset": 0})


def test_extra_map_and_resource_fields_never_survive_projection(engine):
    _, run = engine
    raw, public = run()
    for row in raw["items"]:
        row.update(resource="RESOURCE_URANIUM", hidden_unit={"owner": 63}, yields=999)
    raw["frontier"].update(ai_settle_score=999)
    assert public_inspection(raw, "exploration_frontier", {"offset": 0}) == public


def test_page_cannot_smuggle_other_page_coordinate(engine):
    runtime, run = engine
    runtime.execute("settings.width=40;settings.height=30")
    raw, _ = run(512)
    raw["items"] = [{"x": 0, "y": 0, "visible": True, "revealed": True, "adjacent_unrevealed": True}]
    with pytest.raises(PolicyError):
        public_inspection(raw, "exploration_frontier", {"offset": 512})
