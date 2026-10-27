"""Reference-inspired observations stay within normal own/player UI state."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.empire_status import QUERIES
from civ6_fair_mcp.inspection_policy import public_inspection
from test_city_status import status_engine as defense_engine
from test_extension_empire import engine as gp_engine


def gp_rows(run):
    result = run("great_people", {}, True)
    return {row["id"]: row for row in result["items"].values()}


def test_gp_own_points_and_one_decimal_rate_do_not_read_competitors(gp_engine):
    vm, run = gp_engine
    vm.execute('''
GameInfo.GreatPersonClasses=defs('GreatPersonClassType',{{GreatPersonClassType='GREAT_PERSON_CLASS_SCIENTIST',Index=4,Name='Scientist'}})
player.GetGreatPeoplePoints=function() return {GetPointsTotal=function(self,class) assert(class==4);return 32 end,
 GetPointsPerTurn=function(self,class) assert(class==4);return 3.456 end} end
Players=setmetatable({[0]=player}, {__index=forbid});PlayerConfigurations=setmetatable({}, {__index=forbid})
''')
    rows = gp_rows(run)
    assert rows["GREAT_PERSON_CLASS_SCIENTIST:points"]["value"] == 32
    assert rows["GREAT_PERSON_CLASS_SCIENTIST:points_per_turn"]["value"] == 3.5
    assert len(vm.globals().calls) == 0


@pytest.mark.parametrize("available", [False, True])
def test_gp_visible_quotes_do_not_require_affordability_but_actions_do(gp_engine, available):
    vm, run = gp_engine
    vm.execute("people.CanRecruitPerson=function() return false end;people.CanRejectPerson=function() return false end")
    vm.globals().controls.can = available
    rows = gp_rows(run)
    for currency in ("GOLD", "FAITH"):
        row = rows[f"GREAT_PERSON_INDIVIDUAL_TEST:{currency}"]
        assert row["value"] == 300
        assert (row["action"] is not None) is available


@pytest.mark.parametrize("change", [
    "people.GetPatronizeCost=function() return 1000000 end",
    "people.GetPatronizeCost=function() return -1 end", "people.GetPatronizeCost=function() return 0/0 end",
    "people.GetPatronizeCost=nil", "GameCapabilities.HasCapability=function() return false end",
    "people.CanRecruitPerson=function() return true end", "people.CanRejectPerson=function() return true end",
])
def test_gp_hidden_price_button_cannot_be_recreated_by_permissive_native_check(gp_engine, change):
    vm, run = gp_engine
    vm.execute("people.CanRecruitPerson=function() return false end;people.CanRejectPerson=function() return false end;" + change)
    rows = gp_rows(run)
    assert "GREAT_PERSON_INDIVIDUAL_TEST:GOLD" not in rows
    assert not run("great_person_patronize", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST", "yield": "GOLD"})["accepted"]
    assert len(vm.globals().calls) == 0


def test_gp_normal_pass_cost_is_only_read_when_pass_is_available(gp_engine):
    vm, run = gp_engine
    vm.execute("people.GetRejectCost=function() return 16 end")
    assert gp_rows(run)["GREAT_PERSON_INDIVIDUAL_TEST:pass_cost"]["value"] == 16
    vm.execute("people.CanRejectPerson=function() return false end;people.GetRejectCost=forbid")
    assert "GREAT_PERSON_INDIVIDUAL_TEST:pass_cost" not in gp_rows(run)


@pytest.mark.parametrize("verb,change", [
    ("recruit", "people.GetTimeline=function() return {{Individual=103}} end"),
    ("recruit", "people.GetTimeline=function() return {{Individual=103,Cost=-1}} end"),
    ("recruit", "people.GetTimeline=function() return {{Individual=103,Cost=0/0}} end"),
    ("pass", "people.GetRejectCost=nil"),
    ("pass", "people.GetRejectCost=function() return nil end"),
    ("pass", "people.GetRejectCost=function() return -1 end"),
    ("pass", "people.GetRejectCost=function() return 0/0 end"),
])
def test_gp_missing_or_invalid_stock_button_cost_hides_action_and_blocks_submission(gp_engine, verb, change):
    vm, run = gp_engine
    vm.execute(change)
    assert f"GREAT_PERSON_INDIVIDUAL_TEST:{verb}" not in gp_rows(run)
    result = run(f"great_person_{verb}", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"})
    assert not result["accepted"] and len(vm.globals().calls) == 0


@pytest.mark.parametrize("verb", ["recruit", "pass"])
def test_gp_zero_stock_button_cost_remains_valid(gp_engine, verb):
    vm, run = gp_engine
    vm.execute("people.GetTimeline=function() return {{Individual=103,Cost=0}} end;people.GetRejectCost=function() return 0 end")
    assert gp_rows(run)[f"GREAT_PERSON_INDIVIDUAL_TEST:{verb}"]["action"] is not None
    assert run(f"great_person_{verb}", {"individual": "GREAT_PERSON_INDIVIDUAL_TEST"})["accepted"]


def test_era_status_and_active_dedications_are_own_public_panel_fields(gp_engine):
    vm, run = gp_engine
    vm.execute('''
eras.GetPlayerCurrentScore=function(self,id) assert(id==0);return 45 end
eras.GetPlayerDarkAgeThreshold=function(self,id) assert(id==0);return 40 end
eras.GetPlayerGoldenAgeThreshold=function(self,id) assert(id==0);return 55 end
eras.HasHeroicGoldenAge=function(self,id) assert(id==0);return true end
eras.GetPlayerActiveCommemorations=function(self,id) assert(id==0);return {0} end
''')
    result = run("dedications", {}, True)
    rows = {row["id"]: row for row in result["items"].values()}
    assert rows["era_score"]["value"] == 45 and rows["golden_age_threshold"]["value"] == 55
    assert rows["age"]["value"] == "heroic"
    assert any(key.startswith("active:COMMEMORATION_") for key in rows)


def test_missing_era_heroic_flag_cannot_infer_normal_age(gp_engine):
    _, run = gp_engine
    rows = {row["id"]: row for row in run("dedications", {}, True)["items"].values()}
    assert "age" not in rows and "era_score" not in rows


@pytest.mark.parametrize("allowed", [True, False, None])
def test_golden_age_extra_normal_dedication_bonus_requires_own_ui_flag(gp_engine, allowed):
    vm, run = gp_engine
    vm.execute('''
eras.HasHeroicGoldenAge=function() return false end;eras.HasGoldenAge=function() return true end
eras.GetPlayerActiveCommemorations=function() return {0} end
GameInfo.CommemorationTypes[0].GoldenAgeBonusDescription='GOLDEN_EFFECT'
GameInfo.CommemorationTypes[0].NormalAgeBonusDescription='NORMAL_EFFECT'
''')
    flag = "nil" if allowed is None else str(allowed).lower()
    vm.execute("eras.IsPlayerAlwaysAllowedCommemorationQuest=function(self,id) assert(id==0);return " + flag + " end")
    rows = {row["id"]: row for row in run("dedications", {}, True)["items"].values()}
    extras = [row for key, row in rows.items() if key.endswith(":normal_age_bonus")]
    assert bool(extras) is (allowed is True)
    if allowed:
        assert extras[0]["description"] == "NORMAL_EFFECT"


def setup_defense(vm):
    vm.execute('''
DefenseTypes={DISTRICT_GARRISON=1,DISTRICT_OUTER=2}
IdentityConversionOutcome={GAINING_LOYALTY=1,LOSING_LOYALTY=2}
identity.GetConversionOutcome=function() return 2 end;identity.GetTurnsToConversion=function() return 8 end
city.GetDistrictID=function() return 99 end
center={GetOwner=function() return 0 end,GetID=function() return 99 end,GetDefenseStrength=function() return 49.6 end,
 GetMaxDamage=function(self,kind) return kind==1 and 200 or 300 end,
 GetDamage=function(self,kind) return kind==1 and 27 or 80 end}
player.GetDistricts=function() return {FindID=function(self,id) assert(id==99);return center end} end
''')


def test_own_city_defense_and_wall_hp_use_main_district_and_normal_rounding(defense_engine):
    vm, run = defense_engine
    setup_defense(vm)
    _, values = run()
    assert values["defense_strength"] == 50
    assert values["garrison_hp_maximum"] == 200 and values["garrison_hp"] == 173
    assert values["walls_hp_maximum"] == 300 and values["walls_hp"] == 220
    assert values["loyalty_direction"] == "losing" and values["loyalty_turns_to_outcome"] == 8


def test_loyalty_gaining_estimate_is_not_labeled_rebellion(defense_engine):
    vm, run = defense_engine
    setup_defense(vm)
    vm.execute("identity.GetConversionOutcome=function() return 1 end")
    _, values = run()
    assert values["loyalty_direction"] == "gaining" and values["loyalty_turns_to_outcome"] == 8


@pytest.mark.parametrize("change", [
    "center.GetOwner=function() return 2 end;center.GetID=secret;center.GetDefenseStrength=secret",
    "center.GetID=function() return 100 end;center.GetDefenseStrength=secret",
    "city.GetDistrictID=nil", "player.GetDistricts=nil",
])
def test_foreign_wrong_or_missing_main_district_cannot_supply_city_defense(defense_engine, change):
    vm, run = defense_engine
    setup_defense(vm)
    vm.execute(change)
    _, values = run()
    assert not any(key.startswith(("defense_", "walls_", "garrison_")) for key in values)
    assert values["housing"] == 4.5


def test_unknown_hp_or_loyalty_estimate_is_omitted_not_zero(defense_engine):
    vm, run = defense_engine
    setup_defense(vm)
    vm.execute("center.GetDamage=function() return -1 end;identity.GetTurnsToConversion=function() return -1 end")
    _, values = run()
    assert "walls_hp" not in values and "garrison_hp" not in values
    assert "loyalty_turns_to_outcome" not in values


@pytest.fixture
def observation_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
reads={secret=0,religion=0,city=0,plot=0}
function secret() reads.secret=reads.secret+1;error('PRIVATE') end
function members(list) local i=0;return function() i=i+1;if list[i] then return i,list[i] end end end
settings={owner=0,visible=true,revealed=true,met=true,majority=1,rule='RULESET_EXPANSION_2'}
faiths={{Religion=1,Followers=3.0},{Religion=2,Followers=1},{Religion=-1,Followers=2}}
religion={GetMajorityReligion=function() return settings.majority end,GetReligionsInCity=function() return faiths end,
 GetNextReligion=function() return 2 end,GetTurnsToNextReligion=function() return 7 end}
city={GetOwner=function() return settings.owner end,GetID=function() return 42 end,
 GetX=function() return 3 end,GetY=function() return 2 end,
 GetReligion=function() assert(settings.owner==0 or (settings.met and settings.revealed and settings.visible));reads.religion=reads.religion+1;return religion end,
 GetBuildQueue=function() return queue end}
foreign=setmetatable({GetOwner=function() return 2 end},{__index=secret})
player={GetCities=function() return {Members=function() return members({foreign,city}) end} end,
 GetDiplomacy=function() return {HasMet=function(self,id) assert(id==1);return settings.met end} end,
 GetStats=function() return stats end}
vis={IsRevealed=function() return settings.revealed end,IsVisible=function() return settings.visible end}
Map={GetGridSize=function() return 8,6 end,GetPlot=function(x,y)
 assert(settings.revealed and settings.visible);reads.plot=reads.plot+1;return setmetatable({},{__index=secret}) end}
CityManager={GetCityAt=function(x,y) assert(settings.revealed and settings.visible);reads.city=reads.city+1;return city end}
Game={GetReligion=function() return {GetName=function(self,id) return id==1 and '自定义信仰' or '佛教' end,GetReligions=secret} end,
 IsVictoryEnabled=function(kind) assert(kind=='VICTORY_TECHNOLOGY');return true end}
Players=setmetatable({}, {__index=secret});PlayerConfigurations=setmetatable({}, {__index=secret})
GameConfiguration={GetValue=function(key) assert(key=='RULESET');return settings.rule end}
GameInfo={Religions={[1]={ReligionType='RELIGION_CUSTOM',Name='Custom'},[2]={ReligionType='RELIGION_BUDDHISM',Name='Buddhism'}},Projects={}}
local names={'PROJECT_LAUNCH_EARTH_SATELLITE','PROJECT_LAUNCH_MOON_LANDING','PROJECT_LAUNCH_MARS_BASE',
 'PROJECT_LAUNCH_EXOPLANET_EXPEDITION','PROJECT_LAUNCH_MARS_REACTOR','PROJECT_LAUNCH_MARS_HABITATION','PROJECT_LAUNCH_MARS_HYDROPONICS'}
for i,id in ipairs(names) do GameInfo.Projects[id]={Index=i,Hash=100+i,Name=id} end
stats={GetNumProjectsAdvanced=function(self,index) return index==1 and 1 or 0 end,
 GetScienceVictoryPoints=function() return 15 end,GetScienceVictoryPointsTotalNeeded=function() return 50 end,
 GetScienceVictoryPointsPerTurn=function() return 2 end}
queue={GetProjectCost=function(self,index) return 100+index end,
 GetProjectProgress=function(self,index) return index==2 and 17 or 0 end,
 GetCurrentProductionTypeHash=function() return 102 end}
Locale={Lookup=function(value) return value end}
''')

    def run(category="city_religion", params=None):
        if params is None:
            params = {"city_id": 42} if category == "city_religion" else ({"x": 3, "y": 2} if category == "visible_city_religion" else {})
        result = vm.execute("local me=0;local out={items={}};\n" + LUA_HELPERS
                            + "\nlocal function collect()\n" + QUERIES[category].body(params)
                            + "\nend\ncollect()\nreturn out")
        raw = {"ok": True, "session": "reference_empire_tests", "player_id": 0, "turn": 128,
               "active_turn": True, "category": category, "supported": result["supported"],
               "items": [dict(row) for row in result["items"].values()]}
        public = public_inspection(raw, category)
        assert vm.globals().reads.secret == 0
        return public, {row["id"]: row for row in public["items"]}
    return vm, run


@pytest.mark.parametrize("category,owner", [("city_religion", 0), ("visible_city_religion", 1)])
def test_religion_follower_counts_and_forecast_match_city_lens_without_founder_identity(observation_engine, category, owner):
    vm, run = observation_engine
    vm.globals().settings.owner = owner
    result, rows = run(category)
    assert result["supported"]
    assert rows["majority_religion"]["value"] == "RELIGION_CUSTOM"
    assert rows["majority_religion"]["name"] == "自定义信仰"
    assert rows["religion:RELIGION_CUSTOM:followers"]["value"] == 3
    assert rows["religion:RELIGION_BUDDHISM:followers"]["value"] == 1
    assert rows["turns_to_next_religion"]["value"] == 7
    assert len(rows) == 5


@pytest.mark.parametrize("flag", ["visible", "revealed", "met"])
def test_foreign_city_religion_is_never_read_through_fog_or_unmet_identity(observation_engine, flag):
    vm, run = observation_engine
    vm.globals().settings.owner = 1
    vm.globals().settings[flag] = False
    result, rows = run("visible_city_religion")
    assert not result["supported"] and rows == {}
    assert vm.globals().reads.religion == 0
    if flag != "met":
        assert vm.globals().reads.city == vm.globals().reads.plot == 0


def test_own_city_religion_does_not_need_map_visibility(observation_engine):
    vm, run = observation_engine
    vm.execute("settings.visible=false;settings.revealed=false;Map.GetPlot=secret")
    result, rows = run()
    assert result["supported"] and rows
    assert vm.globals().reads.plot == vm.globals().reads.city == 0


@pytest.mark.parametrize("change", ["religion.GetReligionsInCity=nil", "faiths=false", "faiths={{Religion=1,Followers=-1}}",
                                         "faiths={{Religion=1,Followers=0/0}}", "faiths={{Religion=1,Followers=2},{Religion=1,Followers=1}}",
                                         "settings.majority='1'", "GameInfo.Religions=nil"])
def test_invalid_religion_rows_are_not_partial_success(observation_engine, change):
    vm, run = observation_engine
    vm.execute(change)
    result, rows = run()
    assert not result["supported"] and rows == {}


def test_no_religion_is_explicit_but_missing_forecast_stays_unknown(observation_engine):
    vm, run = observation_engine
    vm.execute("settings.majority=-1;faiths={};religion.GetNextReligion=nil")
    result, rows = run()
    assert result["supported"] and set(rows) == {"majority_religion"}
    assert rows["majority_religion"]["value"] == "NONE"


def test_visibility_lost_during_native_religion_read_discards_data(observation_engine):
    vm, run = observation_engine
    vm.execute("settings.owner=1;religion.GetReligionsInCity=function() settings.visible=false;return faiths end")
    result, rows = run("visible_city_religion")
    assert not result["supported"] and rows == {}


def test_native_float_geometry_is_normalized_before_visible_projection(observation_engine):
    vm, run = observation_engine
    vm.execute("settings.owner=1.0;city.GetX=function() return 3.0 end;city.GetY=function() return 2.0 end")
    result, rows = run("visible_city_religion")
    assert result["supported"] and rows["majority_religion"]["value"] == "RELIGION_CUSTOM"


def test_science_victory_own_completed_and_in_progress_are_distinct(observation_engine):
    _, run = observation_engine
    result, rows = run("own_science_victory")
    assert result["supported"]
    assert rows["PROJECT_LAUNCH_EARTH_SATELLITE:completed"]["value"] is True
    assert rows["PROJECT_LAUNCH_MOON_LANDING:completed"]["value"] is False
    assert rows["city:42:PROJECT_LAUNCH_MOON_LANDING:producing"]["value"] is True
    assert rows["city:42:PROJECT_LAUNCH_MOON_LANDING:progress"]["value"] == 17
    assert rows["light_years"]["value"] == 15 and "light_years_per_turn" not in rows
    assert not any("MARS_REACTOR" in key for key in rows)


def test_science_per_turn_is_not_read_before_expedition_completion(observation_engine):
    vm, run = observation_engine
    vm.execute("stats.GetScienceVictoryPointsPerTurn=secret")
    result, rows = run("own_science_victory")
    assert result["supported"] and "light_years_per_turn" not in rows


def test_science_per_turn_is_public_after_completed_expedition(observation_engine):
    vm, run = observation_engine
    vm.execute("stats.GetNumProjectsAdvanced=function(self,index) return (index==1 or index==4) and 1 or 0 end")
    result, rows = run("own_science_victory")
    assert result["supported"] and rows["light_years_per_turn"]["value"] == 2


@pytest.mark.parametrize("gate", ["nil", "function() return false end", "function() return 1 end"])
def test_disabled_or_unknown_science_victory_does_not_read_own_stats(observation_engine, gate):
    vm, run = observation_engine
    vm.execute("Game.IsVictoryEnabled=" + gate + ";player.GetStats=secret;player.GetCities=secret")
    result, rows = run("own_science_victory")
    assert not result["supported"] and rows == {}


@pytest.mark.parametrize("rule", ["RULESET_STANDARD", "RULESET_EXPANSION_1"])
def test_base_rf_use_original_mars_projects_without_gs_stats(observation_engine, rule):
    vm, run = observation_engine
    vm.globals().settings.rule = rule
    vm.execute("stats.GetScienceVictoryPoints=secret;stats.GetScienceVictoryPointsPerTurn=secret")
    result, rows = run("own_science_victory")
    assert result["supported"] and "PROJECT_LAUNCH_MARS_REACTOR:completed" in rows
    assert "light_years" not in rows and "PROJECT_LAUNCH_MARS_BASE:completed" not in rows


@pytest.mark.parametrize("change", ["settings.rule='MOD_UNKNOWN'", "stats.GetNumProjectsAdvanced=nil",
                                         "stats.GetNumProjectsAdvanced=function() return nil end",
                                         "GameInfo.Projects.PROJECT_LAUNCH_MOON_LANDING=nil"])
def test_unknown_science_rules_or_completion_capability_fail_closed(observation_engine, change):
    vm, run = observation_engine
    vm.execute(change)
    result, rows = run("own_science_victory")
    assert not result["supported"] and rows == {}


def test_missing_optional_science_values_are_not_invented_zeros(observation_engine):
    vm, run = observation_engine
    vm.execute("queue.GetProjectProgress=nil;queue.GetCurrentProductionTypeHash=nil;stats.GetScienceVictoryPoints=nil")
    result, rows = run("own_science_victory")
    assert result["supported"] and "PROJECT_LAUNCH_MOON_LANDING:completed" in rows
    assert "city:42:PROJECT_LAUNCH_MOON_LANDING:progress" not in rows
    assert "city:42:PROJECT_LAUNCH_MOON_LANDING:producing" not in rows and "light_years" not in rows
