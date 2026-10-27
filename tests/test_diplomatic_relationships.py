"""Execute real emitted Lua against poisoned nonpublic diplomatic fields."""
import copy
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.diplomacy import build_diplomacy_query
from civ6_fair_mcp.diplomatic_relationships import project_relationship
from civ6_fair_mcp.policy import PolicyError, public_diplomacy
from test_diplomacy import ENGINE, civilization


RELATIONSHIPS = r'''
settings.alliance=0; settings.alliance_level=2; settings.human=false
reads.ai=0; reads.alliance_points=0; reads.zero_text=0
GameInfo.DiplomaticStates={[7]={StateType='DIPLO_STATE_FRIENDLY',Name='Friendly'}}
GameInfo.Visibilities={[0]={Name='No access'},[3]={Name='Secret'}}
GameInfo.Alliances={[0]={AllianceType='ALLIANCE_RESEARCH',Name='Research alliance'}}
GlobalParameters.ALLIANCE_POINTS_MULTIPLIER=10
local dip=self_player:GetDiplomacy()
dip.GetGrievancesAgainst=function(self,id) assert(id==1);return -12 end
dip.HasDelegationAt=function(self,id) assert(id==1);return true end
dip.HasEmbassyAt=function(self,id) assert(id==1);return false end
dip.HasDefensivePact=function(self,id) assert(id==1);return true end
dip.HasOpenBordersFrom=function(self,id) assert(id==1);return true end
dip.IsFightingAnyJointWarWith=function(self,id) assert(id==1);return false end
dip.GetResearchAgreementTech=function(self,id) assert(id==1);return 5 end
dip.GetAllianceType=function(self,id) assert(id==1);return settings.alliance end
dip.GetAllianceLevel=function(self,id) assert(id==1);return settings.alliance_level end
dip.GetAllianceTurnsUntilExpiration=function(self,id) assert(id==1);return 17 end
dip.GetAllianceTurnsThisLevel=function(self,id) reads.alliance_points=reads.alliance_points+1;return 155 end
dip.GetAllianceTurnsToNextLevel=function(self,id) reads.alliance_points=reads.alliance_points+1;return 300 end
dip.GetAlliancePointsPerTurn=function(self,id) reads.alliance_points=reads.alliance_points+1;return 20 end
known_player.GetDiplomacy=function() return {
    HasOpenBordersFrom=function(self,id) assert(id==0);return false end,
    HasDelegationAt=function() error('NOT PROVEN IN UI') end,
    HasEmbassyAt=function() error('NOT PROVEN IN UI') end,
} end
local zero=setmetatable({Score=0},{__index=function() reads.zero_text=reads.zero_text+1;error('SECRET ZERO ROW') end})
known_player.GetDiplomaticAI=function()
    reads.ai=reads.ai+1
    if settings.human then error('HIDDEN HUMAN FEELINGS') end
    return {
        GetDiplomaticStateIndex=function(self,id) assert(id==0);return 7 end,
        GetDiplomaticModifiers=function(self,id)
            assert(id==0)
            return {{Score=3.14159,Text='Public trade'},
                {Score=-2,Text='LOC_TOOLTIP_DIPLOMACY_UNKNOWN_REASON'},zero}
        end,
        GetDealValue=function() error('PRIVATE AI VALUATION') end,
    }
end
PlayerConfigurations[1].IsHuman=function() return settings.human end
'''


@pytest.fixture
def engine():
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.execute(ENGINE + RELATIONSHIPS)
    output = []
    runtime.globals().print = output.append

    def run():
        output.clear()
        runtime.execute(build_diplomacy_query("a" * 32))
        raw = json.loads(output[0].removeprefix("CIV6FAIR_JSON:"))
        assert raw.get("ok") is True
        return public_diplomacy(raw)

    return runtime, run


def test_relationship_uses_db_types_and_local_bilateral_ui(engine):
    runtime, run = engine
    value = civilization(run())["relationship"]
    assert value == {
        "state": "DIPLO_STATE_FRIENDLY", "state_name": "Friendly",
        "access_level": 0, "access_name": "No access", "grievances": -12,
        "delegation_sent": True, "embassy_sent": False, "defensive_pact": True,
        "open_borders_received": True, "open_borders_given": False,
        "research_agreement": True, "joint_war": False, "allied": True,
        "alliance": "ALLIANCE_RESEARCH", "alliance_name": "Research alliance",
        "alliance_level": 2, "alliance_turns_remaining": 17,
        "alliance_points": 15.5, "alliance_points_required": 30,
        "alliance_points_per_turn": 2,
        "modifiers": [{"score": 3.14, "text": "Public trade"},
                      {"score": -2, "text": "LOC_TOOLTIP_DIPLOMACY_UNKNOWN_REASON"}],
    }
    assert runtime.globals().reads.zero_text == 0
    assert runtime.globals().reads.unknown == 0
    assert runtime.globals().reads.locations == 0
    assert runtime.globals().reads.dead == 0


