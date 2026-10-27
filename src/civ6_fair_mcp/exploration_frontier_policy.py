"""Independent, request-bound projection for exploration labels and geometry."""
from .extensions.base import validate
from .extensions.exploration_frontier import CATEGORY, FIELDS, PAGE_SIZE, MAX_PLOTS
from .policy import PolicyError, envelope, integer


def public_exploration_frontier(raw: dict, params: dict | None) -> dict:
    _, me, turn, active = envelope(raw)
    if raw.get("category") != CATEGORY or type(raw.get("supported")) is not bool:
        raise PolicyError("invalid_response")
    result = {"ok": True, "player_id": me, "turn": turn, "active_turn": active,
              "category": CATEGORY, "supported": raw["supported"], "items": []}
    if not raw["supported"]:
        return result
    try:
        requested = validate(params, FIELDS)
    except (ValueError, TypeError):
        return result
    proof = raw.get("frontier")
    if (type(proof) is not dict or proof.get("source") != "local_visibility_labels"
            or type(proof.get("owner_id")) is not int or proof["owner_id"] != me
            or type(proof.get("offset")) is not int or proof["offset"] != requested["offset"]):
        return result
    width = integer(proof.get("width"), 1, 4096)
    height = integer(proof.get("height"), 1, 4096)
    offset = requested["offset"]
    total = width * height
    if total > MAX_PLOTS or offset > total:
        raise PolicyError("invalid_response")
    stop = min(offset + PAGE_SIZE, total)
    expected_next = stop if stop < total else -1
    if type(proof.get("next_offset")) is not int or proof["next_offset"] != expected_next:
        raise PolicyError("invalid_response")
    rows = raw.get("items")
    if type(rows) is not list or len(rows) > PAGE_SIZE:
        raise PolicyError("invalid_response")
    sites = {}
    for row in rows:
        if type(row) is not dict:
            raise PolicyError("invalid_response")
        if row.get("revealed") is not True or row.get("adjacent_unrevealed") is not True:
            continue
        x, y = integer(row.get("x"), 0, width - 1), integer(row.get("y"), 0, height - 1)
        index = y * width + x
        if not offset <= index < stop or index in sites or type(row.get("visible")) is not bool:
            raise PolicyError("invalid_response")
        sites[index] = (x, y, row["visible"])
    for index, (x, y, visible) in sorted(sites.items()):
        result["items"].extend([
            {"id": f"frontier:{index}:x", "value": x},
            {"id": f"frontier:{index}:y", "value": y},
            {"id": f"frontier:{index}:visible", "value": visible},
        ])
    result["items"].append({"id": "next_offset", "value": expected_next})
    return result
