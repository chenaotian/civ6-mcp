"""Menu-specific second boundary; hidden data is rejected before projection."""
import json

import pytest

from civ6_fair_mcp.inspection_policy import public_inspection
from civ6_fair_mcp.policy import PolicyError


def inspection(category, *records, player_id=0):
    return {"ok": True, "session": "menu-session-1234567890", "player_id": player_id,
            "turn": 30, "active_turn": True, "category": category,
            "supported": True, "items": list(records)}


GOVERNOR_CATEGORY = "governor_city_state_destinations"


def governor_menu_record(**changes):
    return {"scope": "menu", "menu_source": "governor_city_state", "menu_owner_id": 0,
            "menu_offered": True, "menu_governor": "GOVERNOR_THE_AMBASSADOR",
            "menu_target_owner_id": 6, "menu_city_id": 196610,
            "id": "city_state:6:196610", "name": "那烂陀", **changes}


def governor_menu_action(**changes):
    return {"type": "governor_assign_city_state", "governor": "GOVERNOR_THE_AMBASSADOR",
            "owner_id": 6, "city_id": 196610, **changes}


def menu_record(source="trade", unit_id=131073, **changes):
    return {"scope": "menu", "menu_owner_id": 0, "menu_source": source,
            "menu_offered": True, "menu_unit_id": unit_id,
            "id": "destination:12:8", "name": "菜单中的城市",
            "description": "正常菜单公开的目的地", **changes}


def menu_action(kind="trade_route", unit_id=131073, **changes):
    action = {"type": kind, "unit_id": unit_id, "x": 12, "y": 8}
    if kind == "spy_mission":
        action["mission"] = "SPY_SIPHON_FUNDS"
    return {**action, **changes}


@pytest.mark.parametrize("category,source,kind", [
    ("trade_destinations", "trade", "trade_route"),
    ("trade_routes", "trade", "trade_route"),
    ("spy_destinations", "spy", "spy_travel"),
    ("spy_destinations", "spy", "spy_mission"),
    ("spy_missions", "spy", "spy_travel"),
    ("spy_missions", "spy", "spy_mission"),
])
def test_menu_grants_only_matching_category_source_and_owned_unit(category, source, kind):
    action = menu_action(kind)
    record = menu_record(source, action=action, visible=False, detected=False)
    items = public_inspection(inspection(category, record), category)["items"]
    assert items == [{"id": record["id"], "name": record["name"],
                      "description": record["description"], "action": action}]
    assert items[0]["action"] is not action


@pytest.mark.parametrize("unit_id", [0, 2_147_483_647])
def test_menu_unit_id_bounds_are_inclusive(unit_id):
    record = menu_record(unit_id=unit_id, action=menu_action(unit_id=unit_id))
    result = public_inspection(inspection("trade_routes", record), "trade_routes")
    assert result["items"][0]["action"]["unit_id"] == unit_id


@pytest.mark.parametrize("category,source", [
    ("trade_destinations", "trade"), ("trade_routes", "trade"),
    ("spy_destinations", "spy"), ("spy_missions", "spy"),
])
def test_menu_text_or_yield_needs_no_action_and_never_returns_permission_metadata(category, source):
    record = menu_record(source, value=6.25, hidden_city={"population": 99},
                         x=12, y=8, owner_id=3, met=True, visible=False)
    result = public_inspection(inspection(category, record), category)["items"]
    assert result == [{"id": record["id"], "name": record["name"],
                       "description": record["description"], "value": 6.25}]
    assert "menu_" not in json.dumps(result)


class GetterTrap(dict):
    """A non-JSON adapter object must never get to run its hidden getters."""
    def get(self, *args):
        raise AssertionError("hidden getter invoked")

    def __getitem__(self, key):
        raise AssertionError("hidden field read")

    def __str__(self):
        raise AssertionError("hidden object serialized")


