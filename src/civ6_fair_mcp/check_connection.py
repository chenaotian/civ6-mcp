"""Read-only connection smoke check. Does not issue game actions or print raw logs."""

import asyncio
import json

from .service import FairGameService
from .transport import FireTunerTransport


async def check() -> int:
    service = FairGameService(FireTunerTransport())
    try:
        state = await service.get_player_state()
        if not state.get("ok"):
            print(json.dumps({"ok": False, "error": "game_unavailable",
                "next_step": "Load a single-player game with Tuner enabled; close FireTuner GUI. "
                "The installed API guards must also be supported."}))
            return 1
        # Counts are strictly own entities. No capability or raw state is printed.
        print(json.dumps({"ok": True, "player_id": state["player_id"],
            "turn": state["turn"], "active_turn": state["active_turn"],
            "own_units": len(state["units"]), "own_cities": len(state["cities"])}))
        return 0
    finally:
        await service.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(check()))
