"""Exercise the stock envoy-considered acknowledgment in a real Lua VM."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.actions import validate_action
from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.diplomacy_actions import ACTIONS, QUERIES
from test_city_state_details import public_result, records
from test_extension_diplomacy_actions import CITY_STATE_SETUP, ENGINE, execute


SETUP = CITY_STATE_SETUP + r'''
strategic_allowed=true; considered=false; envoy_tokens=2; consideration_reads=0
Game.IsAllowStrategicCommands=function(id) assert(id==me);return strategic_allowed end
own_influence=player:GetInfluence()
own_influence.GetTokensToGive=function(self) assert(self==own_influence);return envoy_tokens end
own_influence.IsGivingTokensConsidered=function(self)
    assert(self==own_influence);consideration_reads=consideration_reads+1;return considered
end
own_influence.SetGivingTokensConsidered=function(self,value)
    assert(self==own_influence and value==true)
    considered=value;table.insert(calls,{'considered',value})
end
'''


def query(mutation=""):
    return execute("city_states", query=True, setup=SETUP + mutation)


def act(mutation=""):
    return execute("city_state_defer_envoys", setup=SETUP + mutation)


def test_query_offers_fixed_own_acknowledgment_and_public_schema_accepts_it():
    vm, out = query()
    item = records(out)["defer_envoys"]
    assert item["scope"] == "self" and item["owner_id"] == 0
    assert item["action"]["type"] == "city_state_defer_envoys"
    public = public_result(out)
    offer = next(row for row in public["items"] if row["id"] == "defer_envoys")
    assert offer["action"] == {"type": "city_state_defer_envoys"}
    assert vm.globals().considered is False
    assert len(vm.globals().calls) == 0


def test_action_acknowledges_only_own_consideration_without_spending_tokens():
    vm, out = act()
    assert out["accepted"] is True
    assert vm.globals().considered is True
    assert vm.globals().envoy_tokens == 2
    assert len(vm.globals().calls) == 1
    assert list(vm.globals().calls[1].values()) == ["considered", True]
    assert vm.globals().reads == 0
    assert vm.globals().citystate_reads.identity == 0
    assert vm.globals().citystate_reads.influence == 0


def test_acknowledgment_needs_no_met_or_eligible_foreign_target():
    mutation = r'''
known[1]=false
PlayerManager.GetAliveMinors=function() return {} end
own_influence.CanGiveTokensToPlayer=function() error('No foreign target is needed') end
'''
    vm, out = query(mutation)
    assert "defer_envoys" in records(out)
    assert vm.globals().reads == 0 and vm.globals().citystate_reads.identity == 0
    vm, out = act(mutation)
    assert out["accepted"] is True and len(vm.globals().calls) == 1


@pytest.mark.parametrize("mutation", [
    "considered=true",
    "considered=nil",
    "considered=0",
    "strategic_allowed=false",
    "strategic_allowed=1",
    "Game.IsAllowStrategicCommands=nil",
    "envoy_tokens=0",
    "envoy_tokens=-1",
    "envoy_tokens=1.5",
    "envoy_tokens=math.huge",
    "envoy_tokens=0/0",
    "envoy_tokens='2'",
    "own_influence.CanGiveInfluence=function() return false end",
    "own_influence.CanGiveInfluence=function() return 1 end",
    "own_influence.IsGivingTokensConsidered=nil",
    "own_influence.SetGivingTokensConsidered=nil",
    "own_influence.IsGivingTokensConsidered=function() error('state unavailable') end",
])
def test_query_and_action_share_current_eligibility_and_fail_closed(mutation):
    # Isolate the own reminder from the pre-existing foreign envoy menu's
    # assumptions about native token types; no target is needed to defer.
    _, out = query("\nPlayerManager.GetAliveMinors=function() return {} end\n" + mutation)
    assert "defer_envoys" not in records(out)
    vm, out = act("\n" + mutation)
    assert out["accepted"] is False
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("mutation", [
    "player.GetInfluence=nil",
    "player.GetInfluence=function() return nil end",
    "player.GetInfluence=function() return false end",
    "player.GetInfluence=function() error('component unavailable') end",
    "own_influence.CanGiveInfluence=nil",
    "own_influence.GetTokensToGive=nil",
    "own_influence.GetTokensToGive=function() error('tokens unavailable') end",
])
def test_action_missing_component_or_api_never_submits(mutation):
    vm, out = act("\n" + mutation)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


@pytest.mark.parametrize("mutation", ["considered=true", "envoy_tokens=0", "strategic_allowed=false"])
def test_action_rechecks_after_offer_goes_stale(mutation):
    vm = LuaRuntime(unpack_returned_tuples=True)
    code = ENGINE + LUA_HELPERS + SETUP + "\nlocal function query()\n"
    code += QUERIES["city_states"].body({}) + "\nend\nquery()\n"
    code += "local offered=false;for _,row in ipairs(out.items) do if row.id=='defer_envoys' then offered=true end end\nassert(offered)\n"
    code += mutation + "\nout={items={},supported=false,accepted=false}\nlocal function submit()\n"
    code += ACTIONS["city_state_defer_envoys"].body({"type": "city_state_defer_envoys"})
    code += "\nend\nsubmit()\nreturn out"
    out = vm.execute(code)
    assert out["accepted"] is False and len(vm.globals().calls) == 0


def test_successful_acknowledgment_removes_offer_without_consuming_envoys():
    vm = LuaRuntime(unpack_returned_tuples=True)
    code = ENGINE + LUA_HELPERS + SETUP + "\nlocal function submit()\n"
    code += ACTIONS["city_state_defer_envoys"].body({"type": "city_state_defer_envoys"})
    code += "\nend\nsubmit()\nassert(out.accepted)\nout={items={},supported=false,accepted=false}\nlocal function query()\n"
    code += QUERIES["city_states"].body({}) + "\nend\nquery()\nreturn out"
    out = vm.execute(code)
    assert "defer_envoys" not in records(out)
    assert records(out)["envoys"]["value"] == 2
    assert len(vm.globals().calls) == 1


def test_registry_accepts_only_the_fixed_parameterless_action():
    assert validate_action({"type": "city_state_defer_envoys"}) == {"type": "city_state_defer_envoys"}
    for extra in ({"target_player": 1}, {"considered": False}, {"operation": "GIVE_INFLUENCE_TOKEN"}):
        with pytest.raises(ValueError):
            validate_action({"type": "city_state_defer_envoys", **extra})
