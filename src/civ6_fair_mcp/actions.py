"""Fixed, player-authorized requests; never expose Lua or target diagnostics.

The signatures are checked against the installed Base/Assets/UI source
(Civ6Common, ResearchChooser, CivicsChooser, ProductionPanel, UnitPanel,
ActionPanel). Runtime integration still needs an active Civilization VI game.
An accepted action means an invocation
was attempted, not that the engine completed it or considered its target valid.
"""

from __future__ import annotations

import re
from typing import Any

from .lua_common import wrap
from .research_options import RESEARCH_OPTION_HELPERS
from .extensions import registries, validate_extension_action
from .extensions.base import LUA_HELPERS
from .extensions.base import lua as lua_literal


_FIELDS = {
    "move": frozenset({"type", "unit_id", "x", "y"}),
    "fortify": frozenset({"type", "unit_id"}),
    "found_city": frozenset({"type", "unit_id"}),
    "build_improvement": frozenset({"type", "unit_id", "improvement"}),
    "set_research": frozenset({"type", "technology"}),
    "set_civic": frozenset({"type", "civic"}),
    "set_production": frozenset({"type", "city_id", "item"}),
    "end_turn": frozenset({"type"}),
}
LEGACY_ACTIONS = frozenset(_FIELDS)
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z", re.ASCII)
_SESSION = re.compile(r"[A-Za-z0-9_.:-]{1,256}\Z", re.ASCII)
_PRODUCTION = {
    "UNIT": ("Units", "UnitType", "PARAM_UNIT_TYPE", "unit"),
    "BUILDING": ("Buildings", "BuildingType", "PARAM_BUILDING_TYPE", "building"),
    "PROJECT": ("Projects", "ProjectType", "PARAM_PROJECT_TYPE", "project"),
}


def _integer(value: Any, maximum: int = 2_147_483_647) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid action")
    return value


def _identifier(value: Any, prefixes: tuple[str, ...]) -> str:
    if (type(value) is not str or not _IDENTIFIER.fullmatch(value)
            or not value.startswith(prefixes)):
        raise ValueError("invalid action")
    return value


def validate_action(action: dict) -> dict:
    """Reject coercions, extra keys, nested payloads, Lua and unsupported actions."""
    if type(action) is not dict or type(action.get("type")) is not str:
        raise ValueError("invalid action")
    kind = action["type"]
    if kind not in LEGACY_ACTIONS:
        return validate_extension_action(action)
    if action.keys() != _FIELDS[kind]:
        raise ValueError("invalid action")
    result = dict(action)
    for key in ("unit_id", "city_id"):
        if key in result:
            _integer(result[key])
    for key in ("x", "y"):
        if key in result:
            _integer(result[key], 65535)
    for key, prefixes in (
        ("technology", ("TECH_",)), ("civic", ("CIVIC_",)),
        ("improvement", ("IMPROVEMENT_",)),
        ("item", ("UNIT_", "BUILDING_", "PROJECT_")),
    ):
        if key in result:
            _identifier(result[key], prefixes)
    return result


def _entity(collection: str, variable: str, entity_id: int) -> str:
    # Iterate only the current player's own collection. Do not truncate packed
    # IDs: modulo arithmetic can silently address a different entity.
    return f"""
local {variable} = nil
local examined = 0
for _, candidate in player:Get{collection}():Members() do
    examined = examined + 1
    if examined > 4096 then return end
    if candidate:GetOwner() == me and candidate:GetID() == {entity_id} then
        {variable} = candidate
        break
    end
end
if {variable} == nil then return end
"""


_UNIT_READY = """
if type(Game.IsAllowTacticalCommands) ~= "function"
    or Game.IsAllowTacticalCommands(me) ~= true then return end
if not UnitManager or type(UnitManager.RequestOperation) ~= "function" then return end
if unit:GetMovesRemaining() <= 0 then return end
"""

_VISIBLE_POSITION = """
local ux, uy = unit:GetX(), unit:GetY()
if ux < 0 or uy < 0 or vis:IsVisible(ux, uy) ~= true
    or vis:IsRevealed(ux, uy) ~= true then return end
"""

# Never expose engine return values or exception strings from a submitted
# request: even a Boolean result could otherwise probe an unseen destination.
_ATTEMPT = """
local function attempt(fn, ...)
    pcall(fn, ...)
    out.accepted = true
end
"""

