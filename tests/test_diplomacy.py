"""Run the actual Lua query with poisoned unknown identities and hidden agendas."""

import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.diplomacy import build_diplomacy_query
from civ6_fair_mcp.policy import parse_response, public_diplomacy


ENGINE = r'''
settings = {access=0, launched=false, all_unmet=false, hidden_agenda='AGENDA_SECRET', faith_yield=6.5,
    science_error=false, missing_agendas=false, disabled_caps={}, disabled_victories={}}
reads = {unknown=0, unknown_config=0, hidden_agenda=0, hidden_definition=0,
    locations=0, dead=0, foreign_gpt=0, prelaunch_travel=0, travel=0}
function forbidden_location()
    reads.locations=reads.locations+1
    error('SECRET CITY COORDINATES')
end
GameConfiguration = {IsAnyMultiplayer=function() return false end,
    IsHotseat=function() return false end, IsWorldBuilderEditor=function() return false end}
Game = {GetLocalPlayer=function() return 0 end, GetLocalObserver=function() return 0 end,
    GetCurrentGameTurn=function() return 12 end,
    IsVictoryEnabled=function(name) return not settings.disabled_victories[name] end}
GameCapabilities = {HasCapability=function(name) return not settings.disabled_caps[name] end}
Automation = {IsActive=function() return false end}
UI = {IsProcessingMessages=function() return false end}
Events = {LoadGameViewStateDone={Add=function(fn) end}, LocalPlayerChanged={Add=function(fn) end}}
PlayersVisibility = {[0]={IsVisible=function() return true end, IsRevealed=function() return true end}}
Locale = {Lookup=function(text) return text end}
GlobalParameters = {DIPLOMATIC_VICTORY_POINTS_REQUIRED=20.0}
GameInfo = {
    Projects={
        PROJECT_LAUNCH_EARTH_SATELLITE={Index=0}, PROJECT_LAUNCH_MOON_LANDING={Index=1},
        PROJECT_LAUNCH_MARS_BASE={Index=2}, PROJECT_LAUNCH_EXOPLANET_EXPEDITION={Index=3}
    },
    Agendas=setmetatable({AGENDA_PUBLIC={AgendaType='AGENDA_PUBLIC'}}, {__index=function(self,key)
        if settings.access < 3 then
            reads.hidden_definition=reads.hidden_definition+1
            error('SECRET AGENDA DEFINITION')
        end
        return {AgendaType=key}
    end})
}
local diplomacy = {
    HasMet=function(self,id) return not settings.all_unmet and (id==1 or id==3) end,
    IsAtWarWith=function(self,id) return id==1 end,
    GetVisibilityOn=function(self,id) return settings.access end
}
local function stats(id)
    return {
        GetMilitaryStrengthWithoutTreasury=function() return 23.7 end,
        GetNumTechsResearched=function() return 8.0 end,
        GetNumProjectsAdvanced=function(self,index)
            if id==0 then return 0 end
            if index==3 then return settings.launched and 1 or 0 end
            return index<=1 and 1 or 0
        end,
        GetScienceVictoryPointsTotalNeeded=function() return 50 end,
        GetScienceVictoryPoints=function()
            if not settings.launched then reads.prelaunch_travel=reads.prelaunch_travel+1; error('SECRET TRAVEL') end
            reads.travel=reads.travel+1
            return 80
        end,
        GetScienceVictoryPointsPerTurn=function()
            if not settings.launched then reads.prelaunch_travel=reads.prelaunch_travel+1; error('SECRET SPEED') end
            reads.travel=reads.travel+1
            return 6
        end,
        GetDiplomaticVictoryPoints=function() return 11.0 end,
        GetNumCitiesFollowingReligion=function() return 9.0 end
    }
end
local function make_player(id)
    local value = {
        GetID=function() return id end,
        IsAlive=function() return true end,
        IsHuman=function() return id==0 end,
        IsTurnActive=function() return true end,
        IsTurnActiveComplete=function() return true end,
        GetDiplomacy=function() return diplomacy end,
        GetTreasury=function() return {
            GetGoldBalance=function() return 53.9 end,
            GetGoldYield=function()
                if id~=0 then reads.foreign_gpt=reads.foreign_gpt+1; error('SECRET NET INCOME') end
                return 9.2
            end,
            GetTotalMaintenance=function()
                if id~=0 then reads.foreign_gpt=reads.foreign_gpt+1; error('SECRET MAINTENANCE') end
                return 2
            end
        } end,
        GetTechs=function() return {GetScienceYield=function()
            if settings.science_error then error('SECRET ENGINE TRACE') end
            return 10.7
        end} end,
        GetCulture=function() return {
            GetCultureYield=function() return 7.2 end,
            GetStaycationers=function() return 21.0 end,
            GetTouristsTo=function() return 13.0 end
        } end,
        GetStats=function() return stats(id) end,
        GetScore=function() return 56.7 end,
        GetReligion=function() return {GetFaithYield=function() return settings.faith_yield end} end,
        GetCities=forbidden_location, GetDistricts=forbidden_location, GetUnits=forbidden_location,
        GetAgendaTypes=function() error('UNFILTERED ALL AGENDAS') end,
        GetAgendasAndVisibilities=function()
            if settings.missing_agendas then error('SECRET ENGINE AGENDA ERROR') end
            local hidden = setmetatable({Visibility=3}, {__index=function(self,key)
                if key=='Agenda' then
                    if settings.access<3 then
                        reads.hidden_agenda=reads.hidden_agenda+1
                        error('SECRET AGENDA ID')
                    end
                    return settings.hidden_agenda
                end
            end})
            return {{Visibility=0, Agenda='AGENDA_PUBLIC'}, hidden}
        end
    }
    return value
end
self_player = make_player(0)
known_player = make_player(1)
unknown_player = setmetatable({GetID=function() return 2 end}, {__index=function()
    reads.unknown=reads.unknown+1
    error('SECRET UNMET CIVILIZATION')
end})
dead_player = setmetatable({GetID=function() return 3 end, IsAlive=function() return false end}, {
    __index=function() reads.dead=reads.dead+1; error('SECRET POSTMORTEM STATE') end})
Players = setmetatable({[0]=self_player}, {__index=function()
    reads.unknown=reads.unknown+1
    error('BROAD PLAYER LOOKUP')
end})
participants = {self_player, known_player, unknown_player, dead_player}
PlayerManager = {GetWasEverAliveMajors=function() return participants end}
local function config(id)
    return {
        GetCivilizationTypeName=function() return 'CIVILIZATION_'..id end,
        GetLeaderTypeName=function() return 'LEADER_'..id end,
        GetPlayerName=function() return 'Name '..id end,
        IsHuman=function() return id==0 end
    }
end
PlayerConfigurations = setmetatable({[0]=config(0), [1]=config(1), [3]=config(3)}, {
    __index=function() reads.unknown_config=reads.unknown_config+1; error('SECRET IDENTITY') end})
Map = {GetPlot=forbidden_location}
GameEffects = {GetRequirementSetInnerRequirements=forbidden_location}
'''


