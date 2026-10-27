"""Bounded read-only diagnosis of own action readiness and UI modal stack."""
import asyncio
import json
import secrets

from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import parse_response
from civ6_fair_mcp.transport import FireTunerTransport
from civ6_fair_mcp.extensions.popups import POPUP_PATHS
from civ6_fair_mcp.extensions.base import lua as lua_literal


async def main():
    paths = [path + "/PopupRoot" for key in ("generic", "diplomacy", "deal", "world_congress")
             for path in POPUP_PATHS[key]]
    body = '''
out.turn_complete=player:IsTurnActiveComplete()
out.processing=UI.IsProcessingMessages()
out.can_end=UI.CanEndTurn()
out.modals=array()
for _,context in pairs(UIManager:GetModalContexts()) do
    if #out.modals>=32 then break end
    local row={}
    for _,method in ipairs({"GetID","IsVisible","IsHidden"}) do
        local ok,value=pcall(function() return context[method](context) end)
        if ok and (type(value)=="boolean" or (type(value)=="string" and #value<256)) then row[method]=value end
    end
    row.ancestors=array()
    local parent=context
    for index=1,12 do
        local ok,next_parent=pcall(function() return parent:GetParent() end)
        if not ok or not next_parent then break end
        parent=next_parent
        local label_ok,label=pcall(function() return parent:GetID() end)
        if label_ok and type(label)=="string" and #label<256 then row.ancestors[#row.ancestors+1]=label end
    end
    row.fixed_matches=array()
    for _,path in ipairs({"/InGame/FakePopups/InGamePopup","/InGame/InGamePopup"}) do
        local candidate=ContextPtr:LookUpControl(path)
        local entry={path=path,exists=candidate~=nil,equal=candidate==context}
        if candidate then
            local ok,value=pcall(UIManager.IsModal,UIManager,candidate)
            if ok and type(value)=="boolean" then entry.modal=value end
        end
        row.fixed_matches[#row.fixed_matches+1]=entry
    end
    out.modals[#out.modals+1]=row
end
out.fixed_roots=array()
for _,path in ipairs(PATHS) do
    local root=ContextPtr:LookUpControl(path)
    if root and type(root.IsVisible)=="function" then
        out.fixed_roots[#out.fixed_roots+1]={path=path,visible=root:IsVisible()}
    end
end
'''.replace("PATHS", lua_literal(paths))
    transport = FireTunerTransport()
    try:
        raw = parse_response(await transport.execute(wrap(body, secrets.token_hex(16))))
        print(json.dumps({k: raw.get(k) for k in ("turn", "active_turn", "turn_complete", "processing", "can_end", "modals", "fixed_roots", "popup_keys")}, ensure_ascii=False))
    finally:
        await transport.close()


if __name__ == "__main__":
    asyncio.run(main())
