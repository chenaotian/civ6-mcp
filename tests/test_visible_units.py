"""Run the real Lua helper, with getter traps on all undetected units."""

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.visible_units import UNIT_HELPERS


ENGINE = r'''
local me = 0
local function array(value) return value end
settings = {revealed=true, visible=true}
counts = {enumerations=0, hidden_reads=0, private_reads=0, detected_getters=0, gates=0}
units = {}
detection = {}
gate_seen = {}
MapLayers = {ANY=9}
Units = {GetUnitsInPlotLayerID=function(x,y,layer)
    assert(x==3 and y==4 and layer==9)
    counts.enumerations=counts.enumerations+1
    return units
end}
local vis = {
    IsRevealed=function() return settings.revealed end,
    IsVisible=function() return settings.visible end,
    IsUnitVisible=function(self,unit)
        counts.gates=counts.gates+1
        if detection[unit] == 'error' then error('SECRET DETECTION ENGINE ERROR') end
        gate_seen[unit] = true
        return detection[unit]
    end
}
visibility = vis
plot = {GetX=function() return 3 end, GetY=function() return 4 end}
GameInfo = {Units={
    [0]={UnitType='UNIT_WARRIOR'}, [1]={UnitType='UNIT_SUBMARINE'},
    [2]={UnitType='UNIT_SCOUT'}, [3]={UnitType='UNIT_SPY'}
}}
Locale = {Lookup=function(value) return value end}
function hidden(result)
    local unit = setmetatable({}, {__index=function()
        counts.hidden_reads=counts.hidden_reads+1
        error('SECRET HIDDEN UNIT PROPERTY')
    end})
    detection[unit] = result
    return unit
end
function detected(id, owner, unit_type)
    local unit = {}
    local function read(value)
        assert(gate_seen[unit], 'GETTER BEFORE DETECTION')
        counts.detected_getters=counts.detected_getters+1
        return value
    end
    unit.IsDelayedDeath=function() return read(false) end
    unit.GetID=function() return read(id) end
    unit.GetOwner=function() return read(owner or 1) end
    unit.GetX=function() return read(3) end
    unit.GetY=function() return read(4) end
    unit.GetUnitType=function() return read(unit_type or 0) end
    unit.GetName=function() return read('单位名称') end
    unit.GetDamage=function() return read(12) end
    unit.GetMaxDamage=function() return read(100) end
    unit.GetCombat=function() return read(60) end
    unit.GetRangedCombat=function() return read(70) end
    unit.GetMovesRemaining=function() counts.private_reads=counts.private_reads+1; error('SECRET MOVES') end
    unit.GetBuildCharges=function() counts.private_reads=counts.private_reads+1; error('SECRET CHARGES') end
    unit.GetSpyOperation=function() counts.private_reads=counts.private_reads+1; error('SECRET MISSION') end
    unit.GetExperience=function() counts.private_reads=counts.private_reads+1; error('SECRET PROMOTIONS') end
    detection[unit] = true
    return unit
end
'''


@pytest.fixture
def engine():
    lua = LuaRuntime(unpack_returned_tuples=True)
    query = lua.execute(ENGINE + UNIT_HELPERS + "\nreturn function() return visible_units_at(plot, 19) end")

    def run():
        result = query()
        if result is None:
            return None
        return [dict(item.items()) for item in result.values()]

    return lua, run


def test_detected_unit_has_only_confirmed_public_fields(engine):
    lua, run = engine
    lua.execute("units = {detected(8, 1, 1)}")
    assert run() == [{
        "id": 8, "owner_id": 1, "x": 3, "y": 4, "detected": True,
        "type": "UNIT_SUBMARINE", "name": "单位名称", "damage": 12,
        "max_damage": 100, "combat": 60, "ranged_combat": 70,
    }]
    assert lua.globals().counts.private_reads == 0


def test_hidden_units_never_have_any_property_read_even_id_or_owner(engine):
    lua, run = engine
    lua.execute("units = {hidden(false), hidden(nil), hidden(1), hidden('error')}")
    assert run() == []
    assert lua.globals().counts.hidden_reads == 0
    assert lua.globals().counts.gates == 4


