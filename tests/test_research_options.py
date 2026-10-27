"""Own research/civic metadata and its independent output whitelist."""
import copy

import pytest

from civ6_fair_mcp.actions import build_options_query
from civ6_fair_mcp.policy import PolicyError, public_options
from test_actions import engine


DETAILS = r'''
local tech=Players[0]:GetTechs()
local culture=Players[0]:GetCulture()
tech.GetResearchCost=function(self,index) assert(index==4); return 45.5 end
tech.GetResearchProgress=function(self,index) assert(index==4); return 12.25 end
tech.GetTurnsToResearch=function(self,index) assert(index==4); return 3.0 end
tech.HasBoostBeenTriggered=function(self,index) assert(index==4); return false end
culture.GetCultureCost=function(self,index) assert(index==5); return 60 end
culture.GetCulturalProgress=function(self,index) assert(index==5); return 20.5 end
culture.GetTurnsToProgressCivic=function(self,index) assert(index==5); return 7.0 end
culture.HasBoostBeenTriggered=function(self,index) assert(index==5); return true end
GameInfo.Technologies.TECH_MINING.Name="LOC_MINING"
GameInfo.Technologies.TECH_MINING.Description="LOC_MINING_DESCRIPTION"
GameInfo.Civics.CIVIC_CODE_OF_LAWS.Name="LOC_LAWS"
GameInfo.Civics.CIVIC_CODE_OF_LAWS.Description="LOC_LAWS_DESCRIPTION"
GameInfo.Boosts=definitions("ID",{
    {ID=1,TechnologyType="TECH_MINING",TriggerDescription="LOC_TECH_TRIGGER"},
    {ID=2,CivicType="CIVIC_CODE_OF_LAWS",TriggerDescription="LOC_CIVIC_TRIGGER"},
})
local words={LOC_MINING="采矿业",LOC_LAWS="法典",LOC_MINING_DESCRIPTION="允许建造矿山。",
    LOC_LAWS_DESCRIPTION="市政说明。\n第二行",LOC_TECH_TRIGGER="公开科技触发条件",LOC_CIVIC_TRIGGER="公开市政触发条件"}
Locale={Lookup=function(key) return words[key] or key end}
'''


def query(run, kind="research"):
    return run(build_options_query("research_details_test", kind))


@pytest.mark.parametrize("kind,expected", [
    ("research", {"id": "TECH_MINING", "kind": "research", "name": "采矿业", "description": "允许建造矿山。",
                  "cost": 45.5, "progress": 12.25, "turns": 3, "boosted": False, "boost_description": "公开科技触发条件"}),
    ("civic", {"id": "CIVIC_CODE_OF_LAWS", "kind": "civic", "name": "法典", "description": "市政说明。\n第二行",
               "cost": 60, "progress": 20.5, "turns": 7, "boosted": True, "boost_description": "公开市政触发条件"}),
])
def test_owned_chooser_facts_round_trip_the_python_whitelist(engine, kind, expected):
    vm, run = engine
    vm.execute(DETAILS)
    raw = query(run, kind)
    assert raw["options"] == [expected]
    assert public_options(raw, kind, None)["options"] == [expected]
    assert type(raw["options"][0]["turns"]) is int
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("kind", ["research", "civic"])
def test_existing_runtime_without_optional_apis_keeps_legal_options(engine, kind):
    _, run = engine
    result = query(run, kind)
    assert len(result["options"]) == 1
    assert set(result["options"][0]) == {"id", "kind"}


@pytest.mark.parametrize("kind,current_method", [("research", "GetResearchingTech"), ("civic", "GetProgressingCivic")])
def test_current_selection_uses_stock_turns_left_override(engine, kind, current_method):
    vm, run = engine
    vm.execute(DETAILS)
    getter, index = ("GetTechs", 4) if kind == "research" else ("GetCulture", 5)
    vm.execute(f'''local p=Players[0]:{getter}()
        p.{current_method}=function() return {index} end
        p.GetTurnsLeft=function() return 0.0 end''')
    assert query(run, kind)["options"][0]["turns"] == 0


def test_failed_current_override_preserves_normal_estimate(engine):
    vm, run = engine
    vm.execute(DETAILS + '''
        local p=Players[0]:GetTechs()
        p.GetResearchingTech=function() return 4 end
        p.GetTurnsLeft=forbid
    ''')
    assert query(run)["options"][0]["turns"] == 3


@pytest.mark.parametrize("method,field", [
    ("GetResearchCost", "cost"), ("GetResearchProgress", "progress"),
    ("GetTurnsToResearch", "turns"), ("HasBoostBeenTriggered", "boosted"),
])
@pytest.mark.parametrize("failure", ["nil", "forbid"])
def test_missing_or_throwing_optional_getter_only_omits_its_own_field(engine, method, field, failure):
    vm, run = engine
    vm.execute(DETAILS)
    vm.execute(f"Players[0]:GetTechs().{method}={failure}")
    option = query(run)["options"][0]
    assert field not in option
    assert option["name"] == "采矿业" and option["boost_description"] == "公开科技触发条件"
    assert len(option) == 8


