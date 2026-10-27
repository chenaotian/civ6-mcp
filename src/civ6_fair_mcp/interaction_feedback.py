"""Bounded feedback derived only from already projected public observations.

No engine access, stored foreign/map observations, executable capabilities or
causal claims. A changed field is not proof an earlier request completed.
"""
from __future__ import annotations

from copy import deepcopy


MAX_EVENTS = 64
_PLAYER = ("gold", "faith", "gold_per_turn", "faith_per_turn", "science_per_turn",
           "culture_per_turn", "research", "civic")
_UNIT = ("type", "x", "y", "moves", "damage", "build_charges")
_CITY = ("population", "production", "production_turns", "production_indefinite")
_BLOCKERS = {
    "ENDTURN_BLOCKING_RESEARCH": ("list_options", {"kind": "research"}),
    "ENDTURN_BLOCKING_CIVIC": ("list_options", {"kind": "civic"}),
    "ENDTURN_BLOCKING_PRODUCTION": ("get_player_state", {}),
    "ENDTURN_BLOCKING_UNITS": ("get_player_state", {}),
    "ENDTURN_BLOCKING_STACKED_UNITS": ("get_player_state", {}),
    "ENDTURN_BLOCKING_UNIT_NEEDS_ORDERS": ("get_player_state", {}),
    "ENDTURN_BLOCKING_CONSIDER_GOVERNMENT_CHANGE": ("inspect_game", {"category": "government"}),
    "ENDTURN_BLOCKING_FILL_CIVIC_SLOT": ("inspect_game", {"category": "government"}),
    "ENDTURN_BLOCKING_GOVERNOR_APPOINTMENT": ("inspect_game", {"category": "governors"}),
    "ENDTURN_BLOCKING_GOVERNOR_OPPORTUNITY": ("inspect_game", {"category": "governors"}),
    "ENDTURN_BLOCKING_GOVERNOR_PROMOTION": ("inspect_game", {"category": "governors"}),
    "ENDTURN_BLOCKING_GOVERNOR_IDLE": ("inspect_game", {"category": "governors"}),
    "ENDTURN_BLOCKING_CLAIM_GREAT_PERSON": ("inspect_game", {"category": "great_people"}),
    "ENDTURN_BLOCKING_GIVE_INFLUENCE_TOKEN": ("inspect_game", {"category": "city_states"}),
    "ENDTURN_BLOCKING_PANTHEON": ("inspect_game", {"category": "religion"}),
    "ENDTURN_BLOCKING_RELIGION": ("inspect_game", {"category": "religion"}),
    "ENDTURN_BLOCKING_BELIEF": ("inspect_game", {"category": "religion"}),
    "ENDTURN_BLOCKING_ARTIFACT": ("inspect_game", {"category": "archaeology"}),
    "ENDTURN_BLOCKING_SPY_CHOOSE_ESCAPE_ROUTE": ("inspect_game", {"category": "spy_escape_routes"}),
    "ENDTURN_BLOCKING_WORLD_CONGRESS_SESSION": ("inspect_game", {"category": "world_congress"}),
    "ENDTURN_BLOCKING_WORLD_CONGRESS_LOOK": ("inspect_game", {"category": "world_congress"}),
    "ENDTURN_BLOCKING_EMERGENCY_NEEDS_ATTENTION": ("inspect_game", {"category": "emergencies"}),
}


def next_steps(ui: dict) -> list[dict]:
    """Read suggestions only; never invent a button, action, ID or success."""
    result = []
    if ui.get("status") in {"partial", "unavailable"}:
        result.append({"reason": "ui_incomplete", "tool": "get_game_status", "args": {}})
    for popup in ui.get("popups", []):
        offered = any("action" in b for b in popup.get("buttons", []))
        result.append({"reason": "visible_popup", "popup": popup["id"],
                       "guidance": "use_current_offered_button" if offered else "refresh_before_response"})
    for blocker in dict.fromkeys(ui.get("turn_blockers", [])):
        tool, args = _BLOCKERS.get(blocker, ("get_pending_decisions", {}))
        result.append({"reason": "turn_blocker", "blocker": blocker,
                       "tool": tool, "args": dict(args)})
    if ui.get("engine_activity") == "busy":
        result.append({"reason": "engine_busy", "tool": "wait_for_change", "args": {}})
    elif ui.get("status") == "waiting":
        result.append({"reason": "waiting_for_player_turn", "tool": "wait_for_change", "args": {}})
    return result


def snapshot(kind: str, public: dict) -> dict:
    """Retain only own-player fields and small public UI metadata, never a map."""
    out = {"turn": public.get("turn"), "active_turn": public.get("active_turn")}
    if "status" in public:
        out["status"] = public["status"]
    if "game_state_available" in public:
        out["game_state_available"] = public["game_state_available"]
    ui = public.get("ui")
    if isinstance(ui, dict):
        out["ui"] = {key: deepcopy(ui[key]) for key in
                     ("status", "engine_activity", "turn_blockers", "modal_unavailable_reason") if key in ui}
        out["ui"]["popup_ids"] = [p["id"] for p in ui.get("popups", [])]
    if kind == "player" and public.get("game_state_available") is not False:
        if "player" in public:
            out["player"] = {key: deepcopy(public["player"][key]) for key in _PLAYER if key in public["player"]}
        for group, fields in (("units", _UNIT), ("cities", _CITY)):
            if group in public:
                out[group] = {
                    item["id"]: {key: deepcopy(item[key]) for key in fields if key in item}
                    for item in public[group]
                    if item.get("owner_id") == public.get("player_id")
                }
    return out


def changes(before: dict, after: dict) -> dict:
    """Diff equal-query, equal-session snapshots; the caller checks identity."""
    events = []
    omitted = 0

    def add(event):
        nonlocal omitted
        if len(events) < MAX_EVENTS:
            events.append(event)
        else:
            omitted += 1

    def fields(entity, old, new, entity_id=None):
        for key in sorted(old.keys() | new.keys()):
            if old.get(key) == new.get(key) and (key in old) == (key in new):
                continue
            event = {"kind": "field_changed", "entity": entity, "field": key,
                     "before_known": key in old, "after_known": key in new}
            if entity_id is not None:
                event["id"] = entity_id
            if key in old:
                event["before"] = deepcopy(old[key])
            if key in new:
                event["after"] = deepcopy(new[key])
            add(event)

    common = ("active_turn", "status", "game_state_available")
    fields("observation", {k: before[k] for k in common if k in before},
           {k: after[k] for k in common if k in after})
    for group in ("player", "ui"):
        if group in before and group in after:
            fields(group, before[group], after[group])
    for group in ("units", "cities"):
        if group not in before or group not in after:
            continue  # Failed/recovered world reads are not mass losses.
        old, new = before[group], after[group]
        for entity_id in sorted(old.keys() | new.keys()):
            if entity_id not in new:
                add({"kind": "no_longer_observed", "entity": group, "id": entity_id,
                     "cause": "unknown"})
            elif entity_id not in old:
                add({"kind": "now_observed", "entity": group, "id": entity_id,
                     "cause": "unknown"})
            else:
                fields(group, old[entity_id], new[entity_id], entity_id)
    return {"basis": "same_query_public_observations", "from_turn": before["turn"],
            "to_turn": after["turn"], "events": events, "truncated": omitted > 0}
