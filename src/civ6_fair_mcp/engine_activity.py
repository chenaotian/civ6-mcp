"""Fixed UI activity hint; never an action permission or completion receipt.

Stock ActionPanel.lua:152,541 uses IsProcessingMessages, and
WorldInput.lua:884 / UnitPanel.lua:3892 use IsGameCoreBusy to defer UI work.
Only these two Boolean UI signals are sampled, with no game-state traversal.
"""

ACTIVITY_LUA = r'''
do
    local function read_activity_flag(name)
        local ok, value = pcall(function()
            if not UI or type(UI[name]) ~= "function" then return nil end
            return UI[name]()
        end)
        if not ok or type(value) ~= "boolean" then return nil end
        return value
    end
    local core_busy = read_activity_flag("IsGameCoreBusy")
    local processing = read_activity_flag("IsProcessingMessages")
    if core_busy == true or processing == true then
        out.engine_activity = "busy"
    elseif core_busy == false and processing == false then
        out.engine_activity = "idle"
    else
        out.engine_activity = "unknown"
    end
end
'''


def combine_engine_activity(*values: object) -> str:
    """Project only the fixed enum and conservatively combine completed reads."""
    states = [value if type(value) is str and value in {"busy", "idle", "unknown"}
              else "unknown" for value in values]
    if "busy" in states:
        return "busy"
    if states and all(value == "idle" for value in states):
        return "idle"
    return "unknown"
