"""Execute terminal detection against hostile Lua fixtures and service paths."""
import json
import pytest

from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import PolicyError
from civ6_fair_mcp.service import FairGameService
from civ6_fair_mcp.status import build_status_query, public_status
from test_actions import engine
from test_service import FakeTransport, raw


@pytest.mark.parametrize("value", ["-1", "nil"])
def test_no_winner_sentinel_is_playing_without_reading_team_or_foreign_players(engine, value):
    vm, run = engine
    vm.execute(f"Game.GetWinningTeam=function() return {value} end; Players[0].GetTeam=forbid")
    assert public_status(run(build_status_query("a" * 32)))["status"] == "playing"


@pytest.mark.parametrize("value", ["false", "'0'", "-2", "0.5", "64", "0/0"])
def test_malformed_winner_is_unavailable_not_terminal_or_playing(engine, value):
    vm, run = engine
    vm.execute(f"Game.GetWinningTeam=function() return {value} end")
    assert run(build_status_query("a" * 32)) == {"ok": False, "error": "unavailable"}


@pytest.mark.parametrize("team,expected", [(0, "victorious"), (7, "finished")])
def test_confirmed_winner_exposes_only_local_result(engine, team, expected):
    vm, run = engine
    vm.execute(f"Game.GetWinningTeam=function() return {team}, 'SECRET_VICTORY_TYPE' end; Players[0].GetTeam=function() return 0 end")
    result = public_status(run(build_status_query("a" * 32)))
    assert result["status"] == expected and result["status_reason"] == "winning_team_confirmed"
    assert "winner" not in result and "victory_type" not in result


def test_eliminated_player_status_survives_missing_visibility_and_turn_ui(engine):
    vm, run = engine
    vm.execute('''Players[0].IsAlive=function() return false end
        Players[0].GetUnits=forbid; Players[0].GetCities=forbid; Game.GetWinningTeam=forbid
        PlayersVisibility=nil; UI=nil; Players[0].IsTurnActive=nil; Players[0].IsTurnActiveComplete=nil''')
    result = public_status(run(build_status_query("a" * 32)))
    assert result["status"] == "defeated" and result["status_reason"] == "local_player_eliminated"
    assert result["active_turn"] is False


@pytest.mark.parametrize("visible,expected", [("true", "finished"), ("false", "playing"), ("1", "playing"), ("nil", "playing")])
def test_only_strict_visible_end_game_context_is_terminal_evidence(engine, visible, expected):
    vm, run = engine
    vm.execute(f'''Game.GetWinningTeam=function() return -1 end
        ContextPtr={{LookUpControl=function(self,path)
            if path=="/InGame/EndGameMenu" then return {{IsVisible=function() return {visible} end,
                GetChildren=forbid, GetText=forbid}} end
        end}}''')
    result = public_status(run(build_status_query("a" * 32)))
    assert result["status"] == expected
    if expected == "finished":
        assert result["status_reason"] == "end_game_screen_visible"


def test_normal_observation_envelope_has_terminal_evidence_without_world_enumeration(engine):
    vm, run = engine
    vm.execute('''Game.GetWinningTeam=function() return 7 end; Players[0].GetTeam=function() return 0 end
        Players[0].GetUnits=forbid; Players[0].GetCities=forbid''')
    result = run(wrap("", "test_nonce"))
    assert result["game_status"] == "finished"


@pytest.mark.parametrize("field,value", [("Game.GetLocalObserver", "-1"),
    ("GameConfiguration.IsAnyMultiplayer", "true"), ("Automation.IsActive", "true")])
def test_terminal_status_does_not_relax_controller_guards(engine, field, value):
    vm, run = engine
    vm.execute(f"Players[0].IsAlive=function() return false end; {field}=function() return {value} end")
    assert run(build_status_query("a" * 32)) == {"ok": False, "error": "unavailable"}


@pytest.mark.parametrize("method,args", [("get_player_state", ()), ("get_diplomacy", ()),
    ("observe_area", (0,0,0)), ("list_options", ("research",)), ("inspect_game", ("pending_decisions",))])
async def test_terminal_read_short_circuits_world_projection_and_grants_no_token(method, args):
    transport = FakeTransport(raw(game_status="finished", status_reason="end_game_screen_visible", units="SECRET_INVALID"))
    service = FairGameService(transport)
    result = await getattr(service, method)(*args)
    assert result["status"] == "finished" and "units" not in result
    assert "observation_token" not in result and service._observation is None
    assert len(transport.calls) == 1


@pytest.mark.parametrize("category,params", [("district_preview", {"city_id": 1, "item": "DISTRICT_CAMPUS"}),
                                            ("deal_negotiation", {"target_player": 1})])
async def test_fixed_context_inspections_stop_after_terminal_anchor_without_context_query(category, params):
    transport = FakeTransport(raw(game_status="finished", status_reason="winning_team_confirmed"))
    service = FairGameService(transport)
    result = await service.inspect_game(category, params)
    assert result["status"] == "finished" and "observation_token" not in result
    assert len(transport.calls) == 1 and service._observation is None
    assert (await service.get_session_history())["entries"][-1]["status"] == "finished"


def test_status_reason_is_allowlisted():
    with pytest.raises(PolicyError):
        public_status(raw(status="finished", status_reason="SECRET"))


async def test_generated_lua_through_service_end_turn_wait_and_history(engine):
    vm, run = engine
    vm.execute('''controls.winner=-1
        Game.GetWinningTeam=function() return controls.winner end
        Players[0].GetTeam=function() return 0 end''')

    class LuaTransport:
        connection_generation = 1
        calls = 0

        async def execute(self, script, context="InGame", *, expected_generation=None):
            assert context == "InGame"
            assert expected_generation in (None, self.connection_generation)
            self.calls += 1
            return "CIV6FAIR_JSON:" + json.dumps(run(script)) + "\n---END---"

        async def close(self):
            self.connection_generation += 1

    transport = LuaTransport()
    service = FairGameService(transport)
    observed = await service.get_game_status()
    assert observed["status"] == "playing"
    assert (await service.act(observed["observation_token"], {"type": "end_turn"}))["status"] == "submitted"
    vm.execute("controls.winner=7")
    final = await service.wait_for_change(500)
    assert final["status"] == "finished" and "observation_token" not in final
    assert len(vm.globals().calls) == 1 and transport.calls == 3
    history = await service.get_session_history()
    assert [e["kind"] for e in history["entries"]] == ["observation", "action_request", "observation"]
    assert history["entries"][-1]["status"] == "finished"
