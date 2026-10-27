"""Second boundary for typed gameplay inspection and executable choices."""
from __future__ import annotations

import math
import re
from .policy import PolicyError, envelope, integer


_MENU_CATEGORIES = {
    "trade_destinations": ("trade", frozenset({"trade_route"})),
    "trade_routes": ("trade", frozenset({"trade_route"})),
    "spy_destinations": ("spy", frozenset({"spy_travel", "spy_mission"})),
    "spy_missions": ("spy", frozenset({"spy_travel", "spy_mission"})),
    "governor_city_state_destinations": ("governor_city_state", frozenset({"governor_assign_city_state"})),
}
_GOVERNOR_IDENTIFIER = re.compile(r"GOVERNOR_[A-Z0-9_]{1,119}\Z", re.ASCII)


def public_inspection(raw: dict, category: str, params: dict | None = None) -> dict:
    if category == "exploration_frontier":
        from .exploration_frontier_policy import public_exploration_frontier
        return public_exploration_frontier(raw, params)
    if category == "unit_recommendations":
        from .stock_recommendations_policy import public_unit_recommendations
        return public_unit_recommendations(raw, params)
    if category == "special_unit_sites":
        from .special_unit_sites_policy import public_special_unit_sites
        return public_special_unit_sites(raw, params)
    if category == "combat_preview":
        from .combat_preview_policy import public_combat_preview
        return public_combat_preview(raw, params)
    if category == "own_trade_routes":
        from .trade_overview_policy import public_trade_overview
        return public_trade_overview(raw)
    from .actions import validate_action
    _, me, turn, active = envelope(raw)
    if raw.get("category") != category or type(raw.get("supported")) is not bool:
        raise PolicyError("invalid_response")
    records = raw.get("items")
    if type(records) is not list or len(records) > 2048:
        raise PolicyError("invalid_response")
    result = []
    menu = _MENU_CATEGORIES.get(category)
    for record in records:
        if type(record) is not dict:
            raise PolicyError("invalid_response")
        scope = record.get("scope")
        # All permission checks precede validation/copying of possibly hidden data.
        if menu is not None and scope != "menu":
            # Only the pagination cursor is public in a menu category. A
            # mislabeled target/yield cannot fall back to self/met/visible.
            if (category != "governor_city_state_destinations" and scope == "public"
                    and record.get("id") == "next_offset" and "action" not in record):
                value = record.get("value")
                if type(value) is int and -1 <= value < 1_000_000_000_000_000:
                    result.append({"id": "next_offset", "value": value})
            continue
        if scope == "self":
            if type(record.get("owner_id")) is not int or record["owner_id"] != me:
                continue
        elif scope == "menu":
            if menu is None or record.get("menu_offered") is not True:
                continue
            if type(record.get("menu_owner_id")) is not int or record["menu_owner_id"] != me:
                continue
            if type(record.get("menu_source")) is not str or record["menu_source"] != menu[0]:
                continue
            if category == "governor_city_state_destinations":
                governor = record.get("menu_governor")
                owner_id, city_id = record.get("menu_target_owner_id"), record.get("menu_city_id")
                if (type(governor) is not str or not _GOVERNOR_IDENTIFIER.fullmatch(governor)
                        or type(owner_id) is not int or not 0 <= owner_id <= 63 or owner_id == me
                        or type(city_id) is not int or not 0 <= city_id <= 2_147_483_647):
                    continue
                if "action" in record:
                    action = record["action"]
                    if (type(action) is not dict or type(action.get("type")) is not str
                            or action["type"] not in menu[1]
                            or type(action.get("governor")) is not str or action["governor"] != governor
                            or type(action.get("owner_id")) is not int or action["owner_id"] != owner_id
                            or type(action.get("city_id")) is not int or action["city_id"] != city_id):
                        continue
            else:
                unit_id = record.get("menu_unit_id")
                if type(unit_id) is not int or not 0 <= unit_id <= 2_147_483_647:
                    continue
                # Unit menu proof authorizes only this unit's matching menu operations.
                # Check before validating/copying any destination text or value.
                if "action" in record:
                    action = record["action"]
                    if (type(action) is not dict or type(action.get("type")) is not str
                            or action["type"] not in menu[1]
                            or type(action.get("unit_id")) is not int
                            or action["unit_id"] != unit_id):
                        continue
        elif scope == "visible":
            if record.get("visible") is not True:
                continue
            if "detected" in record and record["detected"] is not True:
                continue
            integer(record.get("x"), 0, 4095)
            integer(record.get("y"), 0, 4095)
        elif scope == "met":
            if record.get("met") is not True:
                continue
            integer(record.get("owner_id"), 0, 63)
        elif scope != "public":
            continue
        item = {}
        for key, limit in (("id", 256), ("name", 1024), ("description", 8192)):
            if key in record:
                value = record[key]
                if type(value) is not str or len(value) > limit or "\x00" in value:
                    raise PolicyError("invalid_response")
                item[key] = value
        if not item.get("id"):
            raise PolicyError("invalid_response")
        if "value" in record:
            value = record["value"]
            if type(value) not in (str, bool, int, float):
                raise PolicyError("invalid_response")
            if type(value) is str and (len(value) > 2048 or "\x00" in value):
                raise PolicyError("invalid_response")
            if type(value) in (int, float) and (not math.isfinite(value) or abs(value) >= 1e15):
                raise PolicyError("invalid_response")
            item["value"] = value
        if "action" in record:
            try:
                item["action"] = validate_action(record["action"])
            except (ValueError, TypeError, KeyError):
                raise PolicyError("invalid_response") from None
        result.append(item)
    return {"ok": True, "player_id": me, "turn": turn, "active_turn": active,
            "category": category, "supported": raw["supported"], "items": result}
