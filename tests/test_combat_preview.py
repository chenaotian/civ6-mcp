"""Real Lua preview gates, deliberately hostile target and result fixtures."""
from copy import deepcopy

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions import build_inspection_query, registries
from civ6_fair_mcp.extensions.base import validate
from civ6_fair_mcp.extensions.combat_preview import FIELDS, QUERIES
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import PolicyError
from civ6_fair_mcp.waiting import ReadRequest, prepare_read


PARAMS = {"attacker_kind": "unit_ranged", "attacker_id": 10,
          "target_owner_id": 1, "target_unit_id": 40, "x": 3, "y": 2}


@pytest.fixture
def engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute(r'''
rawget=nil;unpack=nil;table.unpack=nil
settings={active=true,owner=0,revealed=true,visible=true,detected=true,busy=false,processing=false,
    tactical=true,can=true,compatible=true,war=false,at_war=true,moves=2,combat=35,ranged=40,bombard=0,
    distance=1,target_owner=1,target_id=40,target_x=3,target_y=2,dead=false}
reads={private=0,hidden=0,plot=0,enumeration=0,legal=0,compatible=0,simulate=0,detected_getters=0,war_change=0,at_war=0}
function forbidden() reads.private=reads.private+1;error('PRIVATE_UNAUDITED') end
function members(list) local i=0;return function() i=i+1;if list[i] then return i,list[i] end end end
ComponentType={UNIT=1,CITY=2,DISTRICT=3}
CombatTypes={MELEE=10,RANGED=11,BOMBARD=12,AIR=13,RELIGIOUS=14}
CombatResultParameters={}
for _,name in ipairs({'ATTACKER','DEFENDER','ID','COMBAT_TYPE','COMBAT_STRENGTH','STRENGTH_MODIFIER',
    'PREVIEW_TEXT_HEALTH','PREVIEW_TEXT_TERRAIN','PREVIEW_TEXT_OPPONENT','PREVIEW_TEXT_MODIFIER',
    'PREVIEW_TEXT_ASSIST','PREVIEW_TEXT_PROMOTION','PREVIEW_TEXT_DEFENSES','PREVIEW_TEXT_RESOURCES'}) do
    CombatResultParameters[name]=name
end
function own_read(v) assert(settings.owner==0);return v end
unit={GetOwner=function() return settings.owner end,GetID=function() return own_read(10) end,
    GetX=function() return 2 end,GetY=function() return 2 end,GetUnitType=function() return 1 end,
    GetMovesRemaining=function() return settings.moves end,GetCombat=function() return settings.combat end,
    GetRangedCombat=function() return settings.ranged end,GetBombardCombat=function() return settings.bombard end,
    IsDelayedDeath=function() return false end,GetComponentID=function() return {type=1,player=0,id=10} end}
city={GetOwner=function() return 0 end,GetID=function() return 20 end,GetDistrictID=function() return 30 end,
    GetComponentID=function() return {type=2,player=0,id=20} end}
center={GetOwner=function() return 0 end,GetID=function() return 30 end,GetType=function() return 1 end,
    GetComponentID=function() return {type=3,player=0,id=30} end}
encampment={GetOwner=function() return 0 end,GetID=function() return 31 end,GetType=function() return 2 end,
    GetComponentID=function() return {type=3,player=0,id=31} end}
unit_list={unit};city_list={city};district_list={center,encampment}
diplomacy={IsAtWarWith=function(self,id)
    assert(id==1 and settings.detected);reads.at_war=reads.at_war+1;return settings.at_war end}
player={GetDiplomacy=function() return diplomacy end,
    GetUnits=function() return {Members=function() return members(unit_list) end} end,
    GetCities=function() return {Members=function() return members(city_list) end} end,
    GetDistricts=function() return {Members=function() return members(district_list) end} end}
function detected_read(value)
    assert(settings.detected and settings.visible and settings.revealed,'TARGET READ BEFORE PROOF')
    reads.detected_getters=reads.detected_getters+1;return value
end
target=setmetatable({GetOwner=function() return detected_read(settings.target_owner) end,
    GetID=function() return detected_read(settings.target_id) end,GetX=function() return detected_read(settings.target_x) end,
    GetY=function() return detected_read(settings.target_y) end,IsDelayedDeath=function() return detected_read(settings.dead) end,
    GetComponentID=function() return detected_read({type=1,player=settings.target_owner,id=settings.target_id}) end},
    {__index=forbidden})
hidden=setmetatable({}, {__index=function() reads.hidden=reads.hidden+1;error('HIDDEN UNIT GETTER') end})
candidates={hidden,target}
vis={IsRevealed=function() return settings.revealed end,IsVisible=function() return settings.visible end,
    IsUnitVisible=function(self,value) return value==target and settings.detected end}
Map={GetGridSize=function() return 100,80 end,GetPlot=function(x,y)
    assert(settings.revealed and settings.visible);reads.plot=reads.plot+1;return {} end,
    GetPlotDistance=function() return settings.distance end,GetPlotByIndex=forbidden}
MapLayers={ANY=9}
Units={GetUnitsInPlotLayerID=function(x,y,layer)
    assert(settings.visible and settings.revealed and x==3 and y==2 and layer==9)
    reads.enumeration=reads.enumeration+1;return candidates end}
Players=setmetatable({}, {__index=forbidden})
UI={IsGameCoreBusy=function() return settings.busy end,IsProcessingMessages=function() return settings.processing end,
    SetInterfaceMode=forbidden,SelectUnit=forbidden,SelectCity=forbidden}
Game={IsAllowTacticalCommands=function(me) assert(me==0);return settings.tactical end}
UnitOperationTypes={PARAM_X='x',PARAM_Y='y',PARAM_MODIFIERS='mods'}
UnitOperationMoveModifiers={ATTACK=7}
CityCommandTypes={RANGE_ATTACK=700}
GameInfo={Units={[1]={Domain='DOMAIN_LAND'}},Districts={[1]={DistrictType='DISTRICT_CITY_CENTER'},
    [2]={DistrictType='DISTRICT_ENCAMPMENT'}},UnitOperations={
    UNITOPERATION_MOVE_TO={Hash=-1234567890,VisibleInUI=true},
    UNITOPERATION_RANGE_ATTACK={Hash=2345678901,VisibleInUI=true}}}
UnitManager={GetUnit=forbidden,RequestOperation=forbidden,
    CanStartOperation=function(actor,hash,unused,params,results)
        assert(actor==unit and unused==nil and results==false and params.x==3 and params.y==2)
        assert(settings.detected and settings.visible and settings.revealed)
        if hash==-1234567890 then assert(params.mods==7) else assert(hash==2345678901 and params.mods==nil) end
        reads.legal=reads.legal+1;return settings.can
    end}
CityManager={RequestCommand=forbidden,CanStartCommand=function(actor,hash,params)
    assert((actor==city or actor==encampment) and hash==700 and params.x==3 and params.y==2)
    assert(settings.detected and settings.visible and settings.revealed)
    reads.legal=reads.legal+1;return settings.can
end}
function result_side(component,base,modifier,texts)
    return setmetatable({ID=component,COMBAT_STRENGTH=base,STRENGTH_MODIFIER=modifier,
        PREVIEW_TEXT_HEALTH=texts[1],PREVIEW_TEXT_TERRAIN=texts[2],PREVIEW_TEXT_OPPONENT={},
        PREVIEW_TEXT_MODIFIER={},PREVIEW_TEXT_ASSIST={},PREVIEW_TEXT_PROMOTION={},
        PREVIEW_TEXT_DEFENSES={},PREVIEW_TEXT_RESOURCES={}}, {__index=forbidden})
end
CombatManager={IsAttackChangeWarState=function(comp,x,y)
    assert(settings.detected and x==3 and y==2 and comp.type==1)
    reads.war_change=reads.war_change+1
    if settings.war then return {1} end;return {} end,
    CanAttackTarget=function(a,d,kind)
        assert(settings.detected and settings.visible and settings.revealed)
        assert(a.player==0 and d.player==1 and d.id==40)
        -- Deliberately model a compatibility distinction: CITY is
        -- not the canonical combat actor, its own center DISTRICT is.
        if a.type==ComponentType.CITY then return false end
        seen_compatibility_attacker=a;seen_compatibility_type=kind
        reads.compatible=reads.compatible+1;return settings.compatible end,
    SimulateAttackVersus=function(a,d,kind)
        assert(reads.legal==1 and settings.can)
        if a.type==3 then assert(reads.compatible==0 and settings.at_war)
        else assert(reads.compatible==1 and settings.compatible) end
        reads.simulate=reads.simulate+1
        seen_attacker=a;seen_defender=d;seen_combat_type=kind
        if a.type==3 then assert(kind==nil) end
        local resolved=kind or (a.type==3 and (settings.district_type or CombatTypes.RANGED) or CombatTypes.MELEE)
        last_result=setmetatable({ATTACKER=result_side(a,40,-3,{{'health_penalty'},{}}),
            DEFENDER=result_side(d,30,6,{{},{'terrain_bonus'}}),COMBAT_TYPE=resolved},{__index=forbidden})
        if mutate_result then mutate_result(last_result) end
        return last_result
    end,SimulateAttackInto=forbidden,SimulatePriorityAttackInto=forbidden}
Locale={Lookup=function(value)
    if value=='health_penalty' then return '-3 受伤' elseif value=='terrain_bonus' then return '+6 地形防御' end
    return value
end}
''')

    def run(params=None):
        params = dict(PARAMS if params is None else params)
        validate(params, FIELDS)
        result = vm.execute("local me=0;local out={active_turn=settings.active};local function array(v) return v end\n"
            + QUERIES["combat_preview"].body(params) + "\nreturn out")
        raw = {"ok": True, "session": "combat_preview_tests", "player_id": 0, "turn": 111,
               "active_turn": vm.globals().settings.active, "category": "combat_preview",
               "supported": result["supported"], "items": [dict(v) for v in result["items"].values()]}
        if result["combat_preview"] is not None:
            raw["combat_preview"] = dict(result["combat_preview"])
        public = public_inspection(raw, "combat_preview", params)
        assert vm.globals().reads.private == vm.globals().reads.hidden == 0
        return raw, {item["id"]: item["value"] for item in public["items"]}
    return vm, run


