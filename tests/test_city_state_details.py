"""Execute city-state query Lua against stock UI signatures and privacy traps.

Fixtures follow CityStates.lua's GetData/GetQuests/GetBonusText, including
LevyMilitaryTurnLimit on the *target* influence object and anonymous rivals.
"""
import json

import pytest

from civ6_fair_mcp.inspection_policy import public_inspection
from test_extension_diplomacy_actions import CITY_STATE_SETUP, city_state_actions, execute


DETAILS_SETUP = CITY_STATE_SETUP + r'''
detail_reads={tokens={},quest_gates={},quest_contents={},resources=0,other_traits=0}
detail_values={tokens={[0]=3,[2]=4,[9]=6,[11]=2,[15]=0},most=6,suzerain=9,levy_counter=-1}
local city_influence={
    CanReceiveInfluence=function() return citystate_flags.receives end,
    GetTokensReceived=function(_,who)
        detail_reads.tokens[#detail_reads.tokens+1]=who
        return detail_values.tokens[who]
    end,
    GetMostTokensReceived=function() return detail_values.most end,
    GetSuzerain=function() return detail_values.suzerain end,
    GetLevyTurnLimit=function() return 30 end,
    GetLevyTurnCounter=function() return detail_values.levy_counter end,
    IsSuzerainUniqueBonusDisabled=function() return false end,
}
Players[1].GetInfluence=function() return city_influence end
Players[1].GetResources=function() detail_reads.resources=detail_reads.resources+1;error('FOREIGN RESOURCES') end
Players[1].GetCities=function() error('FOREIGN CITIES') end
Players[1].GetUnits=function() error('FOREIGN UNITS') end
Players[1].GetDiplomaticAI=function() error('INTERNAL DIPLOMATIC AI') end
Map={GetPlot=function() error('HIDDEN MAP') end}
local own_influence=player:GetInfluence()
own_influence.GetLevyTurnLimit=function() error('Wrong owner for stock LevyMilitaryTurnLimit') end
known[2]=true
PlayerConfigurations[2]={GetPlayerName=function() return 'Known rival' end}
PlayerConfigurations[1].GetLeaderTypeName=function() return 'LEADER_CITY_TEST' end
PlayerManager.GetAliveMajorIDs=function() return {0,2,9,11,15} end
GameInfo.Leaders={LEADER_CITY_TEST={InheritFrom='LEADER_MINOR_CIV_SCIENTIFIC'}}
local function rows(items)
    return setmetatable(items,{__call=function()
        local index=0
        return function() index=index+1;return items[index] end
    end})
end
GameInfo.LeaderTraits=rows({
    {LeaderType='LEADER_CITY_TEST',TraitType='TRAIT_CITY_TEST'},
    {LeaderType='LEADER_SECRET',TraitType='TRAIT_SECRET'},
})
GameInfo.Traits=setmetatable({TRAIT_CITY_TEST={Description='LOC_CITY_UNIQUE'}},{__index=function()
    detail_reads.other_traits=detail_reads.other_traits+1;error('UNRELATED TRAIT DESCRIPTION')
end})
quest_types={'QUEST_CONVERT_CAPITAL_TO_RELIGION','QUEST_SEND_TRADE_ROUTE','QUEST_CLEAR_BARBARIAN_CAMP',
    'QUEST_TRAIN_UNIT_TYPE','QUEST_ZONE_DISTRICT_TYPE','QUEST_TRIGGER_TECH_BOOST',
    'QUEST_TRIGGER_CIVIC_BOOST','QUEST_RECRUIT_GREAT_PERSON_CLASS'}
local quest_rows={}
for index,name in ipairs(quest_types) do quest_rows[index]={Index=index-1,QuestType=name} end
GameInfo.Quests=rows(quest_rows)
active_quests={[1]=true}
local function quest_content(kind,local_id,city_id,index)
    assert(local_id==0 and city_id==1, 'Wrong quest viewer or city-state')
    assert(active_quests[index]==true, 'Inactive quest content read')
    assert(detail_reads.quest_gates[index]==true, 'Content before active gate')
    detail_reads.quest_contents[#detail_reads.quest_contents+1]=kind..':'..index
    return kind..' '..index
end
quest_manager={
    HasActiveQuestFromPlayer=function(_,local_id,city_id,index)
        assert(local_id==0 and city_id==1, 'Wrong quest viewer or city-state')
        detail_reads.quest_gates[index]=true
        return active_quests[index]==true
    end,
    GetActiveQuestName=function(_,...) return quest_content('Objective',...) end,
    GetActiveQuestDescription=function(_,...) return quest_content('Description',...) end,
    GetActiveQuestReward=function(_,...) return quest_content('Reward',...) end,
}
Game.GetQuestsManager=function() return quest_manager end
Locale.Lookup=function(text)
    if text=='LOCAL_CITY_STATES_UNKNOWN' then return 'Unknown civilization' end
    if text=='LOC_CITY_UNIQUE' then return 'The current ruleset unique benefit' end
    return 'localized:'..text
end
'''


