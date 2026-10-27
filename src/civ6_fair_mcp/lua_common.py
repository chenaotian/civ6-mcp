"""Fixed Lua envelope, controller checks, ephemeral session, and JSON encoding.

This module is an internal code generator, never an MCP tool. Only authored
templates may supply ``body``. Missing engine capabilities fail closed.
"""

from __future__ import annotations

import re

from .engine_activity import ACTIVITY_LUA

_NONCE = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")

_PREFIX = r'''
do
local array_marker = {}
local function array(value)
    return setmetatable(value or {}, array_marker)
end
local function quote(value)
    return '"' .. value:gsub('[%z\1-\31\\"]', function(c)
        if c == '"' then return '\\"' end
        if c == '\\' then return '\\\\' end
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
local function encode(value, seen, depth)
    if depth > 16 then error('unavailable') end
    local kind = type(value)
    if kind == 'nil' then return 'null' end
    if kind == 'boolean' then return value and 'true' or 'false' end
    if kind == 'number' then
        if value ~= value or value == math.huge or value == -math.huge then
            error('unavailable')
        end
        return tostring(value)
    end
    if kind == 'string' then return quote(value) end
    if kind ~= 'table' or seen[value] then error('unavailable') end
    seen[value] = true
    local pieces = {}
    if getmetatable(value) == array_marker then
        local length = #value
        for key in pairs(value) do
            if type(key) ~= 'number' or key % 1 ~= 0 or key < 1 or key > length then
                error('unavailable')
            end
        end
        for index = 1, length do
            pieces[#pieces + 1] = encode(value[index], seen, depth + 1)
        end
        seen[value] = nil
        return '[' .. table.concat(pieces, ',') .. ']'
    end
    for key, item in pairs(value) do
        if type(key) ~= 'string' then error('unavailable') end
        pieces[#pieces + 1] = quote(key) .. ':' .. encode(item, seen, depth + 1)
    end
    seen[value] = nil
    return '{' .. table.concat(pieces, ',') .. '}'
end
local success, result = pcall(function()
    -- Never fall back to a selected player, observer, autoplay, or player zero.
    if GameConfiguration.IsAnyMultiplayer() ~= false or
       GameConfiguration.IsHotseat() ~= false or
       GameConfiguration.IsWorldBuilderEditor() ~= false then error('unavailable') end
    if Automation.IsActive() ~= false then error('unavailable') end
    local me = Game.GetLocalPlayer()
    if type(me) ~= 'number' or me % 1 ~= 0 or me < 0 then error('unavailable') end
    if Game.GetLocalObserver() ~= me then error('unavailable') end
    local player = Players[me]
    if player == nil or player:IsAlive() ~= true or player:IsHuman() ~= true then
        error('unavailable')
    end
    local vis = PlayersVisibility[me]
    if vis == nil or type(vis.IsRevealed) ~= 'function' or
       type(vis.IsVisible) ~= 'function' then error('unavailable') end
    local turn = Game.GetCurrentGameTurn()
    if type(turn) ~= 'number' or turn % 1 ~= 0 or turn < 0 then error('unavailable') end
    local active_turn = player:IsTurnActive()
    local turn_ready = player:IsTurnActiveComplete()
    local processing = UI.IsProcessingMessages()
    if type(active_turn) ~= 'boolean' or type(turn_ready) ~= 'boolean' or
       type(processing) ~= 'boolean' then error('unavailable') end
    active_turn = active_turn and turn_ready and not processing

    -- InGame-only state, deliberately never stored in save data or on disk.
    -- Required reset events invalidate tokens even when loading the same turn.
    if Events == nil or Events.LoadGameViewStateDone == nil or
       type(Events.LoadGameViewStateDone.Add) ~= 'function' or
       Events.LocalPlayerChanged == nil or
       type(Events.LocalPlayerChanged.Add) ~= 'function' then
        error('unavailable')
    end
    local state = _CIV6FAIR_V1
    if state == nil then
        state = {}
        _CIV6FAIR_V1 = state
    end
    if type(state) ~= 'table' then error('unavailable') end
    -- Share only gateway authorization state with fixed informational popup
    -- contexts. No world objects or queried data are stored here.
    if ExposedMembers then ExposedMembers.Civ6FairState = state end
    if not state.hooks then
        local function invalidate()
            state.session = nil
            state.last_turn = nil
            state.player_id = nil
            state.diplomacy_statements = nil
            state.diplomacy_session = nil
            state.deal_actions = nil
        end
        Events.LoadGameViewStateDone.Add(invalidate)
        Events.LocalPlayerChanged.Add(invalidate)
        state.hooks = true
    end
    if state.player_id ~= me or (state.last_turn ~= nil and turn < state.last_turn) then
        state.session = nil
    end
    if state.session == nil then state.session = '__NONCE__' end
    state.player_id = me
    state.last_turn = turn
    local session = state.session
    local out = {ok=true, session=session, player_id=me, turn=turn, active_turn=active_turn}
'''

