import copy
import json

import pytest

from civ6_fair_mcp.policy import PolicyError, parse_response, public_map, public_player


def envelope(**extra):
    return {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 15,
            "active_turn": True, **extra}


def test_hidden_world_changes_do_not_change_observation():
    tiles = [{"x": 1, "y": 2, "revealed": False, "visible": False},
             {"x": 2, "y": 2, "revealed": True, "visible": False}]
    a = envelope(tiles=tiles)
    b = copy.deepcopy(a)
    for tile in b["tiles"]:
        tile.update(terrain="TERRAIN_SECRET", resource="RESOURCE_URANIUM",
                    resource_visible=True, owner_id=7, units=["SUBMARINE"],
                    cities=[{"population": 99}], yield_food=999, hidden_seed=78)
    assert public_map(a) == public_map(b)
    assert "SECRET" not in json.dumps(public_map(b))


@pytest.mark.parametrize("district", ["NONE", "DISTRICT_CAMPUS", "DISTRICT_CITY_CENTER"])
def test_visible_district_field_passes_independent_whitelist(district):
    raw = envelope(tiles=[{"x": 2, "y": 1, "revealed": True, "visible": True, "district": district}])
    assert public_map(raw)["tiles"][0]["district"] == district


@pytest.mark.parametrize("district", ["TECH_WRITING", "DISTRICT_", "DISTRICT_CAMPUS;attack()", 3, None])
def test_visible_district_rejects_non_district_identifier(district):
    raw = envelope(tiles=[{"x": 2, "y": 1, "revealed": True, "visible": True, "district": district}])
    with pytest.raises(PolicyError):
        public_map(raw)


@pytest.mark.parametrize("revealed", [False, True])
def test_hidden_district_injection_is_discarded_before_validation(revealed):
    raw = envelope(tiles=[{"x": 2, "y": 1, "revealed": revealed, "visible": False,
                          "district": {"secret": "DISTRICT_SPACEPORT"}}])
    assert public_map(raw)["tiles"] == [{"x": 2, "y": 1, "revealed": revealed, "visible": False}]


@pytest.mark.parametrize("field", ["is_nw_of_cliff", "is_w_of_cliff", "is_ne_of_cliff"])
@pytest.mark.parametrize("value", [True, False])
def test_visible_cliff_edges_are_strict_independent_booleans(field, value):
    raw = envelope(tiles=[{"x": 2, "y": 1, "revealed": True, "visible": True, field: value}])
    assert public_map(raw)["tiles"][0][field] is value


@pytest.mark.parametrize("field", ["is_nw_of_cliff", "is_w_of_cliff", "is_ne_of_cliff"])
@pytest.mark.parametrize("value", [0, 1, "true", None, {"secret": "cliff"}])
def test_visible_cliff_edges_reject_non_boolean_values(field, value):
    raw = envelope(tiles=[{"x": 2, "y": 1, "revealed": True, "visible": True, field: value}])
    with pytest.raises(PolicyError):
        public_map(raw)


@pytest.mark.parametrize("revealed", [False, True])
def test_fogged_cliff_injection_is_discarded_before_value_validation(revealed):
    tile = {"x": 2, "y": 1, "revealed": revealed, "visible": False}
    changed = {**tile, "is_nw_of_cliff": {"secret": 1}, "is_w_of_cliff": True,
               "is_ne_of_cliff": "SECRET_NEIGHBOR"}
    assert public_map(envelope(tiles=[changed])) == public_map(envelope(tiles=[tile]))


def test_own_city_indefinite_production_is_explicit_and_foreign_metadata_discarded():
    raw = envelope(cities=[
        {"owner_id": 0, "id": 12, "x": 2, "y": 0, "production_indefinite": True},
        {"owner_id": 1, "id": 99, "production_indefinite": {"secret": 1}},
    ])
    assert public_player(raw)["cities"] == [
        {"owner_id": 0, "id": 12, "x": 2, "y": 0, "production_indefinite": True}
    ]


