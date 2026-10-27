"""Read-only public UI scheduling diagnostics; never reads hidden popup text."""
import asyncio
import json
from pathlib import Path
import secrets
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.transport import FireTunerTransport
from civ6_fair_mcp.policy import parse_response


async def main():
    transport = FireTunerTransport()
    body = '''
out.diagnostic={}
local d=out.diagnostic
for _,name in ipairs({"IsProcessingMessages","IsInGamePlayMode","GetInterfaceMode"}) do
    if UI and type(UI[name])=="function" then
        local ok,value=pcall(UI[name]); if ok and (type(value)=="boolean" or type(value)=="number") then d[name]=value end
    end
end
for _,name in ipairs({"IsPopupQueueDisabled","IsInPopupQueue","IsModal"}) do
    if UIManager and type(UIManager[name])=="function" then
        local ok,value=pcall(UIManager[name],UIManager,ContextPtr)
        if ok and type(value)=="boolean" then d[name]=value end
    end
end
if UI and type(UI.CanShowPopup)=="function" and PopupPriority then
    local ok,value=pcall(UI.CanShowPopup,PopupPriority.Low)
    if ok and type(value)=="boolean" then d.can_show_low_priority=value end
end
if UIManager and type(UIManager.GetModalContexts)=="function" then
    local contexts=UIManager:GetModalContexts()
    d.modal_contexts=array({})
    if type(contexts)=="table" then
        for _,c in pairs(contexts) do
            local entry={kind=type(c)}
            if (type(c)=="table" or type(c)=="userdata") and type(c.IsVisible)=="function" then
                entry.visible=c:IsVisible()==true
                if entry.visible and type(c.GetID)=="function" then entry.id=c:GetID() end
            end
            table.insert(d.modal_contexts,entry)
        end
    end
end
'''
    try:
        value = parse_response(await transport.execute(wrap(body, secrets.token_hex(16))))
        value.pop("session", None)
        print(json.dumps(value, ensure_ascii=False))
        path = Path(__file__).resolve().parents[1] / "artifacts" / "overnight-test" / "ui-diagnostic.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        await transport.close()


asyncio.run(main())
