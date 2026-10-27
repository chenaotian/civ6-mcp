"""Own status remains usable at starvation and missing expansion APIs."""
import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions.base import LUA_HELPERS
from civ6_fair_mcp.extensions.city_status import city_status
from civ6_fair_mcp.inspection_policy import public_inspection


@pytest.fixture
def status_engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute('''
function secret() error("FOREIGN_DATA") end
growth={GetFood=function() return 12 end,GetGrowthThreshold=function() return 35 end,
 GetFoodSurplus=function() return -2 end,GetOverallGrowthModifier=function() return .5 end,
 GetHousing=function() return 4.5 end,GetHousingGrowthModifier=function() return .5 end,
 GetAmenities=function() return 1 end,GetAmenitiesNeeded=function() return 3 end,
 GetTurnsUntilGrowth=function() return -1 end,GetTurnsUntilStarvation=function() return 6 end,
 GetHappiness=function() return 2 end}
identity={GetLoyalty=function() return 70 end,GetMaxLoyalty=function() return 100 end,
 GetLoyaltyPerTurn=function() return -5 end,GetLoyaltyLevel=function() return 1 end,
 GetIdentitySourcesDetailedBreakdown=secret,GetIdentitySourcesBreakdown=secret}
city={GetOwner=function() return 0 end,GetID=function() return 42 end,
 GetPopulation=function() return 5 end,GetGrowth=function() return growth end,
 GetCulturalIdentity=function() return identity end,IsOccupied=function() return false end}
foreign=setmetatable({GetOwner=function() return 2 end},{__index=secret})
player={GetCities=function() return {Members=function()
 local rows={foreign,city};local i=0
 return function() i=i+1;if rows[i] then return i,rows[i] end end
end} end}
GameInfo={Happinesses={[2]={Name="LOC_UNHAPPY"}},LoyaltyLevels={[1]={Name="LOC_WAVERING"}}}
Locale={Lookup=function(key) return "translated:"..key end}
''')

    def run(city_id=42):
        result = vm.execute("local me=0; local out={items={}};\n" + LUA_HELPERS
            + "\nlocal function collect()\n" + city_status({"city_id": city_id})
            + "\nend\ncollect()\nreturn out")
        raw = {"ok": True, "session": "city_status_tests", "player_id": 0,
            "turn": 45, "active_turn": True, "category": "city_status",
            "supported": result["supported"],
            "items": [dict(row) for row in result["items"].values()]}
        projected = public_inspection(raw, "city_status")
        return projected, {x["id"]: x["value"] for x in projected["items"]}
    return vm, run


def test_starving_unhappy_low_housing_city_is_readable(status_engine):
    _, run = status_engine
    result, values = run()
    assert result["supported"] is True
    assert values["food_surplus"] == -2
    assert values["amenities_net"] == -2
    assert values["housing_spare"] == -.5
    assert values["turns_until_growth_active"] is False
    assert "turns_until_growth" not in values
    assert values["turns_until_starvation"] == 6
    assert values["turns_until_starvation_active"] is True
    assert values["happiness"] == "translated:LOC_UNHAPPY"
    assert values["loyalty_per_turn"] == -5


@pytest.mark.parametrize("body", ["nil", "true", "'7'", "0/0", "math.huge", "-2", "1.5"])
def test_unknown_growth_estimate_is_not_invented(status_engine, body):
    vm, run = status_engine
    vm.execute(f"growth.GetTurnsUntilGrowth=function() return {body} end")
    _, values = run()
    assert "turns_until_growth_active" not in values
    assert "turns_until_growth" not in values
    assert values["housing"] == 4.5


@pytest.mark.parametrize("change", [
    "city.GetGrowth=nil", "city.GetGrowth=function() error('missing') end",
    "city.GetGrowth=function() return nil end",
    "city.GetGrowth=function() return false end", "city.GetGrowth=function() return 3 end",
])
def test_missing_growth_component_preserves_loyalty(status_engine, change):
    vm, run = status_engine
    vm.execute(change)
    _, values = run()
    assert "housing" not in values
    assert values["loyalty"] == 70


@pytest.mark.parametrize("change", [
    "growth.GetHousing=nil", "growth.GetHousing=function() error('missing') end",
    "growth.GetHousing=function() return math.huge end",
])
def test_missing_housing_does_not_infer_spare_capacity(status_engine, change):
    vm, run = status_engine
    vm.execute(change)
    _, values = run()
    assert "housing" not in values and "housing_spare" not in values
    assert values["food_stored"] == 12


def test_base_game_without_loyalty_keeps_growth(status_engine):
    vm, run = status_engine
    vm.execute("city.GetCulturalIdentity=nil;GameInfo.LoyaltyLevels=nil")
    _, values = run()
    assert "loyalty" not in values
    assert values["housing"] == 4.5


def test_foreign_and_missing_city_never_read_details(status_engine):
    vm, run = status_engine
    vm.execute("city.GetOwner=function() return 1 end; city.GetID=secret;city.GetGrowth=secret")
    result, values = run()
    assert result["supported"] is False
    assert values == {}


def test_zero_turns_is_distinct_from_no_growth(status_engine):
    vm, run = status_engine
    vm.execute("growth.GetTurnsUntilGrowth=function() return 0 end")
    _, values = run()
    assert values["turns_until_growth"] == 0
    assert values["turns_until_growth_active"] is True