def test_governor_menu_projects_only_public_text_value_and_bound_action():
    action = governor_menu_action()
    record = governor_menu_record(action=action, value=True, visible=False,
                                  x=GetterTrap(), loyalty=GetterTrap(), menu_unit_id=GetterTrap())
    items = public_inspection(inspection(GOVERNOR_CATEGORY, record), GOVERNOR_CATEGORY)["items"]
    assert items == [{"id": record["id"], "name": "那烂陀", "value": True, "action": action}]
    assert items[0]["action"] is not action


def test_governor_menu_disabled_names_and_duration_need_no_action():
    records = [governor_menu_record(value=False),
               governor_menu_record(id="city_state:6:196610:establish_turns", value=5)]
    items = public_inspection(inspection(GOVERNOR_CATEGORY, *records), GOVERNOR_CATEGORY)["items"]
    assert [row["value"] for row in items] == [False, 5]
    assert all("action" not in row and "menu_owner_id" not in row for row in items)


@pytest.mark.parametrize("changes", [
    {"scope": "self", "owner_id": 0}, {"scope": "public"},
    {"scope": "met", "met": True, "owner_id": 6}, {"scope": "visible", "visible": True, "x": 1, "y": 1},
    {"scope": "public", "id": "next_offset", "value": -1},
    {"menu_source": "trade"}, {"menu_source": "spy"}, {"menu_source": None},
    {"menu_owner_id": 1}, {"menu_owner_id": False}, {"menu_offered": False}, {"menu_offered": 1},
    {"menu_governor": "UNIT_SPY"}, {"menu_governor": None}, {"menu_governor": "governor_ambassador"},
    {"menu_governor": "GOVERNOR_" + "X" * 120}, {"menu_governor": "GOVERNOR_X\n"},
    {"menu_target_owner_id": 0}, {"menu_target_owner_id": -1}, {"menu_target_owner_id": 64},
    {"menu_target_owner_id": True}, {"menu_target_owner_id": 6.0},
    {"menu_city_id": -1}, {"menu_city_id": 2_147_483_648}, {"menu_city_id": False},
    {"menu_city_id": "196610"},
])
def test_governor_menu_bad_proof_is_rejected_before_hidden_fields(changes):
    record = governor_menu_record(name=GetterTrap(), description=GetterTrap(), **changes)
    assert public_inspection(inspection(GOVERNOR_CATEGORY, record), GOVERNOR_CATEGORY)["items"] == []


@pytest.mark.parametrize("missing", [
    "menu_source", "menu_owner_id", "menu_offered", "menu_governor", "menu_target_owner_id", "menu_city_id",
])
def test_governor_menu_requires_each_proof_field(missing):
    record = governor_menu_record(name=GetterTrap(), action=GetterTrap())
    del record[missing]
    assert public_inspection(inspection(GOVERNOR_CATEGORY, record), GOVERNOR_CATEGORY)["items"] == []


@pytest.mark.parametrize("action", [
    governor_menu_action(type="governor_assign"), governor_menu_action(type="end_turn"),
    governor_menu_action(governor="GOVERNOR_THE_BUILDER"), governor_menu_action(owner_id=8),
    governor_menu_action(city_id=42), governor_menu_action(owner_id=6.0),
    governor_menu_action(city_id=196610.0), governor_menu_action(city_id=True),
    {}, GetterTrap(), None,
])
def test_governor_menu_action_must_match_exact_governor_and_destination_before_text(action):
    record = governor_menu_record(name=GetterTrap(), action=action)
    assert public_inspection(inspection(GOVERNOR_CATEGORY, record), GOVERNOR_CATEGORY)["items"] == []


@pytest.mark.parametrize("category", ["governors", "city_states", "trade_routes", "spy_destinations"])
def test_governor_menu_grant_does_not_expand_other_categories(category):
    record = governor_menu_record(name=GetterTrap(), action=GetterTrap())
    assert public_inspection(inspection(category, record), category)["items"] == []