_SUFFIX = r'''
    return out
end)
local payload = '{"ok":false,"error":"unavailable"}'
if success then
    local encoded, candidate = pcall(encode, result, {}, 0)
    if encoded then payload = candidate end
end
-- Never print the pcall error: engine errors can contain privileged state.
print('CIV6FAIR_JSON:' .. payload)
print('---END---')
end
'''


def wrap(body: str, nonce: str, *, shared_context: bool = False, status_only: bool = False,
         observation_activity: bool = True, discover_ui: bool = True) -> str:
    """Wrap an authored template in permission checks and one JSON result.

    ``nonce`` must be fresh for each generated request. It becomes a new session
    only after an InGame reload/player change/reset; existing sessions retain it.
    Body locals: me, player, vis, turn, active_turn, session, out, array.
    """
    if not isinstance(body, str) or not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
        raise ValueError("Invalid internal template input")
    prefix = _PREFIX
    if status_only:
        # Only the fixed terminal-status builder may use this. It never reads
        # world objects, and the service never issues an action token from it.
        prefix = prefix.replace("player:IsAlive() ~= true or ", "")
        # A local terminal read uses neither map visibility nor active-turn
        # readiness. Those APIs may disappear after elimination. Missing turn
        # readiness can never create a capability, even for a playing result.
        start = prefix.index("    local vis = PlayersVisibility[me]")
        end = prefix.index("    local turn = Game.GetCurrentGameTurn()", start)
        prefix = prefix[:start] + "    local vis = nil\n" + prefix[end:]
        start = prefix.index("    local active_turn = player:IsTurnActive()")
        end = prefix.index("\n\n    -- InGame-only state", start)
        prefix = prefix[:start] + '''    local active_turn = false
    local ready_ok, ready = pcall(function()
        return player:IsTurnActive() == true and player:IsTurnActiveComplete() == true
            and UI.IsProcessingMessages() == false
    end)
    active_turn = ready_ok and ready == true
''' + prefix[end:]
    if shared_context:
        prefix = prefix.replace("local state = _CIV6FAIR_V1", "local state = ExposedMembers and ExposedMembers.Civ6FairState\n    if state == nil then error('unavailable') end")
    hook = ""
    if not shared_context and not status_only:
        from .extensions.diplomacy_actions import DIPLOMACY_HOOK
        hook = DIPLOMACY_HOOK
    discovery = ""
    if not shared_context and discover_ui:
        from .extensions.popups import discovery_lua
        discovery = '''
if out.game_status ~= "defeated" and out.game_status ~= "victorious" and out.game_status ~= "finished"
    and player:IsAlive() == true and ContextPtr and type(ContextPtr.LookUpControl) == "function" then
out.ui_monitor_available = true
''' + discovery_lua() + '''
out.turn_blockers = array({})
if NotificationManager and type(NotificationManager.GetAllEndTurnBlocking) == "function" and EndTurnBlockingTypes then
    local blockers = NotificationManager.GetAllEndTurnBlocking(me)
    if type(blockers) == "table" then
        for _, code in ipairs(blockers) do
            if code ~= EndTurnBlockingTypes.NO_ENDTURN_BLOCKING then
                local name = "UNKNOWN_BLOCKER"
                for key, value in pairs(EndTurnBlockingTypes) do
                    if value == code and type(key) == "string" then name = key; break end
                end
                table.insert(out.turn_blockers, name)
                if #out.turn_blockers > 128 then error("unavailable") end
            end
        end
    end
end
end
'''
    # Action replies remain uniform; no post-request activity/timing hint.
    activity = ACTIVITY_LUA if observation_activity else ""
    terminal = ""
    if observation_activity and not shared_context and not status_only:
        from .game_result import RESULT_LUA
        terminal = RESULT_LUA
    return (prefix.replace("__NONCE__", nonce) + "\n" + hook + "\n" + body
            + "\n" + terminal + "\n" + discovery + "\n" + activity + "\n" + _SUFFIX)
