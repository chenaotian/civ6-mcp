"""Explicitly authorized emergency Lua execution; NOT a fairness sandbox.

The user accepted the inability to automatically filter arbitrary Lua on
2026-10-27. The tool is restricted by its usage contract to unresolved normal
interface gaps. Reasons are declarations, not proof of necessity or safety.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from .lua_common import _PREFIX, wrap
from .policy import PolicyError, _unique_object, _reject_constant

MAX_CODE_BYTES = 32768
MAX_LINE_BYTES = 4096
MAX_OUTPUT_BYTES = 65536
MAX_LINES = 128
ATTEMPTED_TOOLS = frozenset({"get_game_status", "get_player_state", "get_diplomacy",
    "observe_area", "list_options", "inspect_game", "get_pending_decisions", "wait_for_change", "act"})
_CONTEXT = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}\Z", re.ASCII)


def validate_request(code: Any, reason: Any, attempted_tools: Any, context: Any) -> dict:
    if (type(code) is not str or not code.strip() or type(reason) is not str
            or not reason.strip() or len(reason) > 2000 or type(context) is not str
            or not _CONTEXT.fullmatch(context) or type(attempted_tools) is not list
            or not 1 <= len(attempted_tools) <= len(ATTEMPTED_TOOLS)
            or any(type(name) is not str or name not in ATTEMPTED_TOOLS for name in attempted_tools)
            or len(set(attempted_tools)) != len(attempted_tools)):
        raise ValueError("invalid_input")
    try:
        encoded = code.encode("utf-8")
        reason.encode("utf-8")
    except UnicodeError:
        raise ValueError("invalid_input") from None
    if (len(encoded) > MAX_CODE_BYTES or any(ord(c) < 32 and c not in "\t\r\n" for c in code)
            or any(ord(c) < 32 and c not in "\t\r\n" for c in reason)):
        raise ValueError("invalid_input")
    context = {"ingame": "InGame", "gamecore": "GameCore_Tuner"}.get(context, context)
    return {"code": code, "reason": reason.strip(), "attempted_tools": list(attempted_tools),
            "context": context, "code_sha256": hashlib.sha256(encoded).hexdigest()}


def _literal(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"'


def build_preflight(nonce: str) -> str:
    # No generic UI scan, diplomatic hook, map read, turn requirement or token.
    return wrap('''
if player:IsAlive() ~= true or type(Game.GetWinningTeam) ~= "function"
    or Game.GetWinningTeam() ~= -1 then error("unavailable") end
out.fallback_eligible = true
''', nonce, status_only=True, observation_activity=False, discover_ui=False)


def build_script(code: str, identity: tuple[str, int, int, bool]) -> str:
    session, player_id, turn, _ = identity
    # Reuse only the fixed serializer, not the normal player-observation body.
    serializer = _PREFIX[:_PREFIX.index("local success, result = pcall(function()")]
    body = r'''
local output = {phase="identity_rejected", lines=array({}), truncated=false}
local guarded = pcall(function()
    if GameConfiguration.IsAnyMultiplayer() ~= false or GameConfiguration.IsHotseat() ~= false
        or GameConfiguration.IsWorldBuilderEditor() ~= false or Automation.IsActive() ~= false then return end
    if Game.GetLocalPlayer() ~= __PLAYER__ or Game.GetLocalObserver() ~= __PLAYER__
        or Game.GetCurrentGameTurn() ~= __TURN__ or Game.GetWinningTeam() ~= -1 then return end
    local localPlayer = Players[__PLAYER__]
    if not localPlayer or localPlayer:IsAlive() ~= true or localPlayer:IsHuman() ~= true then return end
    local state = _CIV6FAIR_V1 or (ExposedMembers and ExposedMembers.Civ6FairState)
    if type(state) ~= "table" or state.session ~= __SESSION__ or state.player_id ~= __PLAYER__ then return end
    output.phase = "compiler_unavailable"
    local used = 0
    local function scalar(value)
        local kind = type(value)
        if kind == "string" then return value end
        if kind == "nil" then return "nil" end
        if kind == "boolean" then return value and "true" or "false" end
        if kind == "number" and value == value and value ~= math.huge and value ~= -math.huge then return tostring(value) end
        return "[" .. kind .. "]"
    end
    local function capture(...)
        local count, pieces, size = select("#", ...), {}, 0
        if count > 64 then output.truncated=true; return end
        for i=1,count do
            local value = scalar(select(i, ...))
            size = size + #value + (i > 1 and 1 or 0)
            if size > 4096 then output.truncated=true; return end
            pieces[i] = value
        end
        local text = table.concat(pieces, "\t"):gsub("\r\n", "\n"):gsub("\r", "\n")
        for line in (text .. "\n"):gmatch("(.-)\n") do
            if #output.lines >= 128 or used + #line > 65536 then output.truncated=true; return end
            output.lines[#output.lines+1] = line
            used = used + #line
        end
    end
    local function diagnostic(value)
        local text = scalar(value)
        if #text <= 4096 then output.error_text=text else output.error_text="[diagnostic omitted: too long]"; output.truncated=true end
    end
    -- Capture only the script's lexical print. Do not replace global print or
    -- traverse returned tables/userdata. This deliberately is NOT a sandbox.
    local source = "local print = ...;\n" .. __CODE__
    local loader, compileError
    if type(loadstring) == "function" then
        loader, compileError = loadstring(source, "civ6-fallback")
    elseif type(load) == "function" then
        loader, compileError = load(source, "civ6-fallback", "t", _ENV)
    else return end
    if not loader then output.phase="compile_error"; diagnostic(compileError); return end
    output.phase = "runtime_error"
    local succeeded, value = pcall(loader, capture)
    if not succeeded then diagnostic(value); return end
    output.phase = "completed"
    local kind = type(value)
    output.return_type = kind
    if kind == "string" and #value <= 4096 then output.return_value=value
    elseif kind == "boolean" then output.return_value=value
    elseif kind == "number" and value == value and value ~= math.huge and value ~= -math.huge then output.return_value=value
    elseif kind ~= "nil" then output.return_omitted=true end
end)
-- Wrapper failures are opaque: a runtime error can follow an earlier side effect.
if not guarded then output = {phase="outcome_unknown", lines=array({}), truncated=false} end
local encoded, payload = pcall(encode, output, {}, 0)
if not encoded then payload='{"phase":"outcome_unknown","lines":[],"truncated":false}' end
print('CIV6FAIR_JSON:' .. payload)
print('---END---')
end
'''
    # Substitution occurs once, before inserting arbitrary source text as data.
    # A user's source cannot be interpreted as placeholders or wrapper syntax.
    body = body.replace("__PLAYER__", str(player_id)).replace("__TURN__", str(turn))
    body = body.replace("__SESSION__", _literal(session)).replace("__CODE__", _literal(code))
    return serializer + body


def parse_result(text: str) -> dict:
    try:
        valid_text = type(text) is str and len(text.encode("utf-8")) <= 512 * 1024
    except UnicodeError:
        valid_text = False
    if not valid_text:
        raise PolicyError("invalid_response")
    lines = [line[len("CIV6FAIR_JSON:"):] for line in text.split("\n") if line.startswith("CIV6FAIR_JSON:")]
    if len(lines) != 1:
        raise PolicyError("invalid_response")
    try:
        raw = json.loads(lines[0], parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise PolicyError("invalid_response") from None
    if (type(raw) is not dict or type(raw.get("phase")) is not str or raw["phase"] not in {
            "identity_rejected", "compiler_unavailable", "compile_error", "runtime_error", "completed", "outcome_unknown"}
            or type(raw.get("truncated")) is not bool or type(raw.get("lines")) is not list
            or len(raw["lines"]) > MAX_LINES):
        raise PolicyError("invalid_response")
    def bounded(value):
        try:
            valid = type(value) is str and len(value.encode("utf-8")) <= MAX_LINE_BYTES
        except UnicodeError:
            valid = False
        if not valid:
            raise PolicyError("invalid_response")
        return value
    output = {"phase": raw["phase"], "lines": [bounded(line) for line in raw["lines"]],
              "truncated": raw["truncated"]}
    if sum(len(line.encode("utf-8")) for line in output["lines"]) > MAX_OUTPUT_BYTES:
        raise PolicyError("invalid_response")
    if "error_text" in raw:
        output["error_text"] = bounded(raw["error_text"])
    if "return_type" in raw:
        if type(raw["return_type"]) is not str or raw["return_type"] not in {"nil", "string", "boolean", "number", "table", "userdata", "function", "thread"}:
            raise PolicyError("invalid_response")
        output["return_type"] = raw["return_type"]
    if "return_value" in raw:
        value = raw["return_value"]
        if type(value) is str: value = bounded(value)
        elif type(value) is bool: pass
        elif type(value) in (int, float):
            try:
                if not math.isfinite(value): raise PolicyError("invalid_response")
            except OverflowError:
                raise PolicyError("invalid_response") from None
        else: raise PolicyError("invalid_response")
        expected_type = {str: "string", bool: "boolean", int: "number", float: "number"}[type(value)]
        if raw.get("return_type") != expected_type:
            raise PolicyError("invalid_response")
        output["return_value"] = value
    if "return_omitted" in raw:
        if type(raw["return_omitted"]) is not bool: raise PolicyError("invalid_response")
        output["return_omitted"] = raw["return_omitted"]
    return output