@pytest.mark.parametrize("fields", [
    {"production_turns": -1}, {"production_indefinite": 1},
    {"production_indefinite": True, "production_turns": 4},
])
def test_python_boundary_rejects_invalid_or_contradictory_production_estimate(fields):
    raw = envelope(cities=[{"owner_id": 0, "id": 12, "x": 2, "y": 0, **fields}])
    with pytest.raises(PolicyError):
        public_player(raw)


def test_resource_and_yield_noninterference_even_on_visible_tiles():
    a = envelope(tiles=[{"x": 1, "y": 1, "visible": True, "revealed": True,
                         "terrain": "TERRAIN_GRASS"}])
    b = copy.deepcopy(a)
    b["tiles"][0].update(resource="RESOURCE_URANIUM", resource_visible=False,
                         yields={"production": 99}, enemy_units=["invisible"])
    assert public_map(a) == public_map(b)
    b["tiles"][0]["resource_visible"] = True
    assert public_map(b)["tiles"][0]["resource"] == "RESOURCE_URANIUM"
    assert "yields" not in public_map(b)["tiles"][0]


def test_foreign_entities_and_unknown_fields_are_dropped():
    own = {"owner_id": 0, "id": 2, "x": 3, "y": 4, "name": "北京"}
    raw = envelope(player={"gold": 50, "all_players": "secret"},
                   units=[own, {"owner_id": 1, "secret": object()}],
                   cities=[{**own, "enemy_population": 42}, {"owner_id": 1}],
                   seed=42, secrets={"players": [1, 2, 3]})
    out = public_player(raw)
    assert out["units"] == [own]
    assert out["cities"] == [own]
    assert out["player"] == {"gold": 50}
    assert "session" not in out and "secrets" not in out


@pytest.mark.parametrize('candidate', [9,True,'1',-1,object()])
def test_first_ready_pointer_cannot_reintroduce_foreign_or_malformed_ids(candidate):
    own={'owner_id':0,'id':1,'x':3,'y':4}
    raw=envelope(units=[own,{'owner_id':1,'id':9,'secret':object()}],
        first_ready_unit_checked=True,first_ready_unit_id=candidate)
    assert 'first_ready_unit_id' not in public_player(raw)


def test_first_ready_pointer_requires_capability_proof_and_matching_own_id():
    own={'owner_id':0,'id':1,'x':3,'y':4}
    raw=envelope(units=[own],first_ready_unit_id=1)
    assert 'first_ready_unit_id' not in public_player(raw)
    raw['first_ready_unit_checked']=True
    assert public_player(raw)['first_ready_unit_id']==1
    raw['first_ready_unit_id']=None
    assert public_player(raw)['first_ready_unit_id'] is None
    assert 'first_ready_unit_checked' not in public_player(raw)


@pytest.mark.parametrize("bad", [1, "true", None])
def test_visibility_must_be_boolean(bad):
    with pytest.raises(PolicyError):
        public_map(envelope(tiles=[{"x": 1, "y": 2, "visible": bad, "revealed": True}]))


def test_inconsistent_flags_fail_closed():
    with pytest.raises(PolicyError):
        public_map(envelope(tiles=[{"x": 1, "y": 2, "visible": True, "revealed": False}]))


@pytest.mark.parametrize("raw", [
    'CIV6FAIR_JSON:{"ok":true,"ok":false}',
    'CIV6FAIR_JSON:{"ok":true,"gold":NaN}',
    'CIV6FAIR_JSON:{"ok":true}\nCIV6FAIR_JSON:{"ok":true}',
    'stack trace with secret state',
])
def test_bad_frames_cannot_pass(raw):
    with pytest.raises(PolicyError) as exc:
        parse_response(raw)
    assert "secret" not in str(exc.value)


def test_parser_accepts_one_valid_envelope():
    raw = envelope()
    assert parse_response("CIV6FAIR_JSON:" + json.dumps(raw) + "\n---END---") == raw
