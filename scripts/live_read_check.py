"""Read-only live smoke check. Never sends act()/gameplay/UI button requests."""
import argparse
import asyncio
import json
from pathlib import Path

from civ6_fair_mcp.service import FairGameService
from civ6_fair_mcp.transport import FireTunerTransport


async def run(extended: bool):
    service = FairGameService(FireTunerTransport())
    results = {}
    try:
        results["status"] = await service.get_game_status()
        results["player"] = await service.get_player_state()
        results["pending_decisions"] = await service.inspect_game("pending_decisions")
        if extended:
            for category in ("governors", "great_people", "government", "religion", "dedications",
                             "diplomacy_sessions", "city_states", "world_congress", "emergencies", "archaeology"):
                results[category] = await service.inspect_game(category)
            units = results["player"].get("units", [])
            if units:
                for category in ("unit_actions", "unit_promotions", "unit_details"):
                    results[category] = await service.inspect_game(category, {"unit_id": units[0]["id"]})
        for value in results.values():
            value.pop("observation_token", None)
        directory = Path(__file__).resolve().parents[1] / "artifacts"
        directory.mkdir(exist_ok=True)
        path = directory / "live-read-check.json"
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        for key, value in results.items():
            print(json.dumps({"query":key, "ok":value.get("ok"), "error":value.get("error"),
                "supported":value.get("supported"),"state_error":value.get("state_error"),
                "ui":value.get("ui"),"items":len(value.get("items", []))},ensure_ascii=False))
        print(str(path))
    finally:
        await service.close()


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extended",action="store_true")
    asyncio.run(run(parser.parse_args().extended))
