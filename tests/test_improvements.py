"""Regression for visible tribal villages omitted during the first live game."""

import copy

import pytest

from civ6_fair_mcp.policy import public_map
from civ6_fair_mcp.queries import build_map_query
from test_queries import engine


@pytest.mark.parametrize("index, expected", [
    (0, "IMPROVEMENT_GOODY_HUT"),
    (1, "IMPROVEMENT_BARBARIAN_CAMP"),
    (2, "IMPROVEMENT_FARM"),
])
def test_visible_improvement_survives_lua_and_python_projection(engine, index, expected):
    lua, run = engine
    lua.globals().settings.improvement = index
    result = public_map(run(build_map_query("a" * 32, 1, 0, 2)))
    assert result["tiles"][2]["improvement"] == expected
    assert result["tiles"][2]["improvement_pillaged"] is False
    assert result["tiles"][0] == {"x": 0, "y": 0, "revealed": False, "visible": False}
    assert result["tiles"][1] == {"x": 1, "y": 0, "revealed": True, "visible": False}
    assert lua.globals().counts.hidden_reads == 0


def test_consumed_village_changes_to_confirmed_none(engine):
    lua, run = engine
    lua.globals().settings.improvement = 0
    assert public_map(run(build_map_query("a" * 32, 2, 0, 0)))["tiles"][0]["improvement"] == "IMPROVEMENT_GOODY_HUT"
    lua.globals().settings.improvement = -1
    tile = public_map(run(build_map_query("b" * 32, 2, 0, 0)))["tiles"][0]
    assert tile["improvement"] == "NONE"
    assert "improvement_pillaged" not in tile


def test_lost_visibility_does_not_read_or_update_village(engine):
    lua, run = engine
    lua.execute("settings.improvement = 0")
    run(build_map_query("a" * 32, 2, 0, 0))
    lua.execute("""
        visibility.IsVisible = function() return false end
        plots[2].GetImprovementType = function() error('HIDDEN VILLAGE CHANGE') end
        plots[2].IsImprovementPillaged = function() error('HIDDEN PILLAGE') end
    """)
    assert public_map(run(build_map_query("b" * 32, 2, 0, 0)))["tiles"] == [
        {"x": 2, "y": 0, "revealed": True, "visible": False}
    ]


@pytest.mark.parametrize("setup", [
    "plots[2].GetImprovementType = nil",
    "plots[2].GetImprovementType = function() error('engine detail') end",
    "settings.improvement = 999",
    "settings.improvement = -2",
    "settings.improvement = '0'",
    "settings.improvement = 0.5",
    "settings.improvement = 0; GameInfo.Improvements = nil",
])
def test_unavailable_improvement_is_unknown_not_none(engine, setup):
    lua, run = engine
    lua.execute(setup)
    tile = public_map(run(build_map_query("a" * 32, 2, 0, 0)))["tiles"][0]
    assert "improvement" not in tile
    assert "improvement_pillaged" not in tile


def test_pillaged_visible_farm(engine):
    lua, run = engine
    lua.execute("settings.improvement = 2; settings.pillaged = true")
    tile = public_map(run(build_map_query("a" * 32, 2, 0, 0)))["tiles"][0]
    assert tile["improvement_pillaged"] is True


@pytest.mark.parametrize("revealed", [False, True])
def test_python_drops_hidden_improvements_before_validation(revealed):
    raw = {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 8,
           "active_turn": True, "tiles": [
               {"x": 5, "y": 23, "revealed": revealed, "visible": False}]}
    changed = copy.deepcopy(raw)
    changed["tiles"][0].update(improvement={"bad": object()},
                               improvement_pillaged="malformed", goody_reward="secret")
    assert public_map(raw) == public_map(changed)


def test_python_never_exports_unapproved_village_rewards():
    raw = {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 8,
           "active_turn": True, "tiles": [
               {"x": 5, "y": 23, "revealed": True, "visible": True,
                "improvement": "IMPROVEMENT_GOODY_HUT", "goody_reward": "SECRET"}]}
    assert "goody_reward" not in public_map(raw)["tiles"][0]
