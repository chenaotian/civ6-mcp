"""The separate live diagnostic reports only the fixed query's reached stage."""
import pytest
from lupa import LuaRuntime

from scripts.live_combat_preview_check import CHECKS, build_probe, probe_body, project
from test_combat_preview import PARAMS, engine  # reuse the hostile native fixture


def run_probe(vm, params=None):
    output = vm.execute("local me=0;local out={active_turn=true};local function array(v) return v end\n"
                        + probe_body(params or PARAMS) + "\nreturn out")
    raw = {"session": "combat_probe_tests", "player_id": 0, "turn": 117,
           "active_turn": True, "supported": output["supported"],
           "probe_stage": output["probe_stage"], "probe_checks": dict(output["probe_checks"])}
    assert output["items"] is None and output["combat_preview"] is None
    return project(raw)


def test_probe_keeps_legality_and_detection_but_never_reads_strength_or_text(engine):
    vm, _ = engine
    vm.execute("mutate_result=function(r) r.ATTACKER.COMBAT_STRENGTH=nil;r.DEFENDER.STRENGTH_MODIFIER=nil end;"
               "Locale.Lookup=forbidden")
    output = run_probe(vm)
    assert output == {"ok": True, "supported": True, "stage": "ready_to_project",
                      "checks": {key: True for key in CHECKS}}
    assert vm.globals().reads.private == vm.globals().reads.hidden == 0
    assert vm.globals().reads.legal == 1 and vm.globals().reads.compatible == 2


@pytest.mark.parametrize("change,phase,simulations", [
    ("settings.at_war=false", "components_bound", 0),
    ("settings.can=false", "war_clear", 0),
    ("settings.compatible=false", "result_identity", 1),
    ("settings.visible=false", "source_resolved", 0),
    ("settings.detected=false", "visible_plot", 0),
    ("mutate_result=function(r) r.COMBAT_TYPE=CombatTypes.MELEE end", "result_structure", 1),
    ("mutate_result=function(r) r.ATTACKER.ID={type=2,player=0,id=20} end", "result_structure", 1),
    ("mutate_result=function(r) r.DEFENDER.ID={type=1,player=1,id=99} end", "result_structure", 1),
    ("mutate_result=function(r) city.GetOwner=function() return 2 end end", "post_compatible", 1),
    ("mutate_result=function(r) settings.target_x=4 end", "post_compatible", 1),
])
def test_probe_does_not_bypass_a_failing_current_gate(engine, change, phase, simulations):
    vm, _ = engine
    vm.execute(change)
    output = run_probe(vm, {**PARAMS, "attacker_kind": "city", "attacker_id": 20})
    assert output["stage"] == phase and output["supported"] is True
    assert vm.globals().reads.simulate == simulations
    assert vm.globals().reads.private == vm.globals().reads.hidden == 0
    assert set(output) == {"ok", "supported", "stage", "checks"}


def test_probe_full_script_compiles_without_any_game_connection():
    LuaRuntime().compile(build_probe(PARAMS))


def test_projector_discards_envelope_and_rejects_arbitrary_fields():
    raw = {"session": "combat_probe_tests", "player_id": 0, "turn": 117,
           "active_turn": True, "supported": False, "probe_stage": "start", "probe_checks": {},
           "items": [{"id": "SECRET", "value": 999}]}
    assert project(raw) == {"ok": True, "supported": False, "stage": "start",
                            "checks": {key: None for key in CHECKS}}
    raw["probe_checks"]["hidden_count"] = True
    with pytest.raises(ValueError):
        project(raw)