@pytest.mark.parametrize("kind,actor,expected_type,simulation_id", [
    ("unit_ranged", 10, 11, 10), ("unit_melee", 10, None, 10),
    ("city", 20, None, 30), ("district", 31, None, 31),
])
def test_exact_target_preview_strength_modifiers_and_no_mutation(engine, kind, actor, expected_type, simulation_id):
    vm, run = engine
    if kind == "unit_melee":
        vm.execute("settings.ranged=0")
    raw, values = run({**PARAMS, "attacker_kind": kind, "attacker_id": actor})
    assert raw["supported"] is True
    assert values == {"attacker_strength": 37, "defender_strength": 36,
        "attacker_modifier:1": "-3 受伤", "defender_modifier:1": "+6 地形防御",
        "combat_type": "melee" if kind == "unit_melee" else "ranged"}
    assert vm.globals().seen_attacker.id == simulation_id
    assert vm.globals().seen_defender.id == 40
    assert vm.globals().seen_combat_type == expected_type
    assert vm.globals().reads.simulate == 1
    assert vm.globals().reads.compatible == (1 if kind in {"city", "district"} else 2)
    assert not any("damage" in key or "hit" in key or "chance" in key for key in values)


def test_bombard_mode_uses_stock_ranged_vs_bombard_comparison(engine):
    vm, run = engine
    vm.execute("settings.bombard=55;GameInfo.Units[1].Domain='DOMAIN_SEA'")
    _, values = run()
    assert values["combat_type"] == "bombard" and vm.globals().seen_combat_type == 12


