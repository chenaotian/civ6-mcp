"""Strict projection bound to the requested attacker and detected target."""
from __future__ import annotations

import math
import re

from .extensions.base import validate
from .extensions.combat_preview import FIELDS
from .policy import PolicyError, envelope


_MODIFIER = re.compile(r"(attacker|defender)_modifier:([1-9][0-9]{0,2})\Z", re.ASCII)


def public_combat_preview(raw: dict, params: dict | None) -> dict:
    _, me, turn, active = envelope(raw)
    if raw.get("category") != "combat_preview" or type(raw.get("supported")) is not bool:
        raise PolicyError("invalid_response")
    result = {"ok": True, "player_id": me, "turn": turn, "active_turn": active,
              "category": "combat_preview", "supported": raw["supported"], "items": []}
    if not active or not raw["supported"]:
        return result
    # A generic caller without the original validated request cannot authorize
    # combat fields merely by relabeling them as self/public/visible items.
    try:
        expected = validate(params, FIELDS)
    except (ValueError, TypeError):
        return result
    proof = raw.get("combat_preview")
    if type(proof) is not dict or proof.get("source") != "stock_unit_panel":
        return result
    if (type(proof.get("attacker_owner_id")) is not int or proof["attacker_owner_id"] != me
            or expected["target_owner_id"] == me or expected["target_owner_id"] > 63):
        return result
    for key, value in expected.items():
        if type(proof.get(key)) is not type(value) or proof[key] != value:
            return result
    if any(proof.get(key) is not True for key in (
            "revealed", "visible", "detected", "legal_action", "can_attack_target",
            "attacker_matches", "defender_matches")):
        return result
    # Validate content only after all identity and perception proofs pass.
    records = raw.get("items")
    if type(records) is not list or len(records) > 515:
        raise PolicyError("invalid_response")
    items, seen = [], set()
    modifier_indices: dict[str, set[int]] = {"attacker": set(), "defender": set()}
    for row in records:
        if type(row) is not dict or row.keys() != {"id", "value"}:
            raise PolicyError("invalid_response")
        identifier, value = row["id"], row["value"]
        if type(identifier) is not str or identifier in seen:
            raise PolicyError("invalid_response")
        seen.add(identifier)
        if identifier in {"attacker_strength", "defender_strength"}:
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1_000_000:
                raise PolicyError("invalid_response")
        elif identifier == "combat_type":
            allowed = {"melee"} if expected["attacker_kind"] == "unit_melee" else {"ranged", "bombard"}
            if type(value) is not str or value not in allowed:
                raise PolicyError("invalid_response")
        else:
            match = _MODIFIER.fullmatch(identifier)
            if not match or int(match[2]) > 256:
                raise PolicyError("invalid_response")
            if (type(value) is not str or not 1 <= len(value) <= 8192
                    or any(ord(c) < 32 or ord(c) == 127 for c in value)):
                raise PolicyError("invalid_response")
            modifier_indices[match[1]].add(int(match[2]))
        items.append({"id": identifier, "value": value})
    if not {"attacker_strength", "defender_strength", "combat_type"} <= seen:
        raise PolicyError("invalid_response")
    if any(indices != set(range(1, len(indices) + 1)) for indices in modifier_indices.values()):
        raise PolicyError("invalid_response")
    result["items"] = items
    return result
