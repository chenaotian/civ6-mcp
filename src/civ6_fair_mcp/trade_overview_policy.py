"""Narrow second boundary for the stock own-route inventory and its endpoints."""
from __future__ import annotations

import math
import re

from .policy import PolicyError, envelope


_ROUTE = re.compile(r"route:([0-9]{1,10}):(trader_unit_id|origin_city_id|origin_name|origin_x|origin_y|destination_owner_id|destination_name|destination_x|destination_y|(?:origin|destination)_yield:YIELD_(?:FOOD|PRODUCTION|GOLD|SCIENCE|CULTURE|FAITH))\Z", re.ASCII)
_TRADER = re.compile(r"trader:([0-9]{1,10}):status\Z", re.ASCII)
_COUNTS = frozenset({"active_count", "capacity", "idle_trader_count"})


def _int(value: object, maximum: int = 2_147_483_647) -> bool:
    return type(value) is int and 0 <= value <= maximum


def public_trade_overview(raw: dict) -> dict:
    _, me, turn, active = envelope(raw)
    if raw.get("category") != "own_trade_routes" or type(raw.get("supported")) is not bool:
        raise PolicyError("invalid_response")
    records = raw.get("items")
    if type(records) is not list or len(records) > 2048:
        raise PolicyError("invalid_response")
    items = []
    public = {"ok": True, "player_id": me, "turn": turn, "active_turn": active,
        "category": "own_trade_routes", "supported": raw["supported"], "items": items}
    # Incomplete native inventories must never become an idle/count claim,
    # even if an upstream implementation accidentally retained partial rows.
    if raw["supported"] is False:
        return public
    for row in records:
        if type(row) is not dict:
            raise PolicyError("invalid_response")
        identifier = row.get("id")
        if type(identifier) is not str or "action" in row:
            continue
        trader = _TRADER.fullmatch(identifier)
        if identifier in _COUNTS or trader:
            if row.get("scope") != "self" or not _int(row.get("owner_id"), 63) or row["owner_id"] != me:
                continue
            value = row.get("value")
            if identifier in _COUNTS:
                if not _int(value, 4096):
                    raise PolicyError("invalid_response")
            elif not _int(int(trader[1])) or type(value) is not str or value not in {"active", "idle"}:
                raise PolicyError("invalid_response")
        else:
            route = _ROUTE.fullmatch(identifier)
            if not route or row.get("scope") != "menu" or row.get("menu_source") != "trade_overview":
                continue
            actor, field = int(route[1]), route[2]
            if (not _int(actor) or not _int(row.get("menu_unit_id")) or row["menu_unit_id"] != actor
                    or row.get("menu_offered") is not True
                    or not _int(row.get("menu_owner_id"), 63) or row["menu_owner_id"] != me
                    or not _int(row.get("menu_origin_owner_id"), 63) or row["menu_origin_owner_id"] != me
                    or not _int(row.get("menu_origin_city_id"))):
                continue
            is_yield = "_yield:" in field
            if is_yield and row.get("menu_yields_calculated") is not True:
                continue
            if field.startswith("destination_") or is_yield:
                if row.get("menu_destination_known") is not True or not _int(row.get("menu_destination_owner_id"), 63):
                    continue
                if field in {"destination_x", "destination_y"} and row.get("menu_destination_revealed") is not True:
                    continue
            value = row.get("value")
            if is_yield:
                if type(value) not in (int, float) or abs(value) > 1_000_000 or not math.isfinite(value):
                    raise PolicyError("invalid_response")
                value = math.floor(value * 10 + 0.5) / 10
            elif field.endswith("_name"):
                if type(value) is not str or not 1 <= len(value) <= 1024 or "\x00" in value:
                    raise PolicyError("invalid_response")
            elif field.endswith(("_x", "_y")):
                if not _int(value, 4095):
                    raise PolicyError("invalid_response")
            elif field == "destination_owner_id":
                if not _int(value, 63) or value != row["menu_destination_owner_id"]:
                    raise PolicyError("invalid_response")
            elif field == "origin_city_id":
                if not _int(value) or value != row["menu_origin_city_id"]:
                    raise PolicyError("invalid_response")
            elif field == "trader_unit_id" and (not _int(value) or value != actor):
                raise PolicyError("invalid_response")
        # Deliberately no arbitrary raw names/descriptions, nested route data,
        # actions, proof fields or historical route reasons pass this boundary.
        items.append({"id": identifier, "value": value})
    return public
