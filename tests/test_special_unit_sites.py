"""Normal specialist lenses: native lists, fog geometry, no hidden plot reads."""
from copy import deepcopy
import json

import pytest
from lupa import LuaRuntime

from civ6_fair_mcp.extensions import build_inspection_query, registries
from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import PolicyError
from civ6_fair_mcp.waiting import ReadRequest, prepare_read


PARAMS = {"unit_id": 12}


@pytest.fixture
def engine():
    vm = LuaRuntime(unpack_returned_tuples=True)
    vm.execute(r'''
rawget=nil;unpack=nil;table.unpack=nil
settings={owner=0,unit_id=12,unit_type=1,charges=1,busy=false,eligible=true}
reads={forbidden=0,archaeology=0,parks=0,geometry=0,capability=0}
function forbidden() reads.forbidden=reads.forbidden+1;error("PRIVATE_UNAUDITED") end
function members(list) local i=0;return function() i=i+1;if list[i] then return i,list[i] end end end
GameConfiguration={IsAnyMultiplayer=function() return false end,IsHotseat=function() return false end,
 IsWorldBuilderEditor=function() return false end}
Automation={IsActive=function() return false end}
Events={LoadGameViewStateDone={Add=function() end},LocalPlayerChanged={Add=function() end}}
UI={IsProcessingMessages=function() return false end,IsGameCoreBusy=function() return settings.busy end,
 SelectUnit=forbidden,SelectCity=forbidden,SetInterfaceMode=forbidden}
unit={GetOwner=function() return settings.owner end,GetID=function() assert(settings.owner==0);return settings.unit_id end,
 GetUnitType=function() assert(settings.owner==0);return settings.unit_type end,
 GetParkCharges=function() assert(settings.owner==0);return settings.charges end,
 GetArchaeology=function() assert(settings.owner==0);return archaeology end}
foreign=setmetatable({GetOwner=function() return 3 end},{__index=forbidden})
player={IsAlive=function() return true end,IsHuman=function() return true end,
 IsTurnActive=function() return true end,IsTurnActiveComplete=function() return true end,
 GetUnits=function() return {Members=function() return members({foreign,unit}) end} end}
Players=setmetatable({[0]=player},{__index=forbidden})
candidates={17.0,10.0,19.0,17.0}
archaeology={GetActivationHighlightPlots=function(self)
 assert(self==archaeology and settings.unit_type==1);reads.archaeology=reads.archaeology+1;return candidates end}
parks={GetPossibleParkTiles=function(self,id)
 assert(self==parks and id==0 and settings.unit_type==2 and settings.charges>0)
 reads.parks=reads.parks+1;return candidates end}
Game={GetLocalPlayer=function() return 0 end,GetLocalObserver=function() return 0 end,
 GetCurrentGameTurn=function() return 127 end,GetNationalParks=function() return parks end}
GameInfo={Units={[1]={ExtractsArtifacts=true,ParkCharges=0},[2]={ExtractsArtifacts=false,ParkCharges=1},
 [3]={ExtractsArtifacts=false,ParkCharges=0}},UnitOperations={
 UNITOPERATION_EXCAVATE={Hash=-42,VisibleInUI=true},
 UNITOPERATION_DESIGNATE_PARK={Hash=4294967295,VisibleInUI=true}}}
UnitManager={RequestOperation=forbidden,GetUnit=forbidden,
 CanStartOperation=function(actor,hash,plot,loose,results)
 assert(actor==unit and settings.owner==0 and plot==nil and loose==true and results==nil)
 assert(hash==(settings.unit_type==1 and -42 or 4294967295))
 reads.capability=reads.capability+1;return settings.eligible end}
-- 10 visible, 17 explored fog, 19 unexplored. Plot objects expose geometry only.
revealed={[10]=true,[17]=true,[19]=false}
vis={IsRevealed=function(self,x,y) return revealed[y*8+x]==true end,
 IsVisible=function(self,x,y) return y*8+x==10 end}
PlayersVisibility={[0]=vis}
Map=setmetatable({GetGridSize=function() return 8.0,6.0 end,
 GetPlotByIndex=function(index)
 assert(index>=0 and index<48 and index%1==0);reads.geometry=reads.geometry+1
 return setmetatable({GetX=function() return (index%8)+0.0 end,
 GetY=function() return math.floor(index/8)+0.0 end},{__index=forbidden})
 end},{__index=forbidden})
''')

    def run(params=None):
        params = PARAMS if params is None else params
        output = []
        vm.globals().print = output.append
        vm.execute(build_inspection_query("special_unit_sites_test", "special_unit_sites", params))
        raw = json.loads(next(line.removeprefix("CIV6FAIR_JSON:") for line in output
                              if line.startswith("CIV6FAIR_JSON:")))
        assert raw["ok"] is True, raw
        public = public_inspection(raw, "special_unit_sites", params)
        assert vm.globals().reads.forbidden == 0
        return raw, public
    return vm, run