def test_hidden_units_cannot_affect_response_or_sort_order(engine):
    lua, run = engine
    lua.execute("a=detected(20,2); b=detected(4,1); units={a,b}")
    baseline = run()
    lua.execute("units={hidden(false),b,hidden('error'),a,hidden(false)}")
    assert run() == baseline
    lua.execute("for i=1,1000 do units[#units+1]=hidden(false) end")
    assert run() == baseline
    assert lua.globals().counts.hidden_reads == 0


@pytest.mark.parametrize("kind", [1, 2, 3])
def test_submarines_camouflaged_recon_and_spies_require_engine_detection(engine, kind):
    lua, run = engine
    lua.execute(f"candidate=detected(5,1,{kind}); detection[candidate]=false; units={{candidate}}")
    assert run() == []
    assert lua.globals().counts.detected_getters == 0
    # Stand-in for the ENGINE changing the detection result after adjacency,
    # a detector's sight, or another actual rule; the adapter has no heuristic.
    lua.execute("detection[candidate]=true")
    assert len(run()) == 1
    lua.execute("detection[candidate]=false; gate_seen[candidate]=nil; counts.detected_getters=0")
    assert run() == []
    assert lua.globals().counts.detected_getters == 0
    assert lua.globals().counts.private_reads == 0


@pytest.mark.parametrize("setup", [
    "settings.revealed=false", "settings.visible=false",
    "visibility.IsUnitVisible=nil", "Units=nil", "Units.GetUnitsInPlotLayerID=nil",
    "MapLayers=nil", "MapLayers.ANY=nil",
])
def test_missing_proof_fails_closed_before_enumeration(engine, setup):
    lua, run = engine
    lua.execute("units={hidden(false), detected(2,1)}")
    lua.execute(setup)
    assert run() is None
    assert lua.globals().counts.enumerations == 0
    assert lua.globals().counts.hidden_reads == 0


@pytest.mark.parametrize("setup", [
    "Units.GetUnitsInPlotLayerID=function() error('SECRET') end",
    "Units.GetUnitsInPlotLayerID=function() return nil end",
    "Units.GetUnitsInPlotLayerID=function() return 12 end",
])
def test_container_failure_returns_unknown_without_error_details(engine, setup):
    lua, run = engine
    lua.execute(setup)
    assert run() is None


@pytest.mark.parametrize("setup", [
    "candidate.GetX=function() return 99 end", "candidate.GetY=function() return -1 end",
    "candidate.GetOwner=function() return 64 end", "candidate.GetOwner=function() return 0 end",
    "candidate.GetID=function() return -1 end", "candidate.GetID=function() return 0/0 end",
    "candidate.IsDelayedDeath=function() return true end", "candidate.IsDelayedDeath=nil",
])
def test_unusable_visible_records_are_omitted(engine, setup):
    lua, run = engine
    lua.execute("candidate=detected(5,1); units={candidate}")
    lua.execute(setup)
    assert run() == []


def test_optional_unsupported_or_invalid_fields_are_omitted(engine):
    lua, run = engine
    lua.execute("""
        candidate=detected(5,1); units={candidate}
        candidate.GetDamage=function() error('SECRET ENGINE ERROR') end
        candidate.GetMaxDamage=function() return math.huge end
        candidate.GetCombat=nil
        candidate.GetRangedCombat=function() return -1 end
        candidate.GetName=function() return string.rep('x',257) end
        candidate.GetUnitType=function() return 1000 end
    """)
    assert run() == [{"id": 5, "owner_id": 1, "x": 3, "y": 4, "detected": True}]


def test_output_bound_and_dedup_depend_only_on_detected_records(engine):
    lua, run = engine
    lua.execute("for i=300,1,-1 do units[#units+1]=detected(i,1) end")
    baseline = run()
    assert len(baseline) == 256
    assert [item["id"] for item in baseline] == list(range(1, 257))
    lua.execute("units[#units+1]=units[1]; for i=1,1000 do units[#units+1]=hidden(false) end")
    assert run() == baseline
    assert lua.globals().counts.hidden_reads == 0