def install_power(vm, *, required=4, free=1, temporary=2, fully=False, project=False):
    vm.execute('''
GameConfiguration={GetValue=function(key) assert(key=="RULESET");return "RULESET_EXPANSION_2" end}
power_reads={component=0,project=0}
power_values={}
power={GetRequiredPower=function() return power_values.required end,
 GetFreePower=function() return power_values.free end,
 GetTemporaryPower=function() return power_values.temporary end,
 IsFullyPowered=function() return power_values.fully end,
 IsFullyPoweredByActiveProject=function()
   power_reads.project=power_reads.project+1;return power_values.project
 end,GetFreePowerSources=secret,GetTemporaryPowerSources=secret,
 GetRequiredPowerSources=secret,GetGeneratedPowerSources=secret}
city.GetPower=function() power_reads.component=power_reads.component+1;return power end
Map=setmetatable({},{__index=secret})
Players=setmetatable({},{__index=secret})
''')
    for key, value in locals().copy().items():
        if key != "vm":
            vm.globals().power_values[key] = value


@pytest.mark.parametrize("required,free,temporary,fully,project,status,usable", [
    (4, 1, 2, False, False, "underpowered", 3),
    (4, 2, 2, True, False, "fully_powered", 4),
    (4, 0, 0, True, True, "fully_powered", 4),
    (0, 2, 3, True, True, "not_required", 5),
    (4, 8, 0, False, False, "underpowered", 8),
    (.01, .04, .04, False, False, "underpowered", .1),
])
def test_power_uses_stock_status_and_project_branch(status_engine, required, free, temporary,
        fully, project, status, usable):
    vm, run = status_engine
    install_power(vm, required=required, free=free, temporary=temporary, fully=fully, project=project)
    result, values = run()
    assert result["supported"] is True
    assert values["power_status"] == status
    assert values["power_usable"] == usable
    assert values["power_fully_powered"] is fully
    assert vm.globals().power_reads.project == int(fully)
    if fully:
        assert values["power_from_active_project"] is project
    else:
        assert "power_from_active_project" not in values
    if required == .01:
        assert values["power_required"] == values["power_free"] == values["power_temporary"] == 0


@pytest.mark.parametrize("rules", ["RULESET_STANDARD", "RULESET_EXPANSION_1", "RULESET_CUSTOM", None])
def test_non_gs_never_reads_power_component(status_engine, rules):
    vm, run = status_engine
    install_power(vm)
    vm.globals().power_rules = rules
    vm.execute('GameConfiguration.GetValue=function() return power_rules end;city.GetPower=secret')
    result, values = run()
    assert result["supported"] is True and values["population"] == 5
    assert not any(key.startswith("power_") for key in values)


@pytest.mark.parametrize("change", [
    "GameConfiguration=nil", "GameConfiguration.GetValue=nil",
    "GameConfiguration.GetValue=function() error('missing') end",
    "city.GetPower=nil", "city.GetPower=function() error('missing') end",
    "city.GetPower=function() return false end", "city.GetPower=function() return nil end",
])
def test_missing_power_capability_preserves_other_city_state(status_engine, change):
    vm, run = status_engine
    install_power(vm)
    vm.execute(change)
    result, values = run()
    assert result["supported"] is True and values["loyalty"] == 70
    assert not any(key.startswith("power_") for key in values)


@pytest.mark.parametrize("change", [
    "power.GetTemporaryPower=nil", "power.GetTemporaryPower=function() error('missing') end",
    "power.GetTemporaryPower=function() return -1 end",
    "power.GetTemporaryPower=function() return '0' end",
    "power.GetTemporaryPower=function() return 0/0 end",
    "power.GetTemporaryPower=function() return math.huge end",
])
def test_missing_power_quantity_omits_sum_without_inventing_zero(status_engine, change):
    vm, run = status_engine
    install_power(vm)
    vm.execute(change)
    _, values = run()
    assert values["power_status"] == "underpowered"
    assert values["power_required"] == 4
    assert "power_temporary" not in values and "power_usable" not in values


@pytest.mark.parametrize("method", ["IsFullyPowered", "IsFullyPoweredByActiveProject"])
@pytest.mark.parametrize("invalid", ["nil", "1", "'false'", "error('missing')"])
def test_unknown_power_boolean_does_not_select_a_display_branch(status_engine, method, invalid):
    vm, run = status_engine
    install_power(vm, fully=True)
    vm.execute(f"power.{method}=function() return {invalid} end")
    _, values = run()
    assert values["power_required"] == 4
    assert "power_usable" not in values and "power_from_active_project" not in values
    if method == "IsFullyPowered":
        assert "power_status" not in values and "power_fully_powered" not in values
        assert vm.globals().power_reads.project == 0
    else:
        assert values["power_status"] == "fully_powered"


def test_project_can_supply_usable_power_without_optional_source_totals(status_engine):
    vm, run = status_engine
    install_power(vm, fully=True, project=True)
    vm.execute("power.GetFreePower=nil;power.GetTemporaryPower=nil")
    _, values = run()
    assert values["power_usable"] == 4 and values["power_from_active_project"] is True
    assert "power_free" not in values and "power_temporary" not in values


def test_missing_requirement_does_not_classify_or_derive_usable(status_engine):
    vm, run = status_engine
    install_power(vm, fully=True, project=True)
    vm.execute("power.GetRequiredPower=nil")
    _, values = run()
    assert values["power_fully_powered"] is True
    assert "power_status" not in values and "power_required" not in values and "power_usable" not in values
