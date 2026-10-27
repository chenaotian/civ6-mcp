"""Fixed local terminal evidence, without winner identity or observer access."""

RESULT_LUA = r'''
local function local_game_result()
    local alive = player:IsAlive()
    if type(alive) ~= "boolean" then error("unavailable") end
    if alive == false then return "defeated", "local_player_eliminated" end
    if type(Game.GetWinningTeam) == "function" then
        local team = Game.GetWinningTeam()
        -- The stock API uses -1 for no winner. Missing data is not a victory.
        if team ~= nil then
            if type(team) ~= "number" or team % 1 ~= 0 or team < -1 or team > 63 then
                error("unavailable")
            end
            if team >= 0 then
                local own = player:GetTeam()
                if type(own) ~= "number" or own % 1 ~= 0 or own < 0 or own > 63 then
                    error("unavailable")
                end
                return team == own and "victorious" or "finished", "winning_team_confirmed"
            end
        end
    end
    -- EndGameMenu is a fixed player-facing context (including the out-of-time
    -- screen). Do not inspect winner lists, replay graphs, or cached panels.
    if ContextPtr and type(ContextPtr.LookUpControl) == "function" then
        local ok, screen = pcall(ContextPtr.LookUpControl, ContextPtr, "/InGame/EndGameMenu")
        if ok and screen and type(screen.IsVisible) == "function" then
            local visible_ok, visible = pcall(screen.IsVisible, screen)
            if visible_ok and visible == true then return "finished", "end_game_screen_visible" end
        end
    end
    return "playing", nil
end
out.game_status, out.status_reason = local_game_result()
'''

TERMINAL_STATUSES = frozenset({"defeated", "victorious", "finished"})
STATUS_REASONS = frozenset({"local_player_eliminated", "winning_team_confirmed", "end_game_screen_visible"})
