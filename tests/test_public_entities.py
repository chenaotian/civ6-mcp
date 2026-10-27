import copy

import pytest

from civ6_fair_mcp.policy import PolicyError, public_map


def raw(tile):
    return {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 10,
            "active_turn": True, "tiles": [{"x": 3, "y": 4,
            "revealed": True, "visible": True, **tile}]}


def test_plot_visibility_is_not_unit_detection():
    clean = raw({"units": []})
    hostile = raw({"units": [{"detected": False, "type": "UNIT_SUBMARINE",
        "name": object(), "x": -999, "secret_orders": "attack Beijing"}]})
    assert public_map(clean) == public_map(hostile)


def test_visible_unit_projects_only_public_fields():
    unit = {"owner_id": 1, "id": 7, "x": 3, "y": 4, "type": "UNIT_SUBMARINE",
        "name": "潜艇", "damage": 10, "max_damage": 100, "combat": 65, "ranged_combat": 75}
    result = public_map(raw({"units": [{**unit, "detected": True,
        "orders": "secret", "moves": 99, "build_charges": 123}]}))
    assert result["tiles"][0]["units"] == [unit]


def test_undetected_unit_details_can_change_without_observation_change():
    a = raw({"units": [{"detected": False}]})
    b = copy.deepcopy(a)
    b["tiles"][0]["units"][0].update(id=900, type="UNIT_SPY", owner_id=4,
        x=1000, y=1000, secret_population=9999)
    assert public_map(a) == public_map(b)


def test_fog_hides_all_city_and_unit_data_even_when_proof_flags_are_true():
    a = raw({"visible": False})
    b = raw({"visible": False, "units": [{"detected": True, "id": object()}],
             "city": {"visible": True, "name": object()}})
    assert public_map(a) == public_map(b)


def test_visible_city_user_approved_fields_are_returned_without_extra_state():
    city = {"owner_id": 1, "id": 9, "x": 3, "y": 4, "name": "Rome", "population": 8,
        "damage": 20, "max_damage": 200, "wall_damage": 10, "wall_max_damage": 100,
        "religion": "RELIGION_BUDDHISM", "production": "UNIT_SETTLER", "production_turns": 3,
        "buildings": ["BUILDING_MONUMENT"], "districts": ["DISTRICT_CITY_CENTER"]}
    result = public_map(raw({"city": {**city, "visible": True,
        "worked_tiles": [{"x": 100, "y": 100}], "espionage": "secret", "gold_per_turn": 88}}))
    assert result["tiles"][0]["city"] == city


def test_invisible_city_is_not_returned_or_inspected():
    assert public_map(raw({"city": {"visible": False, "name": object()}})) == public_map(raw({}))


@pytest.mark.parametrize("field,proof", [("units", "detected"), ("city", "visible")])
def test_entity_must_be_at_observed_visible_tile(field, proof):
    entity = {proof: True, "owner_id": 1, "id": 1, "x": 8, "y": 9}
    with pytest.raises(PolicyError):
        public_map(raw({field: [entity] if field == "units" else entity}))


def test_city_nested_coordinates_cannot_be_smuggled_via_buildings():
    city = {"visible": True, "owner_id": 1, "id": 1, "x": 3, "y": 4,
            "buildings": [{"type": "BUILDING_MONUMENT", "x": 99, "y": 99}]}
    with pytest.raises(PolicyError):
        public_map(raw({"city": city}))
