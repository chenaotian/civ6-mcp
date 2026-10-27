"""A city-center alias is not a second city bombardment option."""
import pytest

from test_extension_units import engine


TARGET = {"city_id": 20, "x": 3, "y": 2}


@pytest.fixture
def combat_engine(engine):
    vm, run = engine
    vm.execute('''
settings.center_id=30;settings.city_can=true;settings.encampment_can=true
reads.district_scans=0;reads.center_can=0;reads.encampment_can=0
city.GetDistrictID=function() return settings.center_id end
center=own_district
encampment={GetOwner=function() return 0 end,GetID=function() return 31 end}
foreign_district=setmetatable({GetOwner=function() return 1 end},{__index=forbidden})
district_list={foreign_district,center,encampment}
city.GetDistricts=function()
    reads.district_scans=reads.district_scans+1
    return {Members=function() return members(district_list) end}
end
CityManager.CanStartCommand=function(actor,command,params)
    assert(command==CityCommandTypes.RANGE_ATTACK and params.x==3 and params.y==2)
    if actor==city then return settings.city_can end
    if actor==center then reads.center_can=reads.center_can+1;return forbidden() end
    assert(actor==encampment)
    reads.encampment_can=reads.encampment_can+1
    return settings.encampment_can
end
''')

    def query():
        result = run("city_combat", TARGET, True)
        assert result["ok"] is True and result["supported"] is True
        assert len(vm.globals().calls) == 0 and vm.globals().reads.hidden == 0
        return [item["action"] for item in result["items"]]

    return vm, run, query


def test_center_is_removed_before_native_probe_and_encampment_is_preserved(combat_engine):
    vm, _, query = combat_engine
    assert query() == [
        {"type": "city_attack", **TARGET},
        {"type": "district_attack", **TARGET, "district_id": 31},
    ]
    assert vm.globals().reads.center_can == 0
    assert vm.globals().reads.encampment_can == 1
    assert vm.globals().reads.district_scans == 1


def test_center_only_city_has_one_attack_option(combat_engine):
    vm, _, query = combat_engine
    vm.execute("district_list={center}")
    assert query() == [{"type": "city_attack", **TARGET}]
    assert vm.globals().reads.center_can == 0


def test_center_alias_does_not_restore_an_unavailable_city_strike(combat_engine):
    vm, _, query = combat_engine
    vm.execute("settings.city_can=false")
    assert query() == [{"type": "district_attack", **TARGET, "district_id": 31}]
    assert vm.globals().reads.center_can == 0


def test_real_encampment_still_requires_its_own_native_permission(combat_engine):
    vm, _, query = combat_engine
    vm.execute("settings.encampment_can=false")
    assert query() == [{"type": "city_attack", **TARGET}]
    assert vm.globals().reads.encampment_can == 1


@pytest.mark.parametrize("change", [
    "city.GetDistrictID=nil", "city.GetDistrictID=false",
    "city.GetDistrictID=function() error('CENTER_UNAVAILABLE') end",
    "city.GetDistrictID=nil;setmetatable(city,{__index=function() error('GETTER_UNAVAILABLE') end})",
    "settings.center_id=nil", "settings.center_id=false", "settings.center_id=true",
    "settings.center_id='30'", "settings.center_id=-1", "settings.center_id=30.5",
    "settings.center_id=0/0", "settings.center_id=math.huge", "settings.center_id=-math.huge",
    "settings.center_id=2147483648", "settings.center_id={}",
])
def test_unknown_center_preserves_city_option_without_scanning_districts(combat_engine, change):
    vm, _, query = combat_engine
    vm.execute(change + ";city.GetDistricts=forbidden")
    assert query() == [{"type": "city_attack", **TARGET}]
    assert vm.globals().reads.district_scans == 0
    assert vm.globals().reads.encampment_can == 0


@pytest.mark.parametrize("center_id", [0, 2_147_483_647])
def test_center_identity_uses_valid_packed_id_without_guessing_or_truncation(combat_engine, center_id):
    vm, _, query = combat_engine
    vm.execute(f"settings.center_id={center_id};center.GetID=function() return settings.center_id end")
    assert query() == [
        {"type": "city_attack", **TARGET},
        {"type": "district_attack", **TARGET, "district_id": 31},
    ]
    assert vm.globals().reads.center_can == 0


@pytest.mark.parametrize("value", ["nil", "false", "'31'", "-1", "31.5", "0/0", "math.huge", "2147483648"])
def test_malformed_district_identity_is_not_used_as_an_attack_candidate(combat_engine, value):
    vm, _, query = combat_engine
    vm.execute(f"encampment.GetID=function() return {value} end")
    assert query() == [{"type": "city_attack", **TARGET}]
    assert vm.globals().reads.encampment_can == 0


def test_failing_district_id_does_not_erase_city_option(combat_engine):
    vm, _, query = combat_engine
    vm.execute("encampment.GetID=function() error('DISTRICT_UNAVAILABLE') end")
    assert query() == [{"type": "city_attack", **TARGET}]
    assert vm.globals().reads.encampment_can == 0


@pytest.mark.parametrize("kind,extra,actor", [
    ("city_attack", {}, "city"),
    ("district_attack", {"district_id": 30}, "center"),
    ("district_attack", {"district_id": 31}, "encampment"),
])
def test_existing_action_submission_semantics_are_unchanged(combat_engine, kind, extra, actor):
    vm, run, _ = combat_engine
    vm.execute(f'''
city.GetDistrictID=forbidden
CityManager.CanStartCommand=function(actual,command,params)
    assert(actual=={actor} and command==CityCommandTypes.RANGE_ATTACK)
    assert(params.x==3 and params.y==2)
    return true
end
''')
    result = run(kind, {**TARGET, **extra})
    assert result["accepted"] is True
    assert len(vm.globals().calls) == 1 and vm.globals().reads.hidden == 0
