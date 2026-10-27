"""Independent output projection. Unknown fields and uncertain facts never pass through.

The Lua adapter establishes visibility before reading; this layer prevents accidental
future adapter additions from silently expanding the information exposed to agents.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

MAX_RESPONSE_BYTES = 2_000_000
IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z", re.ASCII)


class PolicyError(ValueError):
    """Fail closed. Never include the input or engine exception in this error."""


def integer(value: Any, low: int = 0, high: int = 2_147_483_647) -> int:
    if type(value) is not int or not low <= value <= high:
        raise PolicyError("invalid_input")
    return value


def _reject_constant(_: str) -> None:
    raise PolicyError("invalid_response")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError("invalid_response")
        result[key] = value
    return result


def parse_response(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise PolicyError("invalid_response")
    lines = [line[len("CIV6FAIR_JSON:"):] for line in text.split("\n")
             if line.startswith("CIV6FAIR_JSON:")]
    if len(lines) != 1:
        raise PolicyError("invalid_response")
    try:
        data = json.loads(lines[0], parse_constant=_reject_constant,
                          object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise PolicyError("invalid_response") from None
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise PolicyError("unavailable")
    envelope(data)
    return data


def envelope(raw: dict[str, Any]) -> tuple[str, int, int, bool]:
    session = raw.get("session")
    if not isinstance(session, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{16,128}", session):
        raise PolicyError("invalid_response")
    player_id = integer(raw.get("player_id"), 0, 63)
    turn = integer(raw.get("turn"), 0, 1_000_000)
    active = raw.get("active_turn")
    if type(active) is not bool:
        raise PolicyError("invalid_response")
    return session, player_id, turn, active


def _project(raw: Any, fields: dict[str, str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise PolicyError("invalid_response")
    out: dict[str, Any] = {}
    for key, kind in fields.items():
        if key not in raw:
            continue
        value = raw[key]
        if kind == "number":
            valid = type(value) in (int, float) and math.isfinite(value) and abs(value) < 1e15
        elif kind == "int":
            valid = type(value) is int and 0 <= value <= 2_147_483_647
        elif kind == "bool":
            valid = type(value) is bool
        elif kind == "identifier":
            valid = isinstance(value, str) and bool(IDENTIFIER.fullmatch(value))
        elif kind == "district":
            valid = type(value) is str and (value == "NONE" or (
                value.startswith("DISTRICT_") and len(value) > len("DISTRICT_")
                and bool(IDENTIFIER.fullmatch(value))))
        elif kind == "random_event":
            valid = type(value) is str and (value == "NONE" or (
                value.startswith("RANDOM_EVENT_") and len(value) > len("RANDOM_EVENT_")
                and bool(IDENTIFIER.fullmatch(value))))
        elif kind == "turn_count":
            valid = type(value) is int and 0 <= value <= 1_000_000
        elif kind == "movement_cost":
            valid = type(value) in (int, float) and math.isfinite(value) and 0 < value <= 1_000_000
        elif kind == "route_cost":
            valid = type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1_000_000
        elif kind == "planning_number":
            valid = type(value) in (int, float) and math.isfinite(value) and -1_000_000 <= value <= 1_000_000
        elif kind == "route":
            valid = type(value) is str and (value == "NONE" or (
                value.startswith("ROUTE_") and len(value) > len("ROUTE_")
                and bool(IDENTIFIER.fullmatch(value))))
        elif kind == "ui_text":
            valid = type(value) is str and len(value) <= 1024 and all(ord(c) >= 32 for c in value)
        else:
            valid = isinstance(value, str) and len(value) <= 256 and all(
                ord(c) >= 32 for c in value)
        if not valid:
            raise PolicyError("invalid_response")
        out[key] = value
    return out


PLAYER_FIELDS = {key: "number" for key in (
    "gold", "gold_per_turn", "faith", "faith_per_turn", "science_per_turn", "culture_per_turn")}
PLAYER_FIELDS.update(research="identifier", civic="identifier")
ENTITY_FIELDS = {key: "int" for key in ("owner_id", "id", "x", "y")}
UNIT_FIELDS = {**ENTITY_FIELDS, "type": "identifier", "name": "string",
               **{key: "number" for key in ("moves", "max_moves", "damage", "max_damage")},
               "build_charges": "int"}
CITY_FIELDS = {**ENTITY_FIELDS, "name": "string", "population": "int",
               "production": "identifier", "production_turns": "int", "production_indefinite": "bool",
               **{key: "number" for key in ("food", "production_per_turn", "gold_per_turn",
                 "science_per_turn", "culture_per_turn", "faith_per_turn")}}
TILE_FIELDS = {"terrain": "identifier", "feature": "identifier", "district": "district",
               "impassable": "bool", "lake": "bool", "route_pillaged": "bool",
               "movement_cost": "movement_cost", "route_movement_cost": "route_cost",
               "defense_modifier": "planning_number", "appeal": "planning_number", "route": "route",
               "improvement": "identifier", "improvement_pillaged": "bool",
               "hills": "bool", "river": "bool", "water": "bool",
               "is_nw_of_cliff": "bool", "is_w_of_cliff": "bool", "is_ne_of_cliff": "bool",
               "storm_type": "random_event", "storm_name": "string",
               "drought_type": "random_event", "drought_name": "string", "drought_turns": "turn_count"}
VISIBLE_UNIT_FIELDS = {**ENTITY_FIELDS, "type": "identifier", "name": "string",
    **{key: "number" for key in ("damage", "max_damage", "combat", "ranged_combat")}}
VISIBLE_CITY_FIELDS = {**ENTITY_FIELDS, "name": "string", "population": "int",
    "religion": "identifier", "production": "identifier", "production_turns": "int",
    **{key: "number" for key in ("damage", "max_damage", "wall_damage", "wall_max_damage")}}
DIPLOMACY_FIELDS = {"id": "int", "civilization": "identifier", "leader": "identifier",
    "name": "string", "alive": "bool", "at_war": "bool",
    **{key: "number" for key in ("gold", "gold_per_turn", "science_per_turn",
       "culture_per_turn", "military_strength", "score")}}
VICTORY_FIELDS = {
    **{key: "bool" for key in ("science_satellite_completed", "science_moon_completed",
       "science_mars_completed", "science_exoplanet_completed")},
    **{key: "int" for key in ("science_techs_researched", "culture_domestic_tourists",
       "culture_visiting_tourists", "diplomatic_points", "diplomatic_points_required",
       "religion_cities_following")},
    **{key: "number" for key in ("science_light_years", "science_light_years_per_turn",
       "religion_faith_per_turn")},
}


def _array(value: Any, limit: int) -> list:
    # Lua empty arrays must be tagged in the adapter; do not accept arbitrary tables.
    if not isinstance(value, list) or len(value) > limit:
        raise PolicyError("invalid_response")
    return value


def _own_entities(raw: Any, player_id: int, fields: dict[str, str], limit: int) -> list:
    result = []
    for item in _array(raw, limit):
        if not isinstance(item, dict):
            raise PolicyError("invalid_response")
        # Never inspect other fields on foreign entities, even malformed ones.
        if type(item.get("owner_id")) is not int or item["owner_id"] != player_id:
            continue
        projected = _project(item, fields)
        if not set(ENTITY_FIELDS) <= projected.keys():
            raise PolicyError("invalid_response")
        result.append(projected)
    return result


def _identifier_list(raw: Any, limit: int = 512) -> list[str]:
    result = []
    for item in _array(raw, limit):
        if not isinstance(item, str) or not IDENTIFIER.fullmatch(item):
            raise PolicyError("invalid_response")
        result.append(item)
    return result


def _visible_entity(item: Any, proof: str, fields: dict[str, str], x: int, y: int) -> dict | None:
    if not isinstance(item, dict):
        raise PolicyError("invalid_response")
    # Hidden/undetected entities must not influence output or validation of details.
    if item.get(proof) is not True:
        return None
    entity = _project(item, fields)
    if not set(ENTITY_FIELDS) <= entity.keys() or (entity["x"], entity["y"]) != (x, y):
        raise PolicyError("invalid_response")
    integer(entity["owner_id"], 0, 63)
    return entity


def public_player(raw: dict[str, Any]) -> dict[str, Any]:
    _, player_id, turn, active = envelope(raw)
    out = {"ok": True, "player_id": player_id, "turn": turn, "active_turn": active,
           "player": _project(raw.get("player", {}), PLAYER_FIELDS),
           "units": _own_entities(raw.get("units", []), player_id, UNIT_FIELDS, 4096),
           "cities": _own_entities(raw.get("cities", []), player_id, CITY_FIELDS, 1024)}
    for city in out["cities"]:
        if city.get("production_indefinite") is True and "production_turns" in city:
            raise PolicyError("invalid_response")
    if raw.get("first_ready_unit_checked") is True:
        ready_id = raw.get("first_ready_unit_id")
        if ready_id is None:
            out["first_ready_unit_id"] = None
        elif type(ready_id) is int and any(unit["id"] == ready_id for unit in out["units"]):
            out["first_ready_unit_id"] = ready_id
        # A stale, foreign, malformed, or off-map candidate never becomes a new
        # entity lookup or a leaked ID. It is simply an unavailable optional fact.
    return out


def public_map(raw: dict[str, Any]) -> dict[str, Any]:
    _, player_id, turn, active = envelope(raw)
    tiles = []
    seen = set()
    for tile in _array(raw.get("tiles", []), 289):
        if not isinstance(tile, dict):
            raise PolicyError("invalid_response")
        x, y = integer(tile.get("x"), 0, 65535), integer(tile.get("y"), 0, 65535)
        if (x, y) in seen:
            raise PolicyError("invalid_response")
        seen.add((x, y))
        revealed, visible = tile.get("revealed"), tile.get("visible")
        if type(revealed) is not bool or type(visible) is not bool or (visible and not revealed):
            raise PolicyError("invalid_response")
        out = {"x": x, "y": y, "revealed": revealed, "visible": visible}
        if revealed and visible:
            fields = TILE_FIELDS.copy()
            if tile.get("impassable") is not False:
                fields.pop("movement_cost", None)
            if tile.get("route", "NONE") == "NONE":
                fields.pop("route_pillaged", None)
                fields.pop("route_movement_cost", None)
            out.update(_project(tile, fields))
            for hazard in ("storm", "drought"):
                if out.get(f"{hazard}_type", "NONE") == "NONE":
                    out.pop(f"{hazard}_name", None)
                    if hazard == "drought":
                        out.pop("drought_turns", None)
            if "owner_id" in tile:
                out["owner_id"] = integer(tile["owner_id"], -1, 63)
            if tile.get("resource_visible") is True and "resource" in tile:
                out.update(_project(tile, {"resource": "identifier"}))
            # Unit detection is a separate proof, even on visible terrain.
            if "units" in tile:
                units = []
                for item in _array(tile["units"], 256):
                    entity = _visible_entity(item, "detected", VISIBLE_UNIT_FIELDS, x, y)
                    if entity is not None:
                        units.append(entity)
                out["units"] = units
            if tile.get("city") is not None:
                city = _visible_entity(tile["city"], "visible", VISIBLE_CITY_FIELDS, x, y)
                if city is not None:
                    for field in ("districts", "buildings"):
                        if field in tile["city"]:
                            city[field] = _identifier_list(tile["city"][field])
                    out["city"] = city
        tiles.append(out)
    return {"ok": True, "player_id": player_id, "turn": turn,
            "active_turn": active, "tiles": tiles}


def public_diplomacy(raw: dict[str, Any]) -> dict[str, Any]:
    _, player_id, turn, active = envelope(raw)
    civilization_count = integer(raw.get("civilization_count"), 1, 64)
    civilizations = []
    seen = set()
    for item in _array(raw.get("civilizations", []), 64):
        if not isinstance(item, dict):
            raise PolicyError("invalid_response")
        # No identities, statistics or even validation-dependent errors from unknown civs.
        if item.get("met") is not True:
            continue
        civ_id = integer(item.get("id"), 0, 63)
        if civ_id in seen:
            raise PolicyError("invalid_response")
        seen.add(civ_id)
        fields = DIPLOMACY_FIELDS.copy()
        # Reject neither values nor types from conditional fields we cannot reveal.
        # Dropping AFTER validation would leak their validity through errors.
        if civ_id != player_id:
            fields.pop("gold_per_turn", None)
        alive = item.get("alive") is True
        if not alive:
            fields = {key: kind for key, kind in fields.items() if kind != "number"}
        info = _project(item, fields)
        info["met"] = True
        if alive and civ_id != player_id and "relationship" in item:
            from .diplomatic_relationships import project_relationship
            relationship = project_relationship(item["relationship"], player_id, civ_id)
            if relationship is not None:
                info["relationship"] = relationship
        if alive and "agendas" in item:
            agendas = []
            for agenda in _array(item["agendas"], 64):
                if not isinstance(agenda, dict):
                    raise PolicyError("invalid_response")
                if agenda.get("visible") is not True:
                    continue
                entry = _project(agenda, {"id": "identifier"})
                if not entry.get("id", "").startswith("AGENDA_"):
                    raise PolicyError("invalid_response")
                agendas.append(entry["id"])
            info["agendas"] = agendas
        if alive and "victory" in item:
            progress = item["victory"]
            if not isinstance(progress, dict):
                raise PolicyError("invalid_response")
            fields = VICTORY_FIELDS.copy()
            if progress.get("science_exoplanet_completed") is not True:
                fields.pop("science_light_years", None)
                fields.pop("science_light_years_per_turn", None)
            info["victory"] = _project(progress, fields)
        civilizations.append(info)
    if len(civilizations) > civilization_count:
        raise PolicyError("invalid_response")
    return {"ok": True, "player_id": player_id, "turn": turn, "active_turn": active,
        "civilization_count": civilization_count, "civilizations": civilizations}


def public_options(raw: dict[str, Any], kind: str, entity_id: int | None) -> dict[str, Any]:
    _, player_id, turn, active = envelope(raw)
    if raw.get("kind") != kind:
        raise PolicyError("invalid_response")
    if kind == "production" and raw.get("entity_id") != entity_id:
        raise PolicyError("invalid_response")
    kinds = {"research": {"research"}, "civic": {"civic"},
             "production": {"unit", "building", "project"}}[kind]
    prefixes = {"research": "TECH_", "civic": "CIVIC_", "unit": "UNIT_",
                "building": "BUILDING_", "project": "PROJECT_"}
    options = []
    for item in _array(raw.get("options", []), 2048):
        if not isinstance(item, dict) or item.get("kind") not in kinds:
            raise PolicyError("invalid_response")
        option = _project(item, {"id": "identifier", "kind": "string"})
        if not option.get("id", "").startswith(prefixes[option["kind"]]):
            raise PolicyError("invalid_response")
        if kind in {"research", "civic"}:
            # Only these documented own-player facts may expand the list.
            # The adapter omits unavailable optional getters; malformed fields
            # supplied to this independent boundary are rejected, never copied.
            for key, limit in (("name", 1024), ("description", 8192), ("boost_description", 8192)):
                if key not in item:
                    continue
                value = item[key]
                permitted_controls = "\n\r\t" if key != "name" else ""
                if (type(value) is not str or len(value) > limit
                        or any(ord(c) < 32 and c not in permitted_controls for c in value)):
                    raise PolicyError("invalid_response")
                option[key] = value
            for key in ("cost", "progress"):
                if key in item:
                    value = item[key]
                    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value < 1e15:
                        raise PolicyError("invalid_response")
                    option[key] = value
            if "turns" in item:
                option["turns"] = integer(item["turns"])
            if "boosted" in item:
                if type(item["boosted"]) is not bool:
                    raise PolicyError("invalid_response")
                option["boosted"] = item["boosted"]
        options.append(option)
    result = {"ok": True, "player_id": player_id, "turn": turn, "active_turn": active,
              "kind": kind, "options": options}
    if kind == "production":
        result["entity_id"] = entity_id
    return result