def run_details(mutation=""):
    return execute("city_states", query=True, setup=DETAILS_SETUP + mutation)


def records(out):
    return {row["id"]: row for row in out["items"].values()}


def values(out):
    return {key: row["value"] for key, row in records(out).items()}


def native(value):
    if hasattr(value, "items"):
        return {key: native(item) for key, item in value.items()}
    return value


def public_result(out):
    raw = {
        "session": "city_state_test_session", "player_id": 0, "turn": 20,
        "active_turn": True, "category": "city_states", "supported": out["supported"],
        "items": [native(row) for row in out["items"].values()],
    }
    return public_inspection(raw, "city_states")


def test_full_public_menu_fields_have_stock_owner_signatures_and_no_private_scans():
    vm, out = run_details()
    result = values(out)
    assert out["supported"] is True
    assert result["city_state_1"] == 1
    assert result["city_state_1:envoys"] == 3
    assert result["city_state_1:most_envoys"] == 6
    assert result["city_state_1:suzerain_target_envoys"] == 7
    assert result["city_state_1:is_suzerain"] is False
    assert result["city_state_1:at_war"] is False
    assert result["city_state_1:military_available"] is True
    assert result["city_state_1:levy_duration"] == 30
    assert result["city_state_1:levy_active"] is False
    assert result["levy_cost_1"] == 40
    assert result["city_state_1:details_status"] == "complete"
    assert vm.globals().reads == 0
    assert vm.globals().detail_reads.resources == 0
    assert vm.globals().detail_reads.other_traits == 0
    assert len(vm.globals().calls) == 0
    assert {row["scope"] for row in out["items"].values() if row["id"].startswith("city_state_1:")} == {"met"}


def test_encountered_city_state_stays_visible_with_no_available_action():
    _, out = run_details('''
local own=player:GetInfluence()
own.CanGiveInfluence=function() return false end
own.CanLevyMilitary=function() return false end
citystate_flags.can_war=false
''')
    assert city_state_actions(out) == set()
    result = values(out)
    assert result["city_state_1"] == 1
    assert result["city_state_1:can_send_envoy"] is False
    assert result["city_state_1:can_levy"] is False
    assert result["city_state_1:can_declare_war"] is False
    assert result["city_state_1:can_make_peace"] is False
    assert result["levy_cost_1"] == 40  # The normal disabled-button tooltip includes it.
    assert result["city_state_1:envoys"] == 3


def test_unknown_suzerain_and_contributors_are_anonymous_without_id_or_identity_reads():
    vm, out = run_details()
    result = records(out)
    assert result["city_state_1:suzerain"]["value"] == "unknown"
    assert result["city_state_1:suzerain"]["description"] == "Unknown civilization"
    assert "city_state_1:suzerain_player" not in result
    assert result["city_state_1:influence_unknown:1"]["value"] == 6
    assert result["city_state_1:influence_unknown:2"]["value"] == 2
    assert "city_state_1:influence_unknown:3" not in result
    assert result["city_state_1:influence:self"]["value"] == 3
    assert result["city_state_1:influence:2"]["value"] == 4
    assert "Known rival" in result["city_state_1:influence:2"]["name"]
    public = public_result(out)
    encoded = json.dumps(public)
    for key in ("influence:9", "influence:11", "influence:15", "SECRET", "owner_id", "met"):
        assert key not in encoded
    for row in public["items"]:
        assert set(row) <= {"id", "name", "value", "description", "action"}
    assert vm.globals().reads == 0