def test_governor_menu_action_still_rejects_extra_fields():
    record = governor_menu_record(action=governor_menu_action(x=1))
    with pytest.raises(PolicyError, match="^invalid_response$"):
        public_inspection(inspection(GOVERNOR_CATEGORY, record), GOVERNOR_CATEGORY)


@pytest.mark.parametrize("changes", [
    {"scope": "unknown"}, {"scope": "visible", "visible": False},
    {"scope": "met", "met": False}, {"scope": "self", "owner_id": 2},
    {"menu_offered": False}, {"menu_offered": 1}, {"menu_offered": None},
    {"menu_owner_id": 2}, {"menu_owner_id": False}, {"menu_owner_id": 0.0},
    {"menu_source": "spy"}, {"menu_source": "Trade"}, {"menu_source": None},
    {"menu_source": []}, {"menu_unit_id": -1}, {"menu_unit_id": 2_147_483_648},
    {"menu_unit_id": True}, {"menu_unit_id": 131073.0}, {"menu_unit_id": "131073"},
    {"menu_unit_id": None},
])
def test_bad_menu_authorization_drops_hidden_payload_before_any_validation(changes, monkeypatch):
    import civ6_fair_mcp.actions as actions

    def hidden_action_getter(_):
        raise AssertionError("unauthorized action reached validation")

    monkeypatch.setattr(actions, "validate_action", hidden_action_getter)
    record = menu_record(id=None, name=GetterTrap(), description=GetterTrap(),
                         value=GetterTrap(), action=GetterTrap(), **changes)
    assert public_inspection(inspection("trade_routes", record), "trade_routes")["items"] == []


@pytest.mark.parametrize("missing", ["menu_offered", "menu_owner_id", "menu_source", "menu_unit_id"])
def test_each_menu_proof_field_is_required(missing):
    record = menu_record(id=None, name=GetterTrap(), action=GetterTrap())
    del record[missing]
    assert public_inspection(inspection("trade_routes", record), "trade_routes")["items"] == []


@pytest.mark.parametrize("category", ["unit_actions", "pending_decisions", "city_management", "world_congress"])
def test_menu_scope_cannot_authorize_an_unrelated_category(category):
    record = menu_record(id=None, name=GetterTrap(), action=GetterTrap())
    assert public_inspection(inspection(category, record), category)["items"] == []


@pytest.mark.parametrize("category,source,action", [
    ("trade_routes", "trade", menu_action("spy_travel")),
    ("trade_destinations", "trade", menu_action("spy_mission")),
    ("spy_destinations", "spy", menu_action("trade_route")),
    ("spy_missions", "spy", {"type": "end_turn"}),
    ("trade_routes", "trade", {"type": "run_lua", "unit_id": 131073}),
    ("trade_routes", "trade", menu_action(unit_id=131074)),
    ("trade_routes", "trade", menu_action(unit_id=131073.0)),
    ("trade_routes", "trade", menu_action(unit_id=True)),
    ("trade_routes", "trade", {"type": "trade_route"}),
    ("trade_routes", "trade", {"type": [], "unit_id": 131073}),
    ("trade_routes", "trade", None),
    ("trade_routes", "trade", GetterTrap()),
])
def test_wrong_action_or_unit_is_dropped_before_hidden_text(category, source, action):
    record = menu_record(source, id=None, name=GetterTrap(), action=action)
    assert public_inspection(inspection(category, record), category)["items"] == []


@pytest.mark.parametrize("action", [
    menu_action(x=-1), menu_action(y=4096), menu_action(extra=GetterTrap()),
    menu_action("spy_mission", mission="SPY_SECRET_DEBUG"),
])
def test_authorized_menu_still_requires_exact_normal_action_schema(action):
    source = "spy" if action["type"] == "spy_mission" else "trade"
    category = "spy_missions" if source == "spy" else "trade_routes"
    record = menu_record(source, action=action)
    with pytest.raises(PolicyError, match="^invalid_response$"):
        public_inspection(inspection(category, record), category)


