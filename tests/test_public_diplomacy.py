import copy

import pytest

from civ6_fair_mcp.policy import PolicyError, public_diplomacy


def raw(*civilizations):
    for item in civilizations:
        if item.get("met") is True:
            item.setdefault("alive", True)
    return {"ok": True, "session": "a" * 32, "player_id": 0, "turn": 10,
            "active_turn": True, "civilization_count": 6, "civilizations": list(civilizations)}


def test_unknown_civilization_identities_and_stats_do_not_influence_output():
    a = raw({"id": 1, "met": True, "civilization": "CIVILIZATION_ROME", "gold": 50})
    b = copy.deepcopy(a)
    b["civilizations"].extend([
        {"met": False, "id": 3, "civilization": "CIVILIZATION_GERMANY", "gold": 99999},
        {"met": False, "id": object(), "name": object(), "agendas": object()},
        {"civilization": "CIVILIZATION_JAPAN"}])
    assert public_diplomacy(a) == public_diplomacy(b)
    assert public_diplomacy(b)["civilization_count"] == 6


def test_hidden_agenda_identity_is_not_inspected_or_returned():
    a = raw({"id": 1, "met": True, "agendas": [{"visible": True, "id": "AGENDA_IRON_CROWN"}]})
    b = copy.deepcopy(a)
    b["civilizations"][0]["agendas"].append({"visible": False, "id": object()})
    assert public_diplomacy(a) == public_diplomacy(b)
    assert public_diplomacy(b)["civilizations"][0]["agendas"] == ["AGENDA_IRON_CROWN"]


def test_known_civilization_allowlisted_stats_and_public_victory_only():
    item = {"id": 1, "met": True, "civilization": "CIVILIZATION_ROME", "leader": "LEADER_TRAJAN",
        "gold": 100, "science_per_turn": 15, "culture_per_turn": 12, "military_strength": 200,
        "score": 30, "gold_per_turn": 999, "secret_target": "Beijing", "city_locations": [{"x": 99}],
        "victory": {"science_exoplanet_completed": True, "science_light_years": 5,
            "science_light_years_per_turn": 2, "religion_cities_following": 3,
            "religion_faith_per_turn": 12, "hidden_capital_locations": [{"x": 99}]}}
    out = public_diplomacy(raw(item))["civilizations"][0]
    assert out["gold"] == 100 and out["military_strength"] == 200
    assert "gold_per_turn" not in out and "city_locations" not in out and "secret_target" not in out
    assert out["victory"] == {"science_exoplanet_completed": True, "science_light_years": 5,
        "science_light_years_per_turn": 2, "religion_cities_following": 3, "religion_faith_per_turn": 12}


def test_unlaunched_exoplanet_details_are_not_public():
    item = {"id": 1, "met": True, "victory": {"science_exoplanet_completed": False,
             "science_light_years": 99, "science_light_years_per_turn": 5}}
    assert public_diplomacy(raw(item))["civilizations"][0]["victory"] == {"science_exoplanet_completed": False}


def test_duplicate_known_ids_fail_closed():
    with pytest.raises(PolicyError):
        public_diplomacy(raw({"id": 1, "met": True}, {"id": 1, "met": True}))


def test_counts_never_include_unknown_slot_data():
    data = raw()
    data.update(unknown_ids=[2, 3], unknown_alive=1, unknown_leaders=["LEADER_TRAJAN"])
    assert set(public_diplomacy(data)) == {"ok", "player_id", "turn", "active_turn",
        "civilization_count", "civilizations"}


def test_unallowed_foreign_net_income_is_ignored_before_validation():
    a = raw({"id": 1, "met": True, "gold": 100})
    b = copy.deepcopy(a)
    b["civilizations"][0]["gold_per_turn"] = object()
    assert public_diplomacy(a) == public_diplomacy(b)


def test_unlaunched_exoplanet_hidden_fields_cannot_trigger_errors():
    a = raw({"id": 1, "met": True, "victory": {"science_exoplanet_completed": False}})
    b = copy.deepcopy(a)
    b["civilizations"][0]["victory"].update(science_light_years=object(), science_light_years_per_turn=object())
    assert public_diplomacy(a) == public_diplomacy(b)


def test_dead_known_civilization_has_no_live_statistics():
    a = raw({"id": 1, "met": True, "alive": False, "civilization": "CIVILIZATION_ROME"})
    b = copy.deepcopy(a)
    b["civilizations"][0].update(gold=object(), agendas=object(), victory=object())
    assert public_diplomacy(a) == public_diplomacy(b)