# Read-only preconditions shared by action submission and pending decisions.
# These fragments return from their caller without making an engine request.
_TURN_GUARD = """
if active_turn ~= true then return end
if type(player.IsTurnActiveComplete) ~= "function"
    or player:IsTurnActiveComplete() ~= true then return end
if not UI or type(UI.IsProcessingMessages) ~= "function"
    or UI.IsProcessingMessages() ~= false then return end
-- A popup may appear after the observation. Recheck the native modal stack
-- before submitting an ordinary turn action, without reading modal contents.
if UIManager and type(UIManager.GetModalContexts) == "function" then
    local ok, contexts = pcall(UIManager.GetModalContexts, UIManager)
    if not ok or type(contexts) ~= "table" or next(contexts) ~= nil then return end
end
"""

_END_TURN_GUARD = """
if not UI or type(UI.CanEndTurn) ~= "function" or UI.CanEndTurn() ~= true then return end
if type(UI.RequestAction) ~= "function" then return end
if not ActionTypes or type(ActionTypes.ACTION_ENDTURN) ~= "number" then return end
if not NotificationManager or type(NotificationManager.GetFirstEndTurnBlocking) ~= "function"
    or not EndTurnBlockingTypes or type(EndTurnBlockingTypes.NO_ENDTURN_BLOCKING) ~= "number" then return end
if NotificationManager.GetFirstEndTurnBlocking(me) ~= EndTurnBlockingTypes.NO_ENDTURN_BLOCKING then return end
"""


def _non_ui_modal_guard(kind: str, *, require_capabilities: bool = False) -> str:
    from .extensions.popups import POPUP_PATHS
    paths = [path + "/PopupRoot" for key in ("generic", "diplomacy", "deal", "world_congress")
             for path in POPUP_PATHS[key]]
    choice_popup = {"choose_artifact": "artifact", "spy_escape": "spy_escape",
                    "city_fate": "captured_city", "city_loyalty_choice": "disloyal_city"}.get(kind)
    if choice_popup:
        paths.extend(POPUP_PATHS[choice_popup])
    strict = ('if not ContextPtr or type(ContextPtr.LookUpControl) ~= "function" then return end\n'
              if require_capabilities else "")
    visible_check = ('if root and (type(root.IsVisible) ~= "function" or root:IsVisible() ~= false) then return end'
                     if require_capabilities else
                     'if root and type(root.IsVisible) == "function" and root:IsVisible() == true then return end')
    return strict + f'''
-- A newly opened modal can supersede an otherwise fresh game observation.
-- Never submit underlying gameplay/diplomacy choices through that modal.
if ContextPtr and type(ContextPtr.LookUpControl) == "function" then
    for _, path in ipairs({lua_literal(paths)}) do
        local root = ContextPtr:LookUpControl(path)
        {visible_check}
    end
end
'''


def end_turn_readiness_guard() -> str:
    """Conservative observation check; execution rechecks the same conditions."""
    return '''
if not UIManager or type(UIManager.GetModalContexts) ~= "function" then return end
''' + _TURN_GUARD + _non_ui_modal_guard("end_turn", require_capabilities=True) + _END_TURN_GUARD


_SAFE_PRODUCTION_ROW = """
local function safe_production_row(row)
    return row ~= nil and type(row.Hash) == "number"
        and not row.InternalOnly and not row.MustPurchase
        and not row.RequiresPlacement and not row.IsWonder
end
local function can_produce(queue, row, item_kind)
    if item_kind == "unit" then
        if not MilitaryFormationTypes
            or MilitaryFormationTypes.STANDARD_MILITARY_FORMATION == nil then return false end
        local build = {UnitType=row.Hash,
            MilitaryFormationType=MilitaryFormationTypes.STANDARD_MILITARY_FORMATION}
        return queue:CanProduce(build, true) == true
            and queue:CanProduce(build, false, false) == true
    end
    return queue:CanProduce(row.Hash, true) == true
        and queue:CanProduce(row.Hash, false, false) == true
end
"""


