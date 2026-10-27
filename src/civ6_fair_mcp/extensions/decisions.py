"""Player notifications, captured-city decisions and fixed narrative UI acknowledgments.

Sources: shipped ActionPanel.lua, NotificationPanel.lua, RazeCity.lua and
each popup's own OnClose button callback. No generic popup/function dispatch.
"""
from .base import ActionSpec, QuerySpec, lua, own_city

_CITY_CHOICES = {"keep": "KEEP", "raze": "RAZE", "liberate_founder": "LIBERATE_FOUNDER",
                 "liberate_previous": "LIBERATE_PREVIOUS_OWNER"}


def city_fate(a):
    return own_city(a["city_id"]) + f'''
local cities = player:GetCities()
if type(cities.GetNextCapturedCity) ~= "function" then return end
local pending = cities:GetNextCapturedCity()
if not pending or pending:GetOwner() ~= me or pending:GetID() ~= city:GetID() then return end
if not CityDestroyDirectives or not CityCommandTypes or not UnitOperationTypes
    or type(CityManager.CanStartCommand) ~= "function" then return end
local flag = CityDestroyDirectives.{_CITY_CHOICES[a['choice']]}
if type(flag) ~= "number" or type(CityCommandTypes.DESTROY) ~= "number" then return end
local p = {{[UnitOperationTypes.PARAM_FLAGS]=flag}}
if CityManager.CanStartCommand(city, CityCommandTypes.DESTROY, p) ~= true then return end
attempt(CityManager.RequestCommand, city, CityCommandTypes.DESTROY, p)
'''


def notification(a):
    return f'''
if not NotificationManager or type(NotificationManager.Find) ~= "function" then return end
local n = NotificationManager.Find(me, {a['notification_id']})
if not n or n:GetPlayerID() ~= me or n:GetID() ~= {a['notification_id']} then return end
if type(n.IsDismissed) ~= "function" then return end
local state_ok, dismissed = pcall(n.IsDismissed, n)
if not state_ok or dismissed ~= false then return end
''' + ('''
if n:CanUserDismiss() ~= true or n:GetEndTurnBlocking() ~= EndTurnBlockingTypes.NO_ENDTURN_BLOCKING then return end
attempt(NotificationManager.Dismiss, me, n:GetID())
''' if a["type"] == "dismiss_notification" else '''
if not LuaEvents or not LuaEvents.ActionPanel_ActivateNotification then return end
attempt(LuaEvents.ActionPanel_ActivateNotification, n)
''')


def pending_query(_):
    # Import lazily: actions validates against this module's registered specs.
    from ..actions import end_turn_readiness_guard
    return '''
local function item(id, name, description, action)
    add_item({id=id, name=name, description=description, action=action, scope="self", owner_id=me})
end
local function can_end_turn_now()
''' + end_turn_readiness_guard() + '''
    return true
end
local ready_ok, ready = pcall(can_end_turn_now)
add_item({id="can_end_turn", value=ready_ok and ready==true, scope="self", owner_id=me,
    description="Normal end-turn preconditions pass at observation time; the action rechecks them before submitting."})
if NotificationManager and type(NotificationManager.GetAllEndTurnBlocking) == "function"
    and EndTurnBlockingTypes and type(EndTurnBlockingTypes.NO_ENDTURN_BLOCKING) == "number" then
    local blockers = NotificationManager.GetAllEndTurnBlocking(me)
    if type(blockers) == "table" then
        for _, code in ipairs(blockers) do
            if code ~= EndTurnBlockingTypes.NO_ENDTURN_BLOCKING then
                local name = "UNKNOWN_BLOCKER"
                for k, v in pairs(EndTurnBlockingTypes) do
                    if v == code and type(k) == "string" then name=k; break end
                end
                item("blocker:"..tostring(code), name, "Resolve the matching gameplay decision; no force end-turn.")
            end
        end
    end
else out.supported = false end
local seen = {}
local function add_notification(n)
    if not n or n:GetPlayerID() ~= me then return end
    -- FindType may retain an already dismissed core object. ActionPanel
    -- (454-455, 699-700) checks IsDismissed after FindType before showing it.
    -- Unknown state hides just this notification, never all other decisions.
    if type(n.IsDismissed) ~= "function" then return end
    local state_ok, dismissed = pcall(n.IsDismissed, n)
    if not state_ok or dismissed ~= false then return end
    local id = n:GetID()
    if seen[id] then return end
    if n:GetEndTurnBlocking() == EndTurnBlockingTypes.NO_ENDTURN_BLOCKING
        and n:IsIconDisplayable() ~= true then return end
    seen[id] = true
    local message, summary = n:GetMessage(), n:GetSummary()
    if Locale and type(Locale.Lookup) == "function" then
        message, summary = Locale.Lookup(message), Locale.Lookup(summary)
    end
    item("notification:"..tostring(id), message, summary, {type="activate_notification", notification_id=id})
    if n:CanUserDismiss() == true and n:GetEndTurnBlocking() == EndTurnBlockingTypes.NO_ENDTURN_BLOCKING then
        item("dismiss:"..tostring(id), "Dismiss notification", nil, {type="dismiss_notification", notification_id=id})
    end
end
if NotificationManager and type(NotificationManager.FindType) == "function" and GameInfo.Notifications
    and EndTurnBlockingTypes and type(EndTurnBlockingTypes.NO_ENDTURN_BLOCKING) == "number" then
    local n=0
    for row in GameInfo.Notifications() do
        n=n+1; if n>1024 then error("unavailable") end
        add_notification(NotificationManager.FindType(row.Hash, me))
    end
end
local cities = player:GetCities()
if type(cities.GetNextCapturedCity) == "function" then
    local city = cities:GetNextCapturedCity()
    if city and city:GetOwner() == me and CityDestroyDirectives and CityCommandTypes
        and UnitOperationTypes and type(CityManager.CanStartCommand) == "function" then
''' + "\n".join(f'''
        if type(CityDestroyDirectives.{flag}) == "number"
            and CityManager.CanStartCommand(city, CityCommandTypes.DESTROY,
                {{[UnitOperationTypes.PARAM_FLAGS]=CityDestroyDirectives.{flag}}}) == true then
            item("city_fate:{name}:"..tostring(city:GetID()), city:GetName(), {lua(name)},
                 {{type="city_fate", city_id=city:GetID(), choice={lua(name)}}})
        end
''' for name, flag in _CITY_CHOICES.items()) + '''
    end
end
'''


ACTIONS = {
    "city_fate": ActionSpec({"city_id": "id", "choice": "enum:" + "|".join(_CITY_CHOICES)}, city_fate,
                             "Resolve the next captured city's keep, raze or liberation decision."),
    "dismiss_notification": ActionSpec({"notification_id": "id"}, notification,
                                       "Dismiss own user-dismissible, nonblocking notification."),
    "activate_notification": ActionSpec({"notification_id": "id"}, notification,
                                        "Open own notification's normal UI handler."),
}
QUERIES = {"pending_decisions": QuerySpec({}, pending_query,
    "Current turn blockers, own notification summaries, captured city choices and visible informational popups.")}