def test_native_float_ids_and_coordinates_do_not_break_strict_python_proof(engine):
    vm, run = engine
    vm.execute("settings.target_owner=1.0;settings.target_id=40.0;settings.target_x=3.0;settings.target_y=2.0;"
               "unit.GetID=function() return 10.0 end")
    raw, values = run()
    assert values["attacker_strength"] == 37
    for key in ("attacker_id", "attacker_owner_id", "target_owner_id", "target_unit_id", "x", "y"):
        assert type(raw["combat_preview"][key]) is int


@pytest.mark.parametrize("change", ["settings.revealed=false", "settings.visible=false"])
def test_fog_and_unrevealed_never_obtain_plot_unit_container_or_simulate(engine, change):
    vm, run = engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] and not values
    assert vm.globals().reads.plot == vm.globals().reads.enumeration == 0
    assert vm.globals().reads.legal == vm.globals().reads.simulate == 0


@pytest.mark.parametrize("change", ["settings.detected=false", "candidates={hidden}",
    "vis.IsUnitVisible=function() error('HIDDEN_DETECTION_ERROR') end"])
def test_hidden_unit_has_no_getter_or_legality_probe(engine, change):
    vm, run = engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] and not values
    assert vm.globals().reads.detected_getters == 0
    assert vm.globals().reads.legal == vm.globals().reads.compatible == vm.globals().reads.simulate == 0