def test_anonymous_contributor_order_does_not_expose_original_major_id_order():
    _, first = run_details()
    _, second = run_details("PlayerManager.GetAliveMajorIDs=function() return {15,11,2,9,0} end")
    def unknowns(out):
        return {key: native(row) for key, row in records(out).items() if ":influence_unknown:" in key}
    assert unknowns(first) == unknowns(second)


@pytest.mark.parametrize("suzerain,most,status,target,known_id", [
    (-1, 0, "none", 3, None), (-1, 3, "none", 4, None),
    (0, 8, "self", 8, None), (2, 8, "known", 9, 2), (9, 8, "unknown", 9, None),
])
def test_suzerain_status_and_stock_menu_target(suzerain, most, status, target, known_id):
    vm, out = run_details(f"detail_values.suzerain={suzerain};detail_values.most={most}")
    result = values(out)
    assert result["city_state_1:suzerain"] == status
    assert result["city_state_1:is_suzerain"] is (suzerain == 0)
    assert result["city_state_1:suzerain_target_envoys"] == target
    assert result.get("city_state_1:suzerain_player") == known_id
    if status == "known":
        assert "Known rival" in records(out)["city_state_1:suzerain"]["description"]
    assert vm.globals().reads == 0


def test_unmet_city_state_is_gated_before_every_detail_and_identity_getter():
    vm, out = run_details('''
known[1]=false
Players[1].GetInfluence=function() error('UNMET DETAILS') end
PlayerConfigurations[1].GetCivilizationShortDescription=function() error('UNMET IDENTITY') end
PlayerManager.GetAliveMajorIDs=function() error('UNMET COMPETITION') end
Game.GetQuestsManager=function() error('UNMET QUEST') end
''')
    assert set(records(out)) == {"envoys"}
    assert vm.globals().reads == 0


@pytest.mark.parametrize("flag", ["free", "major", "barbarian"])
def test_non_city_state_details_are_not_read(flag):
    _, out = run_details(f'''
citystate_flags.{flag}=true
Players[1].GetInfluence=function() error('NON CITY STATE DETAILS') end
PlayerConfigurations[1].GetLeaderTypeName=function() error('NON CITY STATE LEADER') end
''')
    assert set(records(out)) == {"envoys"}


@pytest.mark.parametrize("category,output_type", [
    ("SCIENTIFIC", "SCIENTIFIC"), ("RELIGIOUS", "RELIGIOUS"), ("TRADE", "TRADE"),
    ("CULTURAL", "CULTURE"), ("MILITARISTIC", "MILITARISTIC"), ("INDUSTRIAL", "INDUSTRIAL"),
])
def test_type_and_each_envoy_tier_use_the_current_localized_stock_rules(category, output_type):
    _, out = run_details(f"GameInfo.Leaders.LEADER_CITY_TEST.InheritFrom='LEADER_MINOR_CIV_{category}'")
    result = records(out)
    assert result["city_state_1:type"]["value"] == output_type
    assert result["city_state_1:type"]["name"].endswith("localized:LOC_CITY_STATES_TYPE_" + category)
    for threshold, tier in ((1, "SMALL"), (3, "MEDIUM"), (6, "LARGE")):
        row = result[f"city_state_1:bonus:{threshold}"]
        assert row["value"] == threshold
        assert row["name"].endswith(f"localized:LOC_MINOR_CIV_{tier}_INFLUENCE_ENVOYS")
        assert row["description"] == f"localized:LOC_MINOR_CIV_{category}_TRAIT_{tier}_INFLUENCE_BONUS"
    assert result["city_state_1:unique_bonus:TRAIT_CITY_TEST"]["description"] == "The current ruleset unique benefit"
    assert result["city_state_1:unique_bonus_disabled"]["value"] is False


def test_quests_use_local_viewer_target_and_active_gate_before_text():
    vm, out = run_details()
    result = records(out)
    assert result["city_state_1:quest_count"]["value"] == 1
    row = result["city_state_1:quest:QUEST_SEND_TRADE_ROUTE"]
    assert row["name"].endswith("Objective 1")
    assert row["description"] == "Description 1\nReward 1"
    assert len(vm.globals().detail_reads.quest_contents) == 3
    assert len([key for key in result if ":quest:" in key]) == 1


