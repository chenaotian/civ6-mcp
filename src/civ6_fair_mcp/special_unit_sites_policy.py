"""Fixed-purpose lens coordinates bound to the requested own specialist."""
from .extensions.base import validate
from .extensions.special_unit_sites import CATEGORY, FIELDS, MAX_SITES
from .policy import PolicyError, envelope, integer


def public_special_unit_sites(raw: dict, params: dict | None) -> dict:
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
    proof = raw.get("special_unit_sites")
    if (type(proof) is not dict or proof.get("source") != "stock_selected_unit_lens"
            or type(proof.get("owner_id")) is not int or proof["owner_id"] != me
            or type(proof.get("unit_id")) is not int or proof["unit_id"] != requested["unit_id"]
            or proof.get("eligible") is not True
            or type(proof.get("purpose")) is not str
            or proof["purpose"] not in {"excavate", "national_park", "great_person", "rock_concert"}):
        return public
    records = raw.get("items")
    if type(records) is not list or len(records) > MAX_SITES:
        raise PolicyError("invalid_response")
    coordinates = set()
    for row in records:
        if type(row) is not dict:
            raise PolicyError("invalid_response")
        # No malformed hidden content is inspected before permission proof.
        if row.get("revealed") is not True or row.get("highlighted") is not True:
            continue
        x, y = integer(row.get("x"), 0, 4095), integer(row.get("y"), 0, 4095)
        if (x, y) in coordinates:
            raise PolicyError("invalid_response")
        coordinates.add((x, y))
    for index, (x, y) in enumerate(sorted(coordinates, key=lambda pair: (pair[1], pair[0]))):
        public["items"].extend([
            {"id": f"site:{index}:x", "value": x},
            {"id": f"site:{index}:y", "value": y},
            {"id": f"site:{index}:purpose", "value": proof["purpose"]},
        ])
    return public
