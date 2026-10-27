"""Read-only stages of the existing fixed combat query; never submits an action.

Close the ordinary MCP client first. Use only current public actor/target IDs
and coordinates. This runs the SAME guards and simulation as combat_preview,
skips reading strengths/modifier text, and prints only fixed stage names
and component/type comparison booleans. It cannot inspect an invalid old target
or reconstruct the earlier reason for an empty preview.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets

from civ6_fair_mcp.extensions.base import validate
from civ6_fair_mcp.extensions.combat_preview import FIELDS, preview
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import envelope, parse_response
from civ6_fair_mcp.transport import FireTunerTransport


PHASES = frozenset({
    "start", "ready", "own_actor", "source_resolved", "visible_plot",
    "detected_target", "components_bound", "war_clear", "normal_action_legal",
    "simulation_entered", "simulation_returned", "result_structure",
    "result_identity", "post_compatible", "ready_to_project",
})
CHECKS = ("combat_type_matches", "attacker_matches", "defender_matches")


def probe_body(params: dict) -> str:
    params = validate(params, FIELDS)
    text = preview(params)
    # Every marker must match exactly once. A future authored query edit cannot
    # silently make this probe skip a guard or instrument a different function.
    replacements = [
        ("    local kind=request.attacker_kind", "    stage='ready'\n    local kind=request.attacker_kind"),
        ("    if not actor then return end", "    if not actor then return end\n    stage='own_actor'"),
        ("    if is_unit then need(type(combat_type)=='number') end",
         "    if is_unit then need(type(combat_type)=='number') end\n    stage='source_resolved'"),
        ("    local plot=Map.GetPlot(x,y)", "    stage='visible_plot'\n    local plot=Map.GetPlot(x,y)"),
        ("    if not target then return end", "    if not target then return end\n    stage='detected_target'"),
        ("    local diplomacy\n", "    stage='components_bound'\n    local diplomacy\n"),
        ("    need(UnitOperationTypes and UnitOperationTypes.PARAM_X~=nil and UnitOperationTypes.PARAM_Y~=nil)",
         "    stage='war_clear'\n    need(UnitOperationTypes and UnitOperationTypes.PARAM_X~=nil and UnitOperationTypes.PARAM_Y~=nil)"),
        ("    if is_unit and CombatManager.CanAttackTarget(attacker_component,target_component,combat_type)~=true then return end",
         "    stage='normal_action_legal'\n    if is_unit and CombatManager.CanAttackTarget(attacker_component,target_component,combat_type)~=true then return end"),
        ("    local result\n", "    stage='simulation_entered'\n    local result\n"),
        ("    need(type(result)=='table')", "    stage='simulation_returned'\n    need(type(result)=='table')"),
        ("    need(type(actual_type)=='number' and actual_type%1==0)",
         "    need(type(actual_type)=='number' and actual_type%1==0)\n"
         "    stage='result_structure'\n"
         "    comparisons.combat_type_matches=(is_unit and actual_type==combat_type)\n"
         "        or (not is_unit and (actual_type==CombatTypes.RANGED or actual_type==CombatTypes.BOMBARD))"),
        ("    if not same_component(attack[keys.ID],attacker_component)\n"
         "        or not same_component(defend[keys.ID],target_component) then return end",
         "    comparisons.attacker_matches=same_component(attack[keys.ID],attacker_component)\n"
         "    if not comparisons.attacker_matches then return end\n"
         "    comparisons.defender_matches=same_component(defend[keys.ID],target_component)\n"
         "    if not comparisons.defender_matches then return end\n"
         "    stage='result_identity'"),
        ("    local proof={attacker_kind=kind", "    stage='ready_to_project'\n    local proof={attacker_kind=kind"),
    ]
    for before, after in replacements:
        if text.count(before) != 1:
            raise ValueError("fixed combat query changed; probe needs review")
        text = text.replace(before, after, 1)
    # Omit only the strength/text projection, keeping the ORIGINAL final
    # readiness, visibility, detection and identity guards below it intact.
    begin = "    local items=array({})\n"
    end = "    -- Recheck current proof after the engine simulation, before publication."
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError("fixed combat query changed; probe needs review")
    prefix, remaining = text.split(begin, 1)
    _, suffix = remaining.split(end, 1)
    text = prefix + "    stage='post_compatible'\n    local items=array({})\n" + end + suffix
    return ("local stage='start';local comparisons={}\n" + text
            + "\nout.items=nil;out.combat_preview=nil;out.probe_stage=stage;out.probe_checks=comparisons\n")


def build_probe(params: dict) -> str:
    return wrap(probe_body(params), secrets.token_hex(16))


def project(raw: dict) -> dict:
    envelope(raw)
    stage, checks = raw.get("probe_stage"), raw.get("probe_checks")
    if (type(stage) is not str or stage not in PHASES or type(checks) is not dict
            or checks.keys() - set(CHECKS) or type(raw.get("supported")) is not bool
            or any(type(value) is not bool for value in checks.values())):
        raise ValueError("invalid combat stage response")
    return {"ok": True, "supported": raw["supported"], "stage": stage,
            "checks": {key: checks.get(key) for key in CHECKS}}


async def run(params: dict) -> dict:
    # Build/validate before obtaining a connection.
    script = build_probe(params)
    client = FireTunerTransport()
    try:
        return project(parse_response(await client.execute(script)))
    except Exception:
        return {"ok": False, "error": "combat_stage_unavailable"}
    finally:
        try:
            await client.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attacker-kind", choices=("unit_melee", "unit_ranged", "city", "district"), required=True)
    for field in ("attacker-id", "target-owner-id", "target-unit-id", "x", "y"):
        parser.add_argument("--" + field, type=int, required=True)
    values = vars(parser.parse_args())
    result = asyncio.run(run(values))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)