@pytest.mark.parametrize("index", range(8))
def test_each_stock_quest_kind_is_supported_without_map_lookup(index):
    vm, out = run_details(f"active_quests={{[{index}]=true}}")
    quest_type = vm.globals().quest_types[index + 1]
    assert f"city_state_1:quest:{quest_type}" in records(out)
    assert values(out)["city_state_1:quest_count"] == 1
    assert len(vm.globals().detail_reads.quest_contents) == 3


def test_no_active_quests_reports_zero_without_reading_objectives():
    vm, out = run_details("active_quests={}")
    assert values(out)["city_state_1:quest_count"] == 0
    assert len(vm.globals().detail_reads.quest_contents) == 0


def test_unknown_quest_type_is_not_read_or_claimed_as_zero():
    vm, out = run_details('''
GameInfo.Quests[9]={Index=99,QuestType='QUEST_MODDED_HIDDEN_TARGET'}
local original=quest_manager.HasActiveQuestFromPlayer
quest_manager.HasActiveQuestFromPlayer=function(self,viewer,target,index)
    assert(index~=99,'Non-stock quest queried');return original(self,viewer,target,index)
end
''')
    assert values(out)["city_state_1:details_status"] == "partial"
    assert "city_state_1:quest_count" not in records(out)
    assert len(vm.globals().detail_reads.quest_contents) == 3


@pytest.mark.parametrize("mutation,missing", [
    ("Game.GetQuestsManager=nil", "quest_count"),
    ("quest_manager.HasActiveQuestFromPlayer=function() return nil end", "quest_count"),
    ("Players[1]:GetInfluence().GetTokensReceived=nil", "envoys"),
    ("Players[1]:GetInfluence().GetSuzerain=nil", "suzerain"),
    ("PlayerConfigurations[1].GetLeaderTypeName=nil", "type"),
    ("GameInfo.LeaderTraits=nil", "unique_bonus:TRAIT_CITY_TEST"),
    ("PlayerManager.GetAliveMajorIDs=nil", "influence:self"),
])
def test_missing_detail_apis_preserve_stable_entry_actions_and_explicit_partial(mutation, missing):
    _, out = run_details(mutation)
    result = values(out)
    assert result["city_state_1"] == 1
    assert result["city_state_1:details_status"] == "partial"
    assert f"city_state_1:{missing}" not in result
    assert city_state_actions(out) == {"city_state_envoy", "city_state_levy", "city_state_war"}


def test_military_disabled_does_not_read_disabled_military_tooltip_and_does_not_block_envoys():
    _, out = run_details('''
citystate_flags.military=false
player:GetInfluence().GetLevyMilitaryCost=function() error('Hidden military tooltip') end
Players[1]:GetInfluence().GetLevyTurnLimit=function() error('Hidden military duration') end
Players[1]:GetInfluence().GetLevyTurnCounter=function() error('Hidden military status') end
''')
    result = values(out)
    assert result["city_state_1:military_available"] is False
    assert "levy_cost_1" not in result
    assert "city_state_1:levy_duration" not in result
    assert city_state_actions(out) == {"city_state_envoy"}
    assert result["city_state_1:details_status"] == "complete"


@pytest.mark.parametrize("at_war", [False, True])
def test_eligibility_fields_agree_with_offered_actions_and_war_state(at_war):
    _, out = run_details(f"citystate_flags.at_war={'true' if at_war else 'false'}")
    result = values(out)
    actions = city_state_actions(out)
    assert result["city_state_1:at_war"] is at_war
    for key, action in (("can_send_envoy", "city_state_envoy"), ("can_levy", "city_state_levy"),
                        ("can_declare_war", "city_state_war"), ("can_make_peace", "city_state_peace")):
        assert result["city_state_1:" + key] is (action in actions)
    assert result["city_state_1:can_declare_war"] is (not at_war)
    assert result["city_state_1:can_make_peace"] is at_war


def test_unknown_war_status_is_not_claimed_as_peace():
    _, out = run_details("citystate_flags.at_war=nil")
    result = values(out)
    assert "city_state_1:at_war" not in result
    assert result["city_state_1:can_declare_war"] is False
    assert result["city_state_1:can_make_peace"] is False
    assert result["city_state_1:details_status"] == "partial"