@pytest.mark.parametrize("method,value,field", [
    ("GetResearchCost", "-1", "cost"), ("GetResearchCost", "math.huge", "cost"),
    ("GetResearchProgress", "0/0", "progress"), ("GetResearchProgress", '"12"', "progress"),
    ("GetTurnsToResearch", "-1", "turns"), ("GetTurnsToResearch", "2.5", "turns"),
    ("HasBoostBeenTriggered", "1", "boosted"),
])
def test_invalid_optional_values_are_omitted_before_serialization(engine, method, value, field):
    vm, run = engine
    vm.execute(DETAILS)
    vm.execute(f"Players[0]:GetTechs().{method}=function() return {value} end")
    option = query(run)["options"][0]
    assert field not in option and option["id"] == "TECH_MINING"


@pytest.mark.parametrize("kind,control,getter,method", [
    ("research", "can_research", "GetTechs", "GetResearchCost"),
    ("civic", "can_civic", "GetCulture", "GetCultureCost"),
])
def test_unavailable_candidate_is_not_enriched(engine, kind, control, getter, method):
    vm, run = engine
    vm.execute(DETAILS)
    vm.execute(f'''controls.{control}=false
        Players[0]:{getter}().{method}=forbid
        Locale.Lookup=forbid''')
    assert query(run, kind)["options"] == []


def test_missing_description_is_not_fabricated_from_name_or_other_text(engine):
    vm, run = engine
    vm.execute(DETAILS)
    vm.execute("GameInfo.Civics.CIVIC_CODE_OF_LAWS.Description=nil")
    option = query(run, "civic")["options"][0]
    assert "description" not in option and option["name"] == "法典"
    assert option["cost"] == 60


@pytest.mark.parametrize("change", [
    "GameInfo.Boosts=nil", "GameInfo.Boosts=forbid",
    "GameInfo.Boosts=function() local i=0; return function() i=i+1; if i<=8193 then return {} end end end",
])
def test_missing_or_bounded_boost_catalog_does_not_break_options(engine, change):
    vm, run = engine
    vm.execute(DETAILS)
    vm.execute(change)
    option = query(run)["options"][0]
    assert "boost_description" not in option
    assert option["boosted"] is False and option["cost"] == 45.5


def test_localization_failure_preserves_numerical_research_state(engine):
    vm, run = engine
    vm.execute(DETAILS + "\nLocale.Lookup=forbid")
    option = query(run)["options"][0]
    assert set(option) == {"id", "kind", "cost", "progress", "turns", "boosted"}


def option_envelope(kind="research", **extra):
    return {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 31, "active_turn": True,
            "kind": kind, "options": [{"id": "TECH_MINING", "kind": kind, **extra}]}


def test_whitelist_drops_unreviewed_fields_and_nonresearch_metadata():
    raw = option_envelope(name="采矿业", enemy_progress={"1": 99}, secret_research="TECH_HIDDEN", owner_id=1)
    assert public_options(raw, "research", None)["options"] == [{"id": "TECH_MINING", "kind": "research", "name": "采矿业"}]
    raw = option_envelope("production", name="Unreviewed", description="Unreviewed", cost=99, turns=5, boosted=True)
    raw["entity_id"] = 10
    raw["options"][0].update(id="UNIT_SCOUT", kind="unit")
    assert public_options(raw, "production", 10)["options"] == [{"id": "UNIT_SCOUT", "kind": "unit"}]


@pytest.mark.parametrize("key,value", [
    ("name", "a" * 1025), ("name", "bad\nname"), ("description", "bad\x00text"),
    ("description", []), ("boost_description", "a" * 8193),
    ("cost", True), ("cost", -1), ("cost", float("inf")), ("progress", float("nan")),
    ("progress", "20"), ("turns", 2.0), ("turns", -1), ("boosted", 1),
])
def test_python_boundary_rejects_malformed_optional_facts(key, value):
    with pytest.raises(PolicyError):
        public_options(option_envelope(**{key: value}), "research", None)


def test_mutating_unexposed_extra_state_does_not_change_projected_choices():
    raw = option_envelope(name="采矿业", cost=45.5, progress=12.25, turns=3, boosted=False)
    changed = copy.deepcopy(raw)
    changed["options"][0]["internal"] = {"enemy_research": "TECH_FUTURE_TECH", "map_resources": [99]}
    assert public_options(raw, "research", None) == public_options(changed, "research", None)