def sites(public):
    values = {row["id"]: row["value"] for row in public["items"]}
    return [(values[f"site:{i}:x"], values[f"site:{i}:y"], values[f"site:{i}:purpose"])
            for i in range(len(values) // 3)]


@pytest.mark.parametrize("kind,purpose", [(1, "excavate"), (2, "national_park")])
def test_stock_highlights_keep_visible_and_revealed_fog_but_not_unexplored(engine, kind, purpose):
    vm, run = engine
    vm.globals().settings.unit_type = kind
    raw, result = run()
    assert result["supported"] is True
    assert sites(result) == [(2, 1, purpose), (1, 2, purpose)]
    assert vm.globals().reads.geometry == 3  # Duplicate native index is deduplicated.
    assert vm.globals().reads.archaeology == (kind == 1)
    assert vm.globals().reads.parks == (kind == 2)
    assert all(type(row["value"]) is int for row in result["items"] if not row["id"].endswith("purpose"))
    assert all(set(row) == {"id", "value"} for row in result["items"])
    assert raw["special_unit_sites"]["unit_id"] == 12
    assert not any("action" in row for row in result["items"])


def test_selection_not_changed_and_current_tile_operation_permission_is_not_inferred(engine):
    vm, run = engine
    # There is deliberately no unit position getter or selected-unit API. Only
    # the source list is offered; no current-site real operation check is made.
    _, result = run()
    assert result["items"] and vm.globals().reads.capability == 2


@pytest.mark.parametrize("change", [
    "settings.owner=1;unit.GetUnitType=forbidden;unit.GetArchaeology=forbidden",
    "settings.unit_id=13;unit.GetUnitType=forbidden;unit.GetArchaeology=forbidden",
])
def test_foreign_or_wrong_unit_does_not_read_specialist_or_map(engine, change):
    vm, run = engine
    vm.execute(change)
    _, result = run()
    assert result["supported"] is False and result["items"] == []
    assert vm.globals().reads.geometry == vm.globals().reads.capability == 0


@pytest.mark.parametrize("change", ["settings.unit_type=3", "settings.eligible=false",
                                         "settings.unit_type=2;settings.charges=0"])
def test_non_specialist_ineligible_or_exhausted_has_no_sites(engine, change):
    vm, run = engine
    vm.execute(change)
    _, result = run()
    assert result["supported"] is True and result["items"] == []
    assert vm.globals().reads.geometry == vm.globals().reads.archaeology == vm.globals().reads.parks == 0


@pytest.mark.parametrize("change", [
    "UI.IsGameCoreBusy=nil", "settings.busy=true", "settings.busy=0", "settings.eligible=1",
    "unit.GetUnitType=nil", "GameInfo.Units=nil", "GameInfo.UnitOperations=nil",
    "GameInfo.UnitOperations.UNITOPERATION_EXCAVATE.VisibleInUI=1",
    "GameInfo.UnitOperations.UNITOPERATION_EXCAVATE.Hash=nil",
    "UnitManager.CanStartOperation=nil", "unit.GetArchaeology=nil", "archaeology.GetActivationHighlightPlots=nil",
    "archaeology.GetActivationHighlightPlots=function() error('PRIVATE') end",
    "settings.unit_type=2;unit.GetParkCharges=nil", "settings.unit_type=2;settings.charges=0/0",
    "settings.unit_type=2;settings.charges=-1", "settings.unit_type=2;settings.charges=1.5",
    "settings.unit_type=2;Game.GetNationalParks=nil", "settings.unit_type=2;parks.GetPossibleParkTiles=nil",
    "Map.GetGridSize=nil", "Map.GetPlotByIndex=nil",
    "Map.GetGridSize=function() return 0,6 end", "Map.GetGridSize=function() return 8,4097 end",
    "Map.GetPlotByIndex=function() return nil end", "Map.GetPlotByIndex=function() return {} end",
])
def test_missing_invalid_or_throwing_capabilities_fail_closed(engine, change):
    vm, run = engine
    vm.execute("setmetatable(Map,nil);" + change)
    _, result = run()
    assert result["supported"] is False and result["items"] == []


@pytest.mark.parametrize("candidate", ["nil", "false", "7", "{10,48}", "{10,-1}",
                                        "{10,'17'}", "{10,17.5}", "{10,0/0}"])
def test_malformed_native_list_discards_partial_sites(engine, candidate):
    vm, run = engine
    vm.execute("candidates=" + candidate)
    _, result = run()
    assert result["supported"] is False and result["items"] == []


def test_only_native_candidates_are_used_even_if_another_tile_is_revealed(engine):
    vm, run = engine
    vm.execute("revealed[25]=true;candidates={17}")
    _, result = run()
    assert sites(result) == [(1, 2, "excavate")]
    assert vm.globals().reads.geometry == 1


def test_empty_native_list_is_supported_without_map_contents(engine):
    vm, run = engine
    vm.execute("candidates={}")
    _, result = run()
    assert result["supported"] is True and result["items"] == []


def test_native_zero_based_iterator_keys_are_not_used_as_indices_or_ordinals(engine):
    vm, run = engine
    vm.execute("local original=ipairs;ipairs=function(t) if t==candidates then local n=0;return function() n=n+1;if t[n] then return (n-1)+0.0,t[n] end end end;return original(t) end")
    _, result = run()
    assert sites(result) == [(2, 1, "excavate"), (1, 2, "excavate")]


@pytest.mark.parametrize("mutation", ["settings.busy=true", "settings.owner=1", "settings.unit_id=13",
                                         "settings.unit_type=3", "revealed[10]=false", "settings.eligible=false"])
def test_actor_or_perception_change_discards_whole_snapshot(engine, mutation):
    vm, run = engine
    vm.execute("local old=Map.GetPlotByIndex;Map.GetPlotByIndex=function(index) local p=old(index);if index==19 then " + mutation + " end;return p end")
    _, result = run()
    assert result["supported"] is False and result["items"] == []


def test_exhausted_park_charges_after_candidate_read_discards_snapshot(engine):
    vm, run = engine
    vm.execute("settings.unit_type=2;local old=parks.GetPossibleParkTiles;parks.GetPossibleParkTiles=function(self,id) local v=old(self,id);settings.charges=0;return v end")
    _, result = run()
    assert result["supported"] is False and result["items"] == []


def test_too_many_revealed_sites_do_not_emit_partial_list(engine):
    vm, run = engine
    vm.execute('''Map.GetGridSize=function() return 100,100 end
candidates={};for i=0,512 do candidates[#candidates+1]=i end
vis.IsRevealed=function() return true end
Map.GetPlotByIndex=function(i) return {GetX=function() return i%100 end,GetY=function() return math.floor(i/100) end} end''')
    _, result = run()
    assert result["supported"] is False and result["items"] == []


@pytest.mark.parametrize("key,value", [("source", "raw_map"), ("owner_id", 2), ("owner_id", 0.0),
                                         ("unit_id", 13), ("unit_id", 12.0), ("eligible", 1),
                                         ("purpose", "hidden_resource"), ("purpose", None)])
def test_python_proof_binds_exact_actor_and_fixed_purpose_before_content(engine, key, value):
    _, run = engine
    raw, _ = run()
    raw["special_unit_sites"][key] = value
    raw["items"] = [{"secret": object()}]
    assert public_inspection(raw, "special_unit_sites", PARAMS)["items"] == []


@pytest.mark.parametrize("params", [None, {}, {"unit_id": 13}, {"unit_id": 12.0}, {"unit_id": True}])
def test_python_requires_original_validated_request(engine, params):
    _, run = engine
    raw, _ = run()
    assert public_inspection(raw, "special_unit_sites", params)["items"] == []


@pytest.mark.parametrize("proof", [{"revealed": False, "highlighted": True},
                                      {"revealed": True, "highlighted": False},
                                      {"revealed": 1, "highlighted": True}])
def test_python_hidden_or_non_lens_row_is_dropped_without_validating_data(engine, proof):
    _, run = engine
    raw, _ = run()
    raw["items"] = [{**proof, "x": object(), "y": "PRIVATE"}]
    assert public_inspection(raw, "special_unit_sites", PARAMS)["items"] == []


@pytest.mark.parametrize("key,value", [("x", 1.0), ("x", True), ("x", -1), ("y", 4096)])
def test_python_invalid_public_coordinates_are_rejected(engine, key, value):
    _, run = engine
    raw, _ = run()
    raw["items"][0][key] = value
    with pytest.raises(PolicyError):
        public_inspection(raw, "special_unit_sites", PARAMS)


def test_projection_never_copies_native_extras_or_actions(engine):
    _, run = engine
    raw, expected = run()
    raw["items"][0].update(name="PRIVATE", resource="SECRET", action={"type": "end_turn"})
    assert public_inspection(raw, "special_unit_sites", PARAMS) == expected
    raw["supported"] = False
    assert public_inspection(raw, "special_unit_sites", PARAMS)["items"] == []


def test_waiting_projection_retains_original_unit_binding(engine):
    _, run = engine
    raw, expected = run()
    script, project, mode = prepare_read(ReadRequest("inspection", ("special_unit_sites", PARAMS)), "site_wait_test")
    LuaRuntime().compile(script)
    assert mode is None and project(raw) == expected
    changed = deepcopy(raw)
    changed["special_unit_sites"]["unit_id"] = 13
    assert project(changed)["items"] == []


def test_registry_read_only_exact_fields_and_no_arbitrary_player_or_getter():
    actions, queries = registries()
    assert "special_unit_sites" not in actions
    assert queries["special_unit_sites"].fields == {"unit_id": "id"}
    for params in ({}, {"unit_id": True}, {"unit_id": 12, "player_id": 2},
                   {"unit_id": 12, "getter": "GetActivationHighlightPlots"}):
        with pytest.raises(ValueError):
            build_inspection_query("site_bad_input", "special_unit_sites", params)


def details(vm):
    output = []
    vm.globals().print = output.append
    vm.execute(build_inspection_query("park_charges_test", "unit_details", PARAMS))
    raw = json.loads(next(line.removeprefix("CIV6FAIR_JSON:") for line in output
                          if line.startswith("CIV6FAIR_JSON:")))
    assert raw["ok"] is True, raw
    public = public_inspection(raw, "unit_details")
    assert vm.globals().reads.forbidden == 0
    return {row["id"]: row["value"] for row in public["items"] if "value" in row}


@pytest.mark.parametrize("charges", [0.0, 1.0, 2])
def test_own_park_charge_stat_matches_stock_display_including_zero(engine, charges):
    vm, _ = engine
    vm.globals().settings.unit_type = 2
    vm.globals().settings.charges = charges
    result = details(vm)
    assert result["park_charges"] == charges and type(result["park_charges"]) is int


@pytest.mark.parametrize("change", [
    "settings.unit_type=1;unit.GetParkCharges=forbidden",
    "settings.owner=1;unit.GetUnitType=forbidden;unit.GetParkCharges=forbidden",
    "unit.GetParkCharges=nil", "unit.GetParkCharges=function() error('PRIVATE') end",
    "settings.charges=nil", "settings.charges=true", "settings.charges='1'",
    "settings.charges=-1", "settings.charges=1.5", "settings.charges=math.huge", "settings.charges=0/0",
])
def test_non_park_or_unknown_charge_stat_is_omitted_not_zero(engine, change):
    vm, _ = engine
    vm.execute("settings.unit_type=2;" + change)
    assert "park_charges" not in details(vm)


def specialist(vm, kind):
    vm.execute('''
reads.gp=0;reads.rock=0
settings.gp_id=7;settings.gp_charges=2;settings.gp_flag=true
gp={IsGreatPerson=function() return true end,GetIndividual=function() return settings.gp_id end,
 GetActionCharges=function() return settings.gp_charges end,
 GetActivationHighlightPlots=function() reads.gp=reads.gp+1;return candidates end,
 GetAreaHighlightPlots=forbidden}
band={GetActivationHighlightPlots=function() reads.rock=reads.rock+1;return candidates end}
unit.GetGreatPerson=function() return gp end;unit.GetRockBand=function() return band end
GameInfo.GreatPersonIndividuals={[7]={ActionEffectTileHighlighting=true}}
GameInfo.UnitCommands={UNITCOMMAND_ACTIVATE_GREAT_PERSON={Hash=55,VisibleInUI=true}}
GameInfo.UnitOperations.UNITOPERATION_FOUND_RELIGION={Hash=56,VisibleInUI=true}
GameInfo.UnitOperations.UNITOPERATION_TOURISM_BOMB={Hash=57,VisibleInUI=true}
UnitManager.CanStartCommand=function(actor,hash,loose)
 assert(actor==unit and hash==55 and loose==true);return settings.eligible end
local old=UnitManager.CanStartOperation
UnitManager.CanStartOperation=function(actor,hash,plot,loose,results)
 if hash==56 or hash==57 then assert(actor==unit and plot==nil and loose==true and results==nil);return settings.eligible end
 return old(actor,hash,plot,loose,results)
end
''')
    if kind == "great_person":
        vm.execute("GameInfo.Units[1].GreatPersonClass='GREAT_PERSON_CLASS_SCIENTIST'")
    elif kind == "prophet":
        vm.execute("GameInfo.Units[1].GreatPersonClass='GREAT_PERSON_CLASS_PROPHET'")
    else:
        vm.execute("GameInfo.Units[1].ExtractsArtifacts=false;GameInfo.Units[1].UnitType='UNIT_ROCK_BAND'")


@pytest.mark.parametrize("kind,purpose", [("great_person", "great_person"), ("prophet", "great_person"), ("rock", "rock_concert")])
def test_gp_and_rock_band_use_exact_native_activation_lens_not_passive_area_or_class_mapping(engine, kind, purpose):
    vm, run = engine
    specialist(vm, kind)
    _, result = run()
    assert sites(result) == [(2, 1, purpose), (1, 2, purpose)]
    assert vm.globals().reads.archaeology == vm.globals().reads.parks == 0
    assert vm.globals().reads.gp == (kind != "rock")
    assert vm.globals().reads.rock == (kind == "rock")


@pytest.mark.parametrize("change", [
    "settings.gp_charges=0", "GameInfo.GreatPersonIndividuals[7].ActionEffectTileHighlighting=false",
    "GameInfo.GreatPersonIndividuals[7].ActionEffectTileHighlighting=nil", "settings.eligible=false",
])
def test_gp_without_visible_activation_highlight_or_available_charge_is_empty(engine, change):
    vm, run = engine
    specialist(vm, "great_person")
    vm.execute(change)
    _, result = run()
    assert result["supported"] and result["items"] == []
    assert vm.globals().reads.gp == 0


@pytest.mark.parametrize("change", [
    "unit.GetGreatPerson=nil", "gp.IsGreatPerson=nil", "gp.IsGreatPerson=function() return false end",
    "gp.GetIndividual=nil", "settings.gp_id=8", "gp.GetActionCharges=nil", "settings.gp_charges=-1",
    "gp.GetActivationHighlightPlots=nil", "UnitManager.CanStartCommand=nil",
])
def test_gp_missing_exact_capability_is_unsupported_not_guessed(engine, change):
    vm, run = engine
    specialist(vm, "great_person")
    vm.execute(change)
    _, result = run()
    assert not result["supported"] and result["items"] == []


def test_gp_individual_change_during_read_discards_snapshot(engine):
    vm, run = engine
    specialist(vm, "great_person")
    vm.execute("gp.GetActivationHighlightPlots=function() settings.gp_id=8;return candidates end")
    _, result = run()
    assert not result["supported"] and result["items"] == []


@pytest.mark.parametrize("change", ["unit.GetRockBand=nil", "band.GetActivationHighlightPlots=nil"])
def test_rock_band_missing_lens_is_unsupported(engine, change):
    vm, run = engine
    specialist(vm, "rock")
    vm.execute(change)
    _, result = run()
    assert not result["supported"] and result["items"] == []
