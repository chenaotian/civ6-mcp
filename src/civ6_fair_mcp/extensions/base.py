"""Typed, authored gameplay extensions; no caller-selected engine functions."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata
from typing import Any, Callable

Schema = Any
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z", re.ASCII)


@dataclass(frozen=True)
class ActionSpec:
    fields: dict[str, Schema]
    body: Callable[[dict], str]
    description: str = ""
    turn_mode: str = "turn"


@dataclass(frozen=True)
class QuerySpec:
    fields: dict[str, Schema]
    body: Callable[[dict], str]
    description: str = ""


def validate(value: Any, schema: Schema, depth: int = 0) -> Any:
    """Copy strictly typed bounded values. Unknown fields/coercions are rejected."""
    if depth > 6:
        raise ValueError("invalid input")
    if isinstance(schema, dict):
        if type(value) is not dict or value.keys() != schema.keys():
            raise ValueError("invalid input")
        return {key: validate(value[key], field, depth + 1) for key, field in schema.items()}
    if isinstance(schema, list):
        if len(schema) != 1 or type(value) is not list or len(value) > 128:
            raise ValueError("invalid input")
        result = [validate(item, schema[0], depth + 1) for item in value]
        if result and not isinstance(result[0], (dict, list)) and len(set(result)) != len(result):
            raise ValueError("invalid input")
        return result
    if schema in {"id", "signed_id", "coord"}:
        low, high = (-1 if schema == "signed_id" else 0), (4095 if schema == "coord" else 2_147_483_647)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("invalid input")
    elif schema == "bool":
        if type(value) is not bool:
            raise ValueError("invalid input")
    elif schema == "number":
        if type(value) not in (float, int) or not math.isfinite(value) or abs(value) >= 1e12:
            raise ValueError("invalid input")
    elif schema == "text":
        if (type(value) is not str or not 1 <= len(value) <= 128
                or any(unicodedata.category(c).startswith("C") for c in value)):
            raise ValueError("invalid input")
    elif schema == "text_identifier" or schema.startswith("identifier:"):
        if type(value) is not str or not _IDENTIFIER.fullmatch(value):
            raise ValueError("invalid input")
        if schema.startswith("identifier:") and not value.startswith(tuple(schema[11:].split("|"))):
            raise ValueError("invalid input")
    elif schema.startswith("enum:"):
        if type(value) is not str or value not in schema[5:].split("|"):
            raise ValueError("invalid input")
    else:
        raise ValueError("unknown internal schema")
    return value


def lua(value: Any) -> str:
    """Serialize validated literals only; UTF-8 byte escapes are Lua-version safe."""
    if value is None:
        return "nil"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (int, float) and math.isfinite(value):
        return repr(value)
    if type(value) is str:
        return '"' + ''.join(chr(b) if 32 <= b < 127 and b not in (34, 92)
                             else "\\%03d" % b for b in value.encode("utf-8")) + '"'
    if type(value) is list:
        return "{" + ",".join(lua(item) for item in value) + "}"
    if type(value) is dict:
        return "{" + ",".join("[" + lua(key) + "]=" + lua(item) for key, item in value.items()) + "}"
    raise ValueError("invalid literal")


def own_unit(entity_id: int) -> str:
    return f'local unit = find_owned("Units", {validate(entity_id, "id")})\nif not unit then return end\n'


def own_city(entity_id: int) -> str:
    return f'local city = find_owned("Cities", {validate(entity_id, "id")})\nif not city then return end\n'


LUA_HELPERS = r'''
local function find_owned(collection, id)
    local getter = player["Get" .. collection]
    if type(getter) ~= "function" then return nil end
    local list = getter(player)
    if not list or type(list.Members) ~= "function" then return nil end
    local n = 0
    for _, candidate in list:Members() do
        n = n + 1
        if n > 4096 then return nil end
        if candidate:GetOwner() == me and candidate:GetID() == id then return candidate end
    end
end
local function visible_plot(x, y)
    if type(x) ~= "number" or type(y) ~= "number" or x < 0 or y < 0 then return nil end
    local width, height = Map.GetGridSize()
    if x >= width or y >= height or vis:IsRevealed(x, y) ~= true
        or vis:IsVisible(x, y) ~= true then return nil end
    return Map.GetPlot(x, y)
end
local function known_player(id)
    if type(id) ~= "number" or id < 0 or id > 63 then return false end
    if id == me then return true end
    local dip = player:GetDiplomacy()
    return dip and type(dip.HasMet) == "function" and dip:HasMet(id) == true
end
local function add_item(item)
    if #out.items >= 2048 then error("unavailable") end
    table.insert(out.items, item)
end
'''