def test_unmet_and_self_and_dead_never_get_relationship(engine):
    runtime, run = engine
    value = run()
    assert "relationship" not in civilization(value, 0)
    assert "relationship" not in civilization(value, 3)
    runtime.execute("settings.all_unmet=true")
    assert [row["id"] for row in run()["civilizations"]] == [0]
    assert runtime.globals().reads.ai == 1


def test_human_feelings_are_not_read(engine):
    runtime, run = engine
    runtime.execute("settings.human=true")
    value = civilization(run())["relationship"]
    assert "state" not in value and "modifiers" not in value
    assert value["alliance"] == "ALLIANCE_RESEARCH"
    assert runtime.globals().reads.ai == 0


@pytest.mark.parametrize("alliance,level", [(-1, 2), (0, 3), (0, 4), (0, 0)])
def test_hidden_alliance_point_fields_are_not_read(engine, alliance, level):
    runtime, run = engine
    runtime.globals().settings.alliance = alliance
    runtime.globals().settings.alliance_level = level
    value = civilization(run())["relationship"]
    assert "alliance_points" not in value
    assert runtime.globals().reads.alliance_points == 0
    if alliance == -1:
        assert value["allied"] is False and "alliance" not in value


@pytest.mark.parametrize("value", ["nil", "0", "-1", "0/0"])
def test_unknown_alliance_multiplier_does_not_invent_points(engine, value):
    runtime, run = engine
    runtime.execute("GlobalParameters.ALLIANCE_POINTS_MULTIPLIER=" + value)
    assert "alliance_points" not in civilization(run())["relationship"]
    assert runtime.globals().reads.alliance_points == 0


def test_missing_optional_apis_do_not_invent_false_or_zero(engine):
    runtime, run = engine
    runtime.execute("""
        local d=self_player:GetDiplomacy()
        d.GetGrievancesAgainst=nil; d.HasEmbassyAt=nil;d.GetAllianceType=nil
        d.HasDelegationAt=function() error('PRIVATE ENGINE MESSAGE') end
        known_player.GetDiplomaticAI=nil
    """)
    value = civilization(run())["relationship"]
    for key in ("grievances", "embassy_sent", "allied", "alliance", "delegation_sent", "state", "modifiers"):
        assert key not in value
    assert "PRIVATE" not in json.dumps(value)


def proof(**values):
    return {"observer_id": 0, "target_id": 1, "public_ui": True, **values}


@pytest.mark.parametrize("changed", [
    {"observer_id": True}, {"observer_id": 1}, {"target_id": True},
    {"target_id": 2}, {"public_ui": 1}, {"public_ui": False},
])
def test_projection_drops_invalid_proof_before_secret_validation(changed):
    assert project_relationship(proof(state=object(), **changed), 0, 1) is None


def test_projection_drops_unauthorized_ai_and_alliance_fields_before_validation():
    value = project_relationship(proof(state=object(), modifiers=object(),
        alliance=object(), alliance_points=object(), allied=False), 0, 1)
    assert value == {"allied": False}


def test_projection_drops_max_level_points_and_extra_private_fields():
    value = project_relationship(proof(allied=True, alliance_level=3,
        alliance_points=object(), ai_private_score=object()), 0, 1)
    assert value == {"allied": True, "alliance_level": 3}


@pytest.mark.parametrize("changes", [
    {"state": "TECH_SECRET", "ai_panel": True},
    {"allied": True, "alliance": "TECH_SECRET"},
    {"access_level": True}, {"grievances": float("nan")},
    {"ai_panel": True, "modifiers": [{"score": 1}]},
    {"ai_panel": True, "modifiers": [{"score": True, "text": "invalid"}]},
    {"ai_panel": True, "modifiers": [{"score": 1, "text": "x"}] * 129},
    {"ai_panel": True, "modifiers": [{"score": 1, "text": "x" * 1025}]},
])
def test_invalid_authorized_data_fails_closed(changes):
    with pytest.raises(PolicyError):
        project_relationship(proof(**changes), 0, 1)


def test_long_localized_public_modifier_text_is_preserved():
    text = "公开的外交关系原因" * 35
    assert project_relationship(proof(ai_panel=True, modifiers=[{"score": 2, "text": text}]), 0, 1)["modifiers"][0]["text"] == text


def test_zero_score_text_is_never_validated_or_copied():
    assert project_relationship(proof(ai_panel=True, modifiers=[{"score": 0, "text": object()}]), 0, 1) == {"modifiers": []}


def test_forged_relationship_for_dead_unmet_or_self_is_discarded(engine):
    _, run = engine
    public = run()
    raw = {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 12,
           "active_turn": True, "civilization_count": 4, "civilizations": []}
    # Use the real wrapper's required metadata shape instead of trusting the
    # serializer: each parent gate should suppress malformed nested fields.
    for row in public["civilizations"]:
        if row["id"] == 1:
            continue
        row = copy.deepcopy(row)
        row["relationship"] = object()
        raw["civilizations"].append(row)
    raw["civilizations"].append({"met": False, "relationship": object()})
    result = public_diplomacy(raw)
    assert all("relationship" not in row for row in result["civilizations"])
