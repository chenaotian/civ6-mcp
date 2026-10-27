"""Read-only diagnosis of the existing own-player snapshot; no foreign reads."""
import asyncio
import json
import secrets

from civ6_fair_mcp.queries import build_player_query
from civ6_fair_mcp.transport import FireTunerTransport
from civ6_fair_mcp.policy import (parse_response, public_player, _project,
    PLAYER_FIELDS, CITY_FIELDS, UNIT_FIELDS)


async def main():
    transport = FireTunerTransport()
    try:
        response = await transport.execute(build_player_query(secrets.token_hex(16)))
        try:
            raw = parse_response(response)
        except Exception as error:
            print(json.dumps({"stage": "parse", "error": type(error).__name__}))
            return
        try:
            public_player(raw)
            print(json.dumps({"stage": "projection", "ok": True}))
        except Exception as error:
            print(json.dumps({"stage": "projection", "error": type(error).__name__}))
            me = raw["player_id"]
            for kind, entities, fields in (
                ("player", [raw.get("player", {})], PLAYER_FIELDS),
                ("cities", raw.get("cities", []), CITY_FIELDS),
                ("units", raw.get("units", []), UNIT_FIELDS),
            ):
                for entity in entities:
                    if kind != "player" and entity.get("owner_id") != me:
                        continue
                    for field, value in entity.items():
                        if field not in fields:
                            continue
                        try:
                            _project({field: value}, {field: fields[field]})
                        except Exception:
                            print(json.dumps({"kind": kind, "id": entity.get("id"),
                                "field": field, "value": value}, ensure_ascii=False))
    finally:
        await transport.close()


if __name__ == "__main__":
    asyncio.run(main())
