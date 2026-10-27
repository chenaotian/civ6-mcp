"""Registry of audited, fixed gameplay capabilities."""
from __future__ import annotations

from .base import ActionSpec, QuerySpec, LUA_HELPERS, lua, validate


def registries() -> tuple[dict[str, ActionSpec], dict[str, QuerySpec]]:
    from . import units, empire, diplomacy_actions, decisions, popups, city_status, resources, neighbors, spy_overview, governor_destinations, movement, district_preview, trade_overview, combat_preview, deal_equalize, special_unit_sites, exploration_frontier, stock_recommendations, empire_status
    actions: dict[str, ActionSpec] = {}
    queries: dict[str, QuerySpec] = {}
    for module in (units, empire, diplomacy_actions, decisions, popups, city_status, resources, neighbors, spy_overview, governor_destinations, movement, district_preview, trade_overview, combat_preview, deal_equalize, special_unit_sites, exploration_frontier, stock_recommendations, empire_status):
        if actions.keys() & module.ACTIONS.keys() or queries.keys() & module.QUERIES.keys():
            raise RuntimeError("duplicate internal capability")
        actions.update(module.ACTIONS)
        queries.update(module.QUERIES)
    if any(spec.turn_mode not in {"turn", "ui", "congress", "diplomacy"} for spec in actions.values()):
        raise RuntimeError("invalid internal action permission mode")
    return actions, queries


def validate_extension_action(action: dict) -> dict:
    actions, _ = registries()
    kind = action.get("type")
    if type(kind) is not str or kind not in actions:
        raise ValueError("invalid action")
    return validate(action, {"type": "enum:" + kind, **actions[kind].fields})


def build_inspection_query(nonce: str, category: str, params: dict) -> str:
    from ..lua_common import wrap
    _, queries = registries()
    if type(category) is not str or category not in queries:
        raise ValueError("invalid category")
    spec = queries[category]
    params = validate(params, spec.fields)
    body = (f'out.category={lua(category)}\nout.supported=true\nout.items=array({{}})\n'
            + LUA_HELPERS + '\nlocal function collect()\n' + spec.body(params)
            + '\nend\ncollect()\n')
    return wrap(body, nonce, shared_context=category == "deal_negotiation")
