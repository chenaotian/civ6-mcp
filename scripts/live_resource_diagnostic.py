"""Read-only runtime compatibility diagnosis, no resource names or amounts."""
import asyncio
import json
import secrets
from civ6_fair_mcp.lua_common import wrap
from civ6_fair_mcp.policy import parse_response
from civ6_fair_mcp.transport import FireTunerTransport


async def main():
    transport = FireTunerTransport()
    try:
        body = '''
out.unpack_type=type(table.unpack)
out.resource_manager_type=type(player.GetResources)
local ok,value=pcall(player.GetResources,player)
out.manager_read=ok
out.visibility_getter=ok and type(value.IsResourceVisible) or "unavailable"
'''
        raw = parse_response(await transport.execute(wrap(body, secrets.token_hex(16))))
        print(json.dumps({k: raw.get(k) for k in ("turn", "unpack_type", "resource_manager_type", "manager_read", "visibility_getter")}))
    finally:
        await transport.close()


if __name__ == "__main__":
    asyncio.run(main())