@pytest.mark.parametrize("change", ["settings.owner=1", "unit_list={}",
    "settings.active=false", "settings.busy=true", "settings.processing=true", "settings.tactical=false"])
def test_no_own_actor_or_current_readiness_means_no_target_read(engine, change):
    vm, run = engine
    vm.execute(change)
    _, values = run()
    assert not values and vm.globals().reads.enumeration == vm.globals().reads.simulate == 0


@pytest.mark.parametrize("change", ["settings.can=false", "settings.compatible=false", "settings.war=true",
    "settings.target_owner=2", "settings.target_id=41", "settings.target_x=4", "settings.dead=true",
    "settings.moves=0", "settings.combat=0", "settings.ranged=0", "GameInfo.Units[1].Domain='DOMAIN_AIR'"])
def test_no_normal_legal_attack_or_wrong_target_never_simulates(engine, change):
    vm, run = engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] and not values and vm.globals().reads.simulate == 0


@pytest.mark.parametrize("change", ["settings.distance=2;settings.ranged=0", "settings.ranged=40", "settings.bombard=50"])
def test_melee_is_adjacent_and_never_inferred_from_archer_defensive_combat(engine, change):
    vm, run = engine
    vm.execute(change)
    _, values = run({**PARAMS, "attacker_kind": "unit_melee"})
    assert not values and vm.globals().reads.simulate == 0


def test_center_district_has_only_canonical_city_preview(engine):
    vm, run = engine
    _, values = run({**PARAMS, "attacker_kind": "district", "attacker_id": 30})
    assert not values and vm.globals().reads.simulate == 0