@pytest.fixture
def engine():
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(ENGINE)
    output = []
    lua.globals().print = output.append

    def run():
        output.clear()
        lua.execute(build_diplomacy_query("a" * 32))
        assert len(output) == 2 and output[1] == "---END---"
        assert output[0].startswith("CIV6FAIR_JSON:")
        return json.loads(output[0][len("CIV6FAIR_JSON:") :])

    return lua, run


def civilization(result, player_id=1):
    return next(row for row in result["civilizations"] if row["id"] == player_id)


def test_total_includes_unknown_and_dead_but_identity_gate_precedes_all_details(engine):
    lua, run = engine
    result = run()
    assert result["ok"] is True
    assert result["civilization_count"] == 4
    assert [row["id"] for row in result["civilizations"]] == [0, 1, 3]
    assert all(row["met"] is True for row in result["civilizations"])
    assert lua.globals().reads.unknown == 0
    assert lua.globals().reads.unknown_config == 0
    assert "CIVILIZATION_2" not in json.dumps(result)
    assert civilization(result, 3)["alive"] is False
    assert "gold" not in civilization(result, 3)
    assert "victory" not in civilization(result, 3)
    assert lua.globals().reads.dead == 0


def test_changing_unmet_data_never_changes_result(engine):
    lua, run = engine
    before = run()
    lua.execute("""
        unknown_player = setmetatable({GetID=function() return 7 end}, {
            __index=function() reads.unknown=reads.unknown+1; error('DIFFERENT SECRET') end})
        participants[3] = unknown_player
    """)
    assert run() == before
    assert lua.globals().reads.unknown == 0
    assert lua.globals().reads.unknown_config == 0


def test_all_unmet_means_no_foreign_config_access(engine):
    lua, run = engine
    lua.execute("settings.all_unmet=true; PlayerConfigurations[1]=nil; PlayerConfigurations[3]=nil")
    result = run()
    assert result["ok"] is True
    assert [row["id"] for row in result["civilizations"]] == [0]
    assert result["civilization_count"] == 4
    assert lua.globals().reads.unknown_config == 0


def test_hidden_agenda_is_not_accessed_or_counted(engine):
    lua, run = engine
    before = run()
    assert civilization(before)["agendas"] == [{"id": "AGENDA_PUBLIC", "visible": True}]
    assert civilization(before, 0)["agendas"] == []
    lua.execute("settings.hidden_agenda='AGENDA_DIFFERENT_SECRET'")
    assert run() == before
    assert lua.globals().reads.hidden_agenda == 0
    assert lua.globals().reads.hidden_definition == 0


