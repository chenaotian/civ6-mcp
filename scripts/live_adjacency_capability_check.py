"""Fixed-context, read-only adjacency UI capability probe.

Close the normal game client first. This script makes one local connection and
reads only authored API types and an exact context-ID equality check. It does
not install observers, invoke rendering/placement, traverse controls, read
labels/plots, or issue operations. No production transport whitelist is edited.

The first live run verified the context but an earlier _G-based probe reported
all nil. That result was inconclusive because the UI's globals are isolated.
The current probe uses fixed direct expressions; no API absence is inferred
from the earlier run and no observer is installed by either version.
"""
from __future__ import annotations

import asyncio
import json

import civ6_fair_mcp.transport as transport_module
from civ6_fair_mcp.extensions.base import lua


CONTEXT = "DistrictPlotIconManager"
CAPABILITY_PATHS = (
    "GetInstanceAt", "Realize2dArtForCityDistricts", "ClearEveything",
    "ContextPtr.GetID", "ContextPtr.IsVisible", "ContextPtr.GetParent",
    "Controls.PlotBonusContainer", "Controls.PlotBonusContainer.IsVisible",
    "Controls.PlotBonusContainer.GetParent", "Controls.PlotBonusContainer.GetChildren",
    "UI.GetHeadSelectedCity", "UI.GetInterfaceMode", "UI.GetInterfaceModeParameter",
    "UI.SelectCity", "UI.SetInterfaceMode", "UILens.CreateLensLayerHash", "UILens.IsLayerOn",
    "CityOperationTypes.PARAM_DISTRICT_TYPE", "InterfaceModeTypes.DISTRICT_PLACEMENT",
    "InterfaceModeTypes.SELECTION", "LuaEvents.CityPanel_ProductionClose",
    "Events.InterfaceModeChanged.Add", "Events.CitySelectionChanged.Add",
    "Events.LensLayerOff.Add", "Events.LoadGameViewStateDone.Add",
    "Events.LocalPlayerChanged.Add", "ExposedMembers.Civ6FairState",
)
_TYPES = frozenset({"nil", "boolean", "number", "string", "table", "function", "userdata", "thread", "unavailable"})


def build_probe() -> str:
    # No shared-state bootstrap or event registration: even a fresh client can
    # check capabilities without installing any hooks in the game UI.
    # Fixed source expressions also avoid relying on _G/rawget/debug, which
    # are not guaranteed to exist in the game's restricted Lua contexts.
    checks = "{" + ",".join("{" + lua(path) + ",function() return type(" + path + ") end}"
                             for path in CAPABILITY_PATHS) + "}"
    return r'''
do
local permitted,authorized=pcall(function()
    if GameConfiguration.IsAnyMultiplayer()~=false or GameConfiguration.IsHotseat()~=false
        or GameConfiguration.IsWorldBuilderEditor()~=false or Automation.IsActive()~=false then return false end
    local me=Game.GetLocalPlayer()
    if type(me)~='number' or me%1~=0 or me<0 or Game.GetLocalObserver()~=me then return false end
    local player=Players[me]
    return player~=nil and player:IsAlive()==true and player:IsHuman()==true
end)
local payload='{"ok":false,"error":"capability_probe_unavailable"}'
if permitted and authorized==true then
    local identity_ok,identity=pcall(function() return ContextPtr:GetID() end)
    local verified=identity_ok and (identity==''' + lua(CONTEXT) + " or identity==" + lua(CONTEXT + ".xml") + r''')
    if verified then
        local fields={}
        for _,check in ipairs(''' + checks + r''') do
            local path=check[1]
            local ok,kind=pcall(check[2])
            if not ok then kind='unavailable' end
            -- Authored ASCII paths and Lua type names require no dynamic text
            -- serialization. Never include the value, name, or engine error.
            fields[#fields+1]='"'..path..'":"'..kind..'"'
        end
        payload='{"ok":true,"context_verified":true,"types":{'..table.concat(fields,',')..'}}'
    else payload='{"ok":false,"error":"fixed_context_not_verified"}' end
end
print('CIV6FAIR_JSON:'..payload)
print('---END---')
end
'''


def project(response: str) -> dict:
    frames = [line.removeprefix("CIV6FAIR_JSON:") for line in response.splitlines()
              if line.startswith("CIV6FAIR_JSON:")]
    if len(frames) != 1:
        raise ValueError("invalid capability response")
    raw = json.loads(frames[0])
    if type(raw) is not dict or raw.get("ok") is not True:
        return {"ok": False, "error": "capability_probe_unavailable"}
    kinds = raw.get("types")
    if raw.get("context_verified") is not True or type(kinds) is not dict or set(kinds) != set(CAPABILITY_PATHS):
        raise ValueError("invalid capability response")
    if any(type(value) is not str or value not in _TYPES for value in kinds.values()):
        raise ValueError("invalid capability response")
    return {"ok": True, "context_verified": True, "types": kinds}


async def run() -> dict:
    original = transport_module._CONTEXTS
    # Process-local extension for this single fixed context only. The package
    # file and the ordinary MCP tool's context surface remain unchanged.
    transport_module._CONTEXTS = frozenset((*original, CONTEXT))
    client = transport_module.FireTunerTransport()
    try:
        response = await client.execute(build_probe(), context=CONTEXT)
        return project(response)
    except Exception:
        # Diagnostics must never print engine output, context inventories,
        # connection addresses, Lua source, or exception text.
        return {"ok": False, "error": "capability_probe_unavailable"}
    finally:
        try:
            await client.close()
        finally:
            transport_module._CONTEXTS = original


if __name__ == "__main__":
    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    raise SystemExit(0 if result["ok"] else 1)
