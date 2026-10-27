"""Acknowledge the own envoy reminder without spending an envoy.

Base/Assets/UI/PartialScreens/CityStates.lua:441-457 (Close) calls the own
influence object's SetGivingTokensConsidered(true). Expansion 1/2 inherit it.
The menu enables envoy allocation with CanGiveInfluence and positive tokens
(1424-1431). This fixed acknowledgment deliberately has no foreign target.
"""


ENVOY_DEFER_HELPERS = r'''
local function unconsidered_envoys()
    if not Game or type(Game.IsAllowStrategicCommands)~="function"
        or Game.IsAllowStrategicCommands(me)~=true
        or type(player.GetInfluence)~="function" then return nil end
    local ok,influence=pcall(player.GetInfluence,player)
    if not ok or (type(influence)~="table" and type(influence)~="userdata") then return nil end
    for _,method in ipairs({"CanGiveInfluence","GetTokensToGive",
            "IsGivingTokensConsidered","SetGivingTokensConsidered"}) do
        if type(influence[method])~="function" then return nil end
    end
    local checked,eligible=pcall(function()
        if influence:CanGiveInfluence()~=true
            or influence:IsGivingTokensConsidered()~=false then return false end
        local tokens=influence:GetTokensToGive()
        return type(tokens)=="number" and tokens==tokens and tokens<math.huge
            and tokens>0 and tokens==math.floor(tokens)
    end)
    if checked and eligible==true then return influence end
    return nil
end
'''


def defer_envoys(_: dict) -> str:
    return ENVOY_DEFER_HELPERS + '''
local influence=unconsidered_envoys()
if not influence then return end
attempt(influence.SetGivingTokensConsidered,influence,true)
'''