def test_gs_per_agenda_visibility_reveals_only_authorized_ids(engine):
    lua, run = engine
    lua.execute("settings.access=3")
    assert civilization(run())["agendas"] == [
        {"id": "AGENDA_PUBLIC", "visible": True}, {"id": "AGENDA_SECRET", "visible": True},
    ]
    assert lua.globals().reads.hidden_agenda == 0


def test_ribbon_precision_and_foreign_net_income_is_not_queried(engine):
    lua, run = engine
    result = run()
    known = civilization(result)
    assert known["gold"] == 53
    assert known["science_per_turn"] == 11
    assert known["culture_per_turn"] == 7
    assert known["military_strength"] == 24
    assert known["score"] == 57
    assert "gold_per_turn" not in known
    assert civilization(result, 0)["gold_per_turn"] == pytest.approx(7.2)
    assert lua.globals().reads.foreign_gpt == 0


def test_aggregate_victory_data_has_no_foreign_location_access(engine):
    lua, run = engine
    victory = civilization(run())["victory"]
    assert victory == {
        "science_techs_researched": 8,
        "science_satellite_completed": True, "science_moon_completed": True,
        "science_mars_completed": False, "science_exoplanet_completed": False,
        "culture_domestic_tourists": 21, "culture_visiting_tourists": 13,
        "religion_cities_following": 9, "religion_faith_per_turn": 6.5,
        "diplomatic_points": 11, "diplomatic_points_required": 20,
    }
    assert lua.globals().reads.locations == 0
    assert lua.globals().reads.prelaunch_travel == 0
    assert lua.globals().reads.travel == 0


def test_expedition_travel_requires_launch_and_caps_to_ui_target(engine):
    lua, run = engine
    lua.execute("settings.launched=true")
    victory = civilization(run())["victory"]
    assert victory["science_exoplanet_completed"] is True
    assert victory["science_light_years"] == 50
    assert victory["science_light_years_per_turn"] == 6
    assert lua.globals().reads.travel == 2
    assert lua.globals().reads.locations == 0


@pytest.mark.parametrize("faith,expected", [(6.54, 6.5), (6.55, 6.6), (123.456, 123.5)])
def test_religion_faith_matches_world_rankings_one_decimal_precision(engine, faith, expected):
    lua, run = engine
    lua.globals().settings.faith_yield = faith
    assert civilization(run())["victory"]["religion_faith_per_turn"] == expected


def test_actual_generated_lua_envelope_passes_python_disclosure_policy(engine):
    lua, run = engine
    lua.execute("settings.launched=true; settings.faith_yield=6.54321")
    raw = run()
    wire = "CIV6FAIR_JSON:" + json.dumps(raw) + "\n---END---"
    public = public_diplomacy(parse_response(wire))
    known = civilization(public)
    assert known["agendas"] == ["AGENDA_PUBLIC"]
    assert known["victory"]["religion_faith_per_turn"] == 6.5
    for field in ("science_techs_researched", "culture_domestic_tourists", "culture_visiting_tourists",
                  "religion_cities_following", "diplomatic_points", "diplomatic_points_required"):
        assert type(known["victory"][field]) is int
    assert "gold_per_turn" not in known
    assert [row["id"] for row in public["civilizations"]] == [0, 1, 3]
    assert "victory" not in civilization(public, 3)


def test_optional_method_errors_omit_fields_without_engine_error_text(engine):
    lua, run = engine
    lua.execute("settings.science_error=true; settings.missing_agendas=true")
    result = run()
    assert result["ok"] is True
    known = civilization(result)
    assert "science_per_turn" not in known and "agendas" not in known
    assert known["gold"] == 53 and known["victory"]["science_techs_researched"] == 8
    assert "SECRET" not in json.dumps(result)


def test_capability_and_victory_gates_omit_disabled_fields(engine):
    lua, run = engine
    lua.execute("""
        settings.disabled_caps.CAPABILITY_DISPLAY_TOP_PANEL_YIELDS=true
        settings.disabled_caps.CAPABILITY_DISPLAY_SCORE=true
        settings.disabled_victories={VICTORY_TECHNOLOGY=true, VICTORY_CULTURE=true,
            VICTORY_RELIGIOUS=true, VICTORY_DIPLOMATIC=true}
    """)
    known = civilization(run())
    for field in ("gold", "science_per_turn", "culture_per_turn", "military_strength", "score", "victory"):
        assert field not in known
    assert known["civilization"] == "CIVILIZATION_1"
    assert lua.globals().reads.locations == 0


def test_unavailable_major_roster_fails_opaque(engine):
    lua, run = engine
    lua.execute("PlayerManager.GetWasEverAliveMajors=function() error('SECRET ROSTER') end")
    assert run() == {"ok": False, "error": "unavailable"}


def test_no_generic_foreign_entity_or_requirement_scans_in_template():
    script = build_diplomacy_query("a" * 32)
    for forbidden in ("GetCities", "GetDistricts", "GetUnits", "GetRequirement", "GetAgendaTypes", "GetResearchingTech"):
        assert forbidden not in script