def build_action_query(
    nonce: str,
    action: dict,
    expected_session: str,
    expected_player: int,
    expected_turn: int,
) -> str:
    """Build one non-retryable action, guarded in the same Lua execution block."""
    action = validate_action(action)
    if type(expected_session) is not str or not _SESSION.fullmatch(expected_session):
        raise ValueError("invalid action")
    _integer(expected_player)
    _integer(expected_turn)
    kind = action["type"]
    extensions, _ = registries()
    extension = extensions.get(kind)
    mode = extension.turn_mode if extension else "turn"
    guard = f"""
out.accepted = false
{_ATTEMPT}
local function perform()
if session ~= "{expected_session}" or me ~= {expected_player}
    or turn ~= {expected_turn} then return end
"""
    if mode == "turn":
        guard += _TURN_GUARD
    if mode != "ui":
        guard += _non_ui_modal_guard(kind)
    if extension:
        from .extensions.deal_ui_refresh import DRAFT_ACTIONS, wrap_draft_edit
        extension_body = extension.body(action)
        if kind in DRAFT_ACTIONS:
            extension_body = wrap_draft_edit(action, extension_body)
        return wrap(guard + LUA_HELPERS + extension_body + "\nend\nperform()\n", nonce,
                    shared_context=mode == "ui" or kind == "deal_equalize" or kind in DRAFT_ACTIONS,
                    observation_activity=False)
    body = ""
    if "unit_id" in action:
        body += _entity("Units", "unit", action["unit_id"]) + _UNIT_READY
    if kind == "move":
        # Geometry only: no plot, path, occupancy, combat, target validity, or
        # hidden terrain query. Adjacent unexplored moves are normal exploration.
        body += f"""
local ux, uy = unit:GetX(), unit:GetY()
local width, height = Map.GetGridSize()
if ux < 0 or uy < 0 or {action['x']} >= width or {action['y']} >= height then return end
if Map.GetPlotDistance(ux, uy, {action['x']}, {action['y']}) ~= 1 then return end
if type(UnitOperationTypes.MOVE_TO) ~= "number" or not UnitOperationMoveModifiers
    or UnitOperationMoveModifiers.NONE ~= 0
    or type(UnitOperationMoveModifiers.MOVE_IGNORE_UNEXPLORED_DESTINATION) ~= "number" then return end
local params = {{}}
params[UnitOperationTypes.PARAM_X] = {action['x']}
params[UnitOperationTypes.PARAM_Y] = {action['y']}
-- Use the stock UI's unexplored-destination flag, but never its ATTACK flag.
params[UnitOperationTypes.PARAM_MODIFIERS] = UnitOperationMoveModifiers.NONE
    + UnitOperationMoveModifiers.MOVE_IGNORE_UNEXPLORED_DESTINATION
attempt(UnitManager.RequestOperation, unit, UnitOperationTypes.MOVE_TO, params)
"""
    elif kind in {"fortify", "found_city"}:
        operation = {"fortify": "FORTIFY", "found_city": "FOUND_CITY"}[kind]
        body += _VISIBLE_POSITION + f"""
if type(UnitOperationTypes.{operation}) ~= "number" then return end
if UnitManager.CanStartOperation(unit, UnitOperationTypes.{operation}, nil, false, false) ~= true then return end
attempt(UnitManager.RequestOperation, unit, UnitOperationTypes.{operation})
"""
    elif kind == "build_improvement":
        body += _VISIBLE_POSITION + f"""
local row = GameInfo.Improvements["{action['improvement']}"]
if not row or type(row.Hash) ~= "number" or row.Buildable ~= true then return end
if type(UnitOperationTypes.BUILD_IMPROVEMENT) ~= "number" then return end
local params = {{}}
params[UnitOperationTypes.PARAM_X] = ux
params[UnitOperationTypes.PARAM_Y] = uy
params[UnitOperationTypes.PARAM_IMPROVEMENT_TYPE] = row.Hash
if UnitManager.CanStartOperation(unit, UnitOperationTypes.BUILD_IMPROVEMENT, nil, params, false) ~= true then return end
attempt(UnitManager.RequestOperation, unit, UnitOperationTypes.BUILD_IMPROVEMENT, params)
"""
    elif kind in {"set_research", "set_civic"}:
        if kind == "set_research":
            table, field, getter, check, parameter, operation = (
                "Technologies", "technology", "GetTechs", "CanResearch", "PARAM_TECH_TYPE", "RESEARCH")
        else:
            table, field, getter, check, parameter, operation = (
                "Civics", "civic", "GetCulture", "CanProgress", "PARAM_CIVIC_TYPE", "PROGRESS_CIVIC")
        body += f"""
local row = GameInfo.{table}["{action[field]}"]
if not row or type(row.Hash) ~= "number" or type(row.Index) ~= "number" then return end
if player:{getter}():{check}(row.Index) ~= true then return end
if type(UI.RequestPlayerOperation) ~= "function" then return end
if type(PlayerOperations.{operation}) ~= "number"
    or PlayerOperations.VALUE_EXCLUSIVE == nil then return end
local params = {{}}
params[PlayerOperations.{parameter}] = row.Hash
params[PlayerOperations.PARAM_INSERT_MODE] = PlayerOperations.VALUE_EXCLUSIVE
attempt(UI.RequestPlayerOperation, me, PlayerOperations.{operation}, params)
"""
    elif kind == "set_production":
        table, _, parameter, item_kind = _PRODUCTION[action["item"].split("_", 1)[0]]
        body += _entity("Cities", "city", action["city_id"]) + _SAFE_PRODUCTION_ROW + f"""
local row = GameInfo.{table}["{action['item']}"]
if not safe_production_row(row) then return end
if not can_produce(city:GetBuildQueue(), row, "{item_kind}") then return end
if not CityManager or type(CityManager.RequestOperation) ~= "function" then return end
if type(CityOperationTypes.BUILD) ~= "number"
    or CityOperationTypes.VALUE_EXCLUSIVE == nil then return end
local params = {{}}
params[CityOperationTypes.{parameter}] = row.Hash
params[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
attempt(CityManager.RequestOperation, city, CityOperationTypes.BUILD, params)
"""
    elif kind == "end_turn":
        body += _END_TURN_GUARD + """
attempt(UI.RequestAction, ActionTypes.ACTION_ENDTURN)
"""
    return wrap(guard + body + "\nend\nperform()\n", nonce, observation_activity=False)