def test_extra_hidden_field_getters_are_never_read_or_exported():
    record = menu_record(extra_field=GetterTrap(), action=menu_action())
    result = public_inspection(inspection("trade_routes", record), "trade_routes")
    assert set(result["items"][0]) == {"id", "name", "description", "action"}
    json.dumps(result)


def test_non_json_record_object_rejected_without_running_getters():
    with pytest.raises(PolicyError, match="^invalid_response$"):
        public_inspection(inspection("trade_routes", GetterTrap()), "trade_routes")


def test_proof_is_bound_to_the_envelope_local_player():
    record = menu_record(menu_owner_id=5)
    assert len(public_inspection(inspection("trade_routes", record, player_id=5), "trade_routes")["items"]) == 1
    assert public_inspection(inspection("trade_routes", record, player_id=0), "trade_routes")["items"] == []


@pytest.mark.parametrize("category", ["trade_destinations", "trade_routes", "spy_destinations", "spy_missions"])
@pytest.mark.parametrize("scope,proof", [
    ("self", {"owner_id": 0}), ("public", {}),
    ("visible", {"visible": True, "x": 12, "y": 8}),
    ("met", {"met": True, "owner_id": 2}),
])
def test_other_scopes_cannot_smuggle_a_target_in_menu_categories(category, scope, proof, monkeypatch):
    import civ6_fair_mcp.actions as actions

    def hidden_action_getter(_):
        raise AssertionError("mislabeled target reached validation")

    monkeypatch.setattr(actions, "validate_action", hidden_action_getter)
    record = {"scope": scope, "id": "target", "name": GetterTrap(),
              "description": GetterTrap(), "value": GetterTrap(), "action": GetterTrap(), **proof}
    assert public_inspection(inspection(category, record), category)["items"] == []


@pytest.mark.parametrize("category", ["trade_destinations", "trade_routes", "spy_destinations", "spy_missions"])
@pytest.mark.parametrize("value", [-1, 0, 1024])
def test_public_menu_cursor_returns_only_id_and_integer_value(category, value):
    record = {"scope": "public", "id": "next_offset", "value": value,
              "name": GetterTrap(), "description": GetterTrap(), "hidden": GetterTrap()}
    assert public_inspection(inspection(category, record), category)["items"] == [
        {"id": "next_offset", "value": value}]


@pytest.mark.parametrize("changes", [
    {"scope": "self", "owner_id": 0}, {"scope": "visible", "visible": True, "x": 1, "y": 1},
    {"scope": "met", "met": True, "owner_id": 2}, {"id": "destination"},
    {"value": True}, {"value": 0.0}, {"value": "1024"}, {"value": -2},
    {"value": 1_000_000_000_000_000}, {"value": GetterTrap()},
    {"action": menu_action()}, {"action": None}, {"action": GetterTrap()},
])
def test_fake_menu_cursor_is_discarded_without_projecting_payload(changes):
    record = {"scope": "public", "id": "next_offset", "value": 1024,
              "name": GetterTrap(), "description": GetterTrap(), **changes}
    assert public_inspection(inspection("trade_destinations", record), "trade_destinations")["items"] == []


def test_other_categories_keep_existing_scope_rules():
    records = [
        {"scope": "public", "id": "public-value", "value": 2},
        {"scope": "self", "owner_id": 0, "id": "own-option", "value": 3},
        {"scope": "visible", "visible": True, "x": 1, "y": 1, "id": "visible-target"},
        {"scope": "met", "met": True, "owner_id": 2, "id": "known-player"},
    ]
    assert public_inspection(inspection("pending_decisions", *records), "pending_decisions")["items"] == [
        {"id": "public-value", "value": 2}, {"id": "own-option", "value": 3},
        {"id": "visible-target"}, {"id": "known-player"},
    ]
