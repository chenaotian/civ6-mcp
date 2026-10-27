"""Read-only fixed popup ancestor metadata, never hidden text."""
import asyncio
import json
import secrets
from pathlib import Path
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.transport import FireTunerTransport
from civ6_fair_mcp.policy import parse_response


async def main():
    transport = FireTunerTransport()
    try:
        await transport.execute(wrap("", secrets.token_hex(16)))
        script = '''
out.chains={}
local function chain(c)
    local entries=array({})
    for i=1,12 do
        if not c then break end
        local e={kind=type(c)}
        if type(c.GetID)=="function" then e.id=c:GetID() end
        if type(c.IsVisible)=="function" then e.visible=c:IsVisible() end
        table.insert(entries,e)
        if type(c.GetParent)~="function" then break end
        local parent=c:GetParent()
        if parent==c then e.self_parent=true; break end
        c=parent
    end
    return entries
end
out.chains.context=chain(ContextPtr)
out.chains.close=chain(Controls.Close)
if UIManager and type(UIManager.IsInPopupQueue)=="function" then
    out.queued=UIManager:IsInPopupQueue(ContextPtr)
end
'''
        result = parse_response(await transport.execute(wrap(script,secrets.token_hex(16),shared_context=True),context="NaturalDisasterPopup"))
        result.pop("session",None)
        print(json.dumps(result,ensure_ascii=False))
        (Path(__file__).resolve().parents[1]/"artifacts"/"overnight-test"/"popup-path-diagnostic.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    finally:
        await transport.close()


asyncio.run(main())