def build_options_query(nonce: str, kind: str, entity_id: int | None = None) -> str:
    """Return bounded options offered by the current player's normal UI checks."""
    if type(kind) is not str or kind not in {"research", "civic", "production"}:
        raise ValueError("invalid options")
    if kind == "production":
        _integer(entity_id)
    elif entity_id is not None:
        raise ValueError("invalid options")
    body = f"""
out.kind = "{kind}"
out.options = array({{}})
local function add_option(id, item_kind)
    if type(id) == "string" and #id <= 128 and id:match("^[A-Z][A-Z0-9_]*$") then
        if #out.options >= 512 then error("unavailable") end
        local item={{id = id, kind = item_kind}}
        table.insert(out.options, item)
        return item
    end
end
local function collect()
local examined = 0
"""
    if kind == "production":
        body += f"out.entity_id = {entity_id}\n"
        body += _entity("Cities", "city", entity_id) + _SAFE_PRODUCTION_ROW
        body += "local queue = city:GetBuildQueue()\n"
        for table, field, _, item_kind in _PRODUCTION.values():
            body += f"""
for row in GameInfo.{table}() do
    examined = examined + 1
    if examined > 8192 then error("unavailable") end
    if safe_production_row(row) and can_produce(queue, row, "{item_kind}") then
        add_option(row.{field}, "{item_kind}")
    end
end
"""
    else:
        table, field, getter, check = (
            ("Technologies", "TechnologyType", "GetTechs", "CanResearch")
            if kind == "research" else ("Civics", "CivicType", "GetCulture", "CanProgress"))
        body += RESEARCH_OPTION_HELPERS + f"""
local progress = player:{getter}()
for row in GameInfo.{table}() do
    examined = examined + 1
    if examined > 8192 then error("unavailable") end
    if type(row.Index) == "number" and progress:{check}(row.Index) == true then
        local item=add_option(row.{field}, "{kind}")
        if item then enrich_research_option(item,row,progress,"{kind}") end
    end
end
"""
    return wrap(body + "\nend\ncollect()\n", nonce)


def action_context(action: dict) -> str:
    from .extensions.deal_ui_refresh import DRAFT_ACTIONS, CONTEXT as DEAL_CONTEXT
    if action.get("type") in DRAFT_ACTIONS:
        return DEAL_CONTEXT
    if action.get("type") == "deal_equalize":
        from .extensions.deal_equalize import CONTEXT
        return CONTEXT
    if action.get("type") == "popup_action":
        from .extensions.popups import POPUP_CONTEXTS
        return POPUP_CONTEXTS[action["popup"]]
    return "InGame"


def __getattr__(name: str):
    if name == "ALLOWED_ACTIONS":
        return LEGACY_ACTIONS | registries()[0].keys()
    raise AttributeError(name)
