"""Narrow projection for stock recommendations, bound to the requested actor."""
import re

from .extensions.base import validate
from .extensions.stock_recommendations import CATEGORY, FIELDS, MAX_RECOMMENDATIONS
from .policy import PolicyError, envelope, integer

_IMPROVEMENT = re.compile(r"IMPROVEMENT_[A-Z0-9_]{1,116}\Z", re.ASCII)


def public_unit_recommendations(raw: dict, params: dict | None) -> dict:
    _, me, turn, active = envelope(raw)
    if raw.get("category") != CATEGORY or type(raw.get("supported")) is not bool:
        raise PolicyError("invalid_response")
    public = {"ok": True, "player_id": me, "turn": turn, "active_turn": active,
              "category": CATEGORY, "supported": raw["supported"], "items": []}
    if not raw["supported"]:
        return public
    try:
        requested = validate(params, FIELDS)
    except (ValueError, TypeError):
        return public
    proof = raw.get("unit_recommendations")
    if (type(proof) is not dict or proof.get("source") != "stock_world_view_icons"
            or type(proof.get("owner_id")) is not int or proof["owner_id"] != me
            or type(proof.get("unit_id")) is not int or proof["unit_id"] != requested["unit_id"]
            or type(proof.get("kind")) is not str or proof["kind"] not in {"builder", "settler"}):
        return public
    records = raw.get("items")
    limit = 5 if proof["kind"] == "settler" else MAX_RECOMMENDATIONS
    if type(records) is not list or len(records) > limit:
        raise PolicyError("invalid_response")
    accepted, seen = [], set()
    for row in records:
        if type(row) is not dict:
            raise PolicyError("invalid_response")
        if row.get("visible") is not True or row.get("revealed") is not True or row.get("recommended") is not True:
            continue
        x, y = integer(row.get("x"), 0, 4095), integer(row.get("y"), 0, 4095)
        identifier = None
        if proof["kind"] == "builder":
            identifier = row.get("improvement")
            if type(identifier) is not str or not _IMPROVEMENT.fullmatch(identifier):
                raise PolicyError("invalid_response")
        key = x, y, identifier
        if key in seen:
            raise PolicyError("invalid_response")
        seen.add(key)
        accepted.append((x, y, identifier, row))
    for index, (x, y, identifier, row) in enumerate(sorted(accepted, key=lambda v: (v[1], v[0], v[2] or ""))):
        prefix = f"recommendation:{index}"
        public["items"].extend([
            {"id": prefix + ":x", "value": x},
            {"id": prefix + ":y", "value": y},
            {"id": prefix + ":kind", "value": proof["kind"]},
        ])
        if identifier is not None:
            item = {"id": prefix + ":improvement", "value": identifier}
            if "name" in row:
                name = row["name"]
                if type(name) is not str or len(name) > 1024 or "\x00" in name:
                    raise PolicyError("invalid_response")
                item["name"] = name
            public["items"].append(item)
    return public