def test_city_center_changed_owner_during_simulation_drops_preview(engine):
    vm, run = engine
    vm.execute("mutate_result=function() center.GetOwner=function() return 2 end end")
    _, values = run({**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert not values and vm.globals().reads.simulate == 1


@pytest.mark.parametrize("kind,actor,source", [("city", 20, 30), ("district", 31, 31)])
@pytest.mark.parametrize("native_type,expected", [(11, "ranged"), (12, "bombard")])
def test_city_and_district_use_actual_native_range_type_and_district_compatibility(engine, kind, actor, source, native_type, expected):
    vm, run = engine
    vm.execute(f"settings.district_type={native_type};CombatManager.IsAttackChangeWarState=forbidden")
    raw, values = run({**PARAMS, "attacker_kind": kind, "attacker_id": actor})
    assert raw["supported"] is True and values["combat_type"] == expected
    assert values["attacker_strength"] == 37 and values["defender_strength"] == 36
    assert vm.globals().seen_compatibility_attacker.type == 3
    assert vm.globals().seen_compatibility_attacker.id == source
    assert vm.globals().seen_compatibility_type == native_type
    assert vm.globals().reads.compatible == 1 and vm.globals().reads.at_war == 2
    assert vm.globals().reads.war_change == 0


@pytest.mark.parametrize("native_type", [10, 13, 14, 999])
def test_city_rejects_nonordinary_simulation_types_before_compatibility_or_text(engine, native_type):
    vm, run = engine
    vm.execute(f"settings.district_type={native_type};Locale.Lookup=forbidden")
    raw, values = run({**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert raw["supported"] and not values and vm.globals().reads.simulate == 1
    assert vm.globals().reads.compatible == 0


@pytest.mark.parametrize("change", [
    "mutate_result=function(r) setmetatable(r,nil);r.COMBAT_TYPE=nil end",
    "mutate_result=function(r) r.COMBAT_TYPE=0/0 end",
    "CombatTypes.BOMBARD=nil;mutate_result=function(r) setmetatable(r,nil);r.COMBAT_TYPE=nil end",
])
def test_missing_or_nonnumeric_native_type_cannot_equal_a_missing_bombard_constant(engine, change):
    vm, run = engine
    vm.execute(change)
    raw, values = run({**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert raw["supported"] is False and not values


@pytest.mark.parametrize("change", ["settings.at_war=false", "settings.at_war=nil", "settings.at_war=1"])
def test_city_requires_explicit_war_with_the_detected_target_before_simulation(engine, change):
    vm, run = engine
    vm.execute(change)
    raw, values = run({**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert raw["supported"] and not values
    assert vm.globals().reads.legal == vm.globals().reads.simulate == vm.globals().reads.war_change == 0


def test_city_missing_public_war_api_is_unsupported_and_does_not_simulate(engine):
    vm, run = engine
    vm.execute("diplomacy.IsAtWarWith=nil")
    raw, values = run({**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert raw["supported"] is False and not values and vm.globals().reads.simulate == 0


def test_city_incompatible_target_and_peace_during_simulation_never_publish(engine):
    vm, run = engine
    vm.execute("settings.compatible=false;Locale.Lookup=forbidden")
    raw, values = run({**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert raw["supported"] and not values and vm.globals().reads.simulate == 1
    vm.execute("settings.compatible=true;reads.legal=0;reads.compatible=0;"
               "Locale.Lookup=function(v) return v end;mutate_result=function() settings.at_war=false end")
    _, values = run({**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert not values


@pytest.mark.parametrize("change", [
    "CombatManager.SimulateAttackVersus=nil", "CombatManager.CanAttackTarget=nil",
    "CombatManager.IsAttackChangeWarState=nil", "UnitManager.CanStartOperation=nil",
    "vis.IsUnitVisible=nil", "Units.GetUnitsInPlotLayerID=nil", "UI.IsGameCoreBusy=nil",
    "GameInfo.UnitOperations.UNITOPERATION_RANGE_ATTACK=nil",
    "GameInfo.UnitOperations.UNITOPERATION_RANGE_ATTACK.VisibleInUI=false",
    "unit.GetMovesRemaining=nil", "target.GetComponentID=false",
    "UnitManager.CanStartOperation=function() error('SECRET_ERROR') end",
])
def test_missing_or_failing_essential_native_api_is_unsupported(engine, change):
    vm, run = engine
    vm.execute(change)
    raw, values = run()
    assert raw["supported"] is False and not values and vm.globals().reads.simulate == 0


@pytest.mark.parametrize("mutation", [
    "r.DEFENDER.ID={type=1,player=1,id=999}", "r.ATTACKER.ID={type=1,player=2,id=10}",
    "r.DEFENDER.ID={type=3,player=1,id=40}", "r.COMBAT_TYPE=CombatTypes.AIR",
    "settings.visible=false", "settings.detected=false", "settings.busy=true",
    "settings.target_x=4", "settings.owner=1", "settings.dead=true",
])
def test_changed_identity_visibility_or_unexpected_result_never_publishes(engine, mutation):
    vm, run = engine
    vm.execute("mutate_result=function(r) " + mutation + " end")
    _, values = run()
    assert not values and vm.globals().reads.simulate == 1


@pytest.mark.parametrize("mutation", [
    "r.ATTACKER.COMBAT_STRENGTH=0/0", "r.DEFENDER.STRENGTH_MODIFIER=math.huge",
    "r.ATTACKER.PREVIEW_TEXT_TERRAIN={[2]='sparse'}", "r.DEFENDER.PREVIEW_TEXT_HEALTH='wrong_type'",
    "r.DEFENDER.PREVIEW_TEXT_HEALTH={'bad'..string.char(0)..'text'}",
    "for i=1,65 do r.DEFENDER.PREVIEW_TEXT_HEALTH[i]='too many' end",
])
def test_malformed_results_drop_all_partial_statistics(engine, mutation):
    vm, run = engine
    vm.execute("mutate_result=function(r) " + mutation + " end")
    raw, values = run()
    assert raw["supported"] is False and not values


def test_negative_total_is_clamped_like_stock_label_and_unknown_metadata_never_leaks(engine):
    vm, run = engine
    vm.execute("mutate_result=function(r) r.ATTACKER.COMBAT_STRENGTH=2;r.ATTACKER.STRENGTH_MODIFIER=-9 end")
    _, values = run()
    assert values["attacker_strength"] == 0


@pytest.mark.parametrize("key,value", [
    ("attacker_owner_id", 2), ("attacker_owner_id", False), ("attacker_id", 11),
    ("attacker_kind", "city"), ("target_owner_id", 2), ("target_unit_id", 41),
    ("x", 4), ("y", 3), ("revealed", False), ("visible", False), ("detected", False),
    ("legal_action", False), ("can_attack_target", False), ("attacker_matches", False),
    ("defender_matches", False), ("source", "raw_engine"),
])
def test_python_rejects_bad_identity_or_permission_before_content_validation(engine, key, value):
    _, run = engine
    raw, _ = run()
    raw["combat_preview"][key] = value
    raw["items"] = object()  # Must not inspect possibly hidden content.
    assert public_inspection(raw, "combat_preview", PARAMS)["items"] == []


def test_python_requires_request_binding_and_ignores_forged_generic_scopes(engine):
    _, run = engine
    raw, _ = run()
    assert public_inspection(raw, "combat_preview")["items"] == []
    assert public_inspection(raw, "combat_preview", {**PARAMS, "target_unit_id": 41})["items"] == []
    raw.pop("combat_preview")
    raw["items"] = [{"id": "secret", "scope": "public", "value": "HIDDEN"}]
    assert public_inspection(raw, "combat_preview", PARAMS)["items"] == []


@pytest.mark.parametrize("item", [
    {"id": "damage_to", "value": 32}, {"id": "attacker_strength", "value": True},
    {"id": "attacker_modifier:257", "value": "excess"},
    {"id": "attacker_modifier:2", "value": "gap"},
    {"id": "attacker_modifier:1", "value": "text", "action": {}},
    {"id": "attacker_modifier:1", "value": "text", "description": "raw result"},
    {"id": "combat_type", "value": "air"},
])
def test_python_accepts_only_a_complete_fixed_output_schema(engine, item):
    _, run = engine
    raw, _ = run()
    if item["id"] in {"attacker_modifier:2", "attacker_modifier:257"}:
        raw["items"] = [row for row in raw["items"] if not row["id"].startswith("attacker_modifier:")]
    else:
        raw["items"] = [row for row in raw["items"] if row["id"] != item["id"]]
    raw["items"].append(item)
    with pytest.raises(PolicyError):
        public_inspection(raw, "combat_preview", PARAMS)


def test_python_unsupported_and_inactive_never_return_partial_raw_items(engine):
    _, run = engine
    raw, _ = run()
    for change in ({"supported": False}, {"active_turn": False}):
        value = {**deepcopy(raw), **change, "items": object()}
        assert public_inspection(value, "combat_preview", PARAMS)["items"] == []


def test_registered_generated_lua_and_wait_projector_keep_exact_request_binding(engine):
    _, run = engine
    raw, _ = run()
    _, queries = registries()
    assert queries["combat_preview"] is QUERIES["combat_preview"]
    request = ReadRequest("inspection", ("combat_preview", PARAMS))
    script, projector, mode = prepare_read(request, "combat_test")
    LuaRuntime().compile(script)
    assert script == build_inspection_query("combat_test", "combat_preview", PARAMS) and mode is None
    assert projector(raw)["items"]
    raw["combat_preview"]["target_unit_id"] = 41
    assert projector(raw)["items"] == []


@pytest.mark.parametrize("params", [
    {**PARAMS, "attacker_kind": "air"}, {**PARAMS, "target_unit_id": True},
    {**PARAMS, "x": -1}, {**PARAMS, "execute_lua": "x"},
])
def test_only_fixed_typed_input_is_accepted(params):
    with pytest.raises(ValueError):
        build_inspection_query("combat_test", "combat_preview", params)
