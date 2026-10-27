"""One read-only movement diagnosis; prints only fixed stages/codes/Lua types.

Usage: python scripts/live_movement_diagnostic.py UNIT_ID X Y
The live owner must run this while it alone holds the FireTuner connection.
No action, retry, path dump, engine error text or observation token is emitted.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import secrets

from civ6_fair_mcp.extensions.base import LUA_HELPERS, validate
from civ6_fair_mcp.extensions.movement import QUERIES, unit_move_preview
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import parse_response
from civ6_fair_mcp.transport import FireTunerTransport


_LUA_TYPES = frozenset({"nil", "boolean", "number", "string", "table", "function", "userdata", "thread"})
_CODES = frozenset({"early_exit", "collect_error", "outer_error", "unavailable", "supported"})
_STAGES = frozenset({"owned_unit", "api_check", "busy", "unit_definition", "grid",
    "actor_coordinate", "visibility", "plot_objects", "plot_indices", "path_call", "path_structure",
    "path_visibility", "portals", "endpoints", "first_step", "turn_estimate", "complete"})
_TYPE_FIELDS = frozenset({"busy", "unit_type", "definition", "ignore_moves", "grid_width", "grid_height",
    "actor_x", "actor_y", "origin", "target", "start_id", "target_id", "path", "plots",
    "portal_array", "portal_key", "portal_value", "first_plot", "first_x", "first_y", "turns", "collect_result",
    "get_path_api", "plot_api", "plot_index_api", "grid_api", "distance_api", "busy_api", "visible_api", "revealed_api",
    "rawget_api", "pairs_api", "next_api", "floor_api"})


def _replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("authored diagnostic source changed")
    return source.replace(old, new, 1)


def build_body(params: dict) -> tuple[str, frozenset[str]]:
    """Instrument the audited body; never evaluate caller-provided Lua or paths."""
    params = validate(params, QUERIES["unit_move_preview"].fields)
    source = unit_move_preview(params)
    stages = set(_STAGES)
    lines = []
    # Line numbers refer to the generated audited body, not an engine error.
    for number, line in enumerate(source.splitlines(), 1):
        if "return nil" in line:
            stage = f"nil_{number}"
            stages.add(stage)
            line = line.replace("return nil", f'out.diagnostic_stage="{stage}"; return nil')
        lines.append(line)
    source = "\n".join(lines)
    before = {
        "local function collect()": "api_check",
        "local busy=UI.IsGameCoreBusy()": "busy",
        "local unit_type=unit:GetUnitType()": "unit_definition",
        "local width,height=Map.GetGridSize()": "grid",
        "local x,y=unit:GetX(),unit:GetY()": "actor_coordinate",
        "if vis:IsRevealed(x,y)~=true": "visibility",
        "local origin,target=Map.GetPlot(x,y),Map.GetPlot(": "plot_objects",
        "local start_id,target_id=origin:GetIndex(),target:GetIndex()": "plot_indices",
        "local path=UnitManager.GetMoveToPathEx(unit,target_id)": "path_call",
        "local plots=path.plots": "path_structure",
        "-- IsVisible(plotID)": "path_visibility",
        '-- Portal geometry': "portals",
        'if count==0 then return status("no_path") end': "endpoints",
        "local first=Map.GetPlotByIndex(plots[2])": "first_step",
        "local turns=path.turns": "turn_estimate",
    }
    for anchor, stage in before.items():
        # The function declaration needs its first statement inside its body.
        if anchor == "local function collect()":
            source = _replace_once(source, anchor, anchor+f'\nout.diagnostic_stage="{stage}"')
        else:
            source = _replace_once(source, anchor, f'out.diagnostic_stage="{stage}"\n'+anchor)
    source = _replace_once(source, 'out.diagnostic_stage="api_check"', '''out.diagnostic_stage="api_check"
out.diagnostic_types.get_path_api=type(UnitManager and UnitManager.GetMoveToPathEx)
out.diagnostic_types.plot_api=type(Map and Map.GetPlot)
out.diagnostic_types.plot_index_api=type(Map and Map.GetPlotByIndex)
out.diagnostic_types.grid_api=type(Map and Map.GetGridSize)
out.diagnostic_types.distance_api=type(Map and Map.GetPlotDistance)
out.diagnostic_types.busy_api=type(UI and UI.IsGameCoreBusy)
out.diagnostic_types.visible_api=type(vis and vis.IsVisible)
out.diagnostic_types.revealed_api=type(vis and vis.IsRevealed)
out.diagnostic_types.rawget_api=type(rawget)
out.diagnostic_types.pairs_api=type(pairs)
out.diagnostic_types.next_api=type(next)
out.diagnostic_types.floor_api=type(math and math.floor)''')
    after = {
        "local busy=UI.IsGameCoreBusy()": (("busy", "busy"),),
        "local unit_type=unit:GetUnitType()": (("unit_type", "unit_type"),),
        "local definition=GameInfo.Units[unit_type]": (("definition", "definition"),),
        "local ignore=definition.IgnoreMoves": (("ignore_moves", "ignore"),),
        "local width,height=Map.GetGridSize()": (("grid_width", "width"), ("grid_height", "height")),
        "local x,y=unit:GetX(),unit:GetY()": (("actor_x", "x"), ("actor_y", "y")),
        f"local origin,target=Map.GetPlot(x,y),Map.GetPlot({params['x']},{params['y']})": (("origin", "origin"), ("target", "target")),
        "local start_id,target_id=origin:GetIndex(),target:GetIndex()": (("start_id", "start_id"), ("target_id", "target_id")),
        "local path=UnitManager.GetMoveToPathEx(unit,target_id)": (("path", "path"),),
        "local plots=path.plots": (("plots", "plots"),),
        "local portals=path[name]": (("portal_array", "portals"),),
        "for index,id in pairs(portals) do": (("portal_key", "index"), ("portal_value", "id")),
        "local first=Map.GetPlotByIndex(plots[2])": (("first_plot", "first"),),
        "local nx,ny=first:GetX(),first:GetY()": (("first_x", "nx"), ("first_y", "ny")),
        "local turns=path.turns": (("turns", "turns"),),
    }
    for anchor, fields in after.items():
        source = _replace_once(source, anchor, anchor+"\n"+"\n".join(
            f'out.diagnostic_types.{key}=type({value})' for key, value in fields))
    source = _replace_once(source, "local ok,items=pcall(collect)", '''local ok,items=pcall(collect)
out.diagnostic_types.collect_result=type(items)
out.diagnostic_code=not ok and "collect_error" or type(items)~="table" and "unavailable" or "supported"
if ok and type(items)=="table" then out.diagnostic_stage="complete" end''')
    body = '''
out.items={}
out.diagnostic_stage="owned_unit"
out.diagnostic_code="early_exit"
out.diagnostic_types={}
''' + LUA_HELPERS + "\nlocal function audited_read()\n" + source + '''
end
local completed=pcall(audited_read)
if not completed then out.diagnostic_code="outer_error" end
-- Even the ordinary public preview values are excluded from diagnostics.
out.items=nil
out.supported=nil
'''
    return body, frozenset(stages)


def project_diagnostic(raw: dict, stages: frozenset[str]) -> dict:
    """Second boundary: arbitrary engine strings and unknown fields never pass."""
    stage, code, types = raw.get("diagnostic_stage"), raw.get("diagnostic_code"), raw.get("diagnostic_types")
    if (raw.get("ok") is not True or type(stage) is not str or stage not in stages
            or type(code) is not str or code not in _CODES or type(types) is not dict):
        return {"stage": "response", "code": "invalid_diagnostic", "types": {}}
    safe_types = {}
    for key in _TYPE_FIELDS:
        value = types.get(key)
        if type(value) is str and value in _LUA_TYPES:
            safe_types[key] = value
    return {"stage": stage, "code": code, "types": safe_types}


async def run(unit_id: int, x: int, y: int) -> dict:
    body, stages = build_body({"unit_id": unit_id, "x": x, "y": y})
    transport = FireTunerTransport()
    try:
        try:
            response = await transport.execute(wrap(body, secrets.token_hex(16)))
        except Exception:
            return {"stage": "transport", "code": "transport_failed", "types": {}}
        try:
            return project_diagnostic(parse_response(response), stages)
        except Exception:
            return {"stage": "response", "code": "parse_failed", "types": {}}
    finally:
        try:
            await transport.close()
        except Exception:
            pass


def _integer(text: str) -> int:
    if not re.fullmatch(r"0|[1-9][0-9]{0,9}", text, re.ASCII):
        raise argparse.ArgumentTypeError("Expected a nonnegative decimal integer.")
    return int(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("unit_id", type=_integer)
    parser.add_argument("x", type=_integer)
    parser.add_argument("y", type=_integer)
    args = parser.parse_args()
    try:
        validate(vars(args), QUERIES["unit_move_preview"].fields)
    except ValueError:
        parser.error("Unit ID or coordinates are outside the supported integer range.")
    try:
        print(json.dumps(asyncio.run(run(args.unit_id, args.x, args.y)), sort_keys=True))
    except KeyboardInterrupt:
        print(json.dumps({"stage": "transport", "code": "cancelled", "types": {}}))
