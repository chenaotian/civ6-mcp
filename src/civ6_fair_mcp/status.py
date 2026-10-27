"""Minimal terminal-state read; a defeated agent never gets observer/world access."""
from .lua_common import wrap
from .policy import PolicyError, envelope
from .game_result import RESULT_LUA, STATUS_REASONS


def build_status_query(nonce: str) -> str:
    return wrap(RESULT_LUA + '\nout.status = out.game_status\n', nonce, status_only=True)


def public_status(raw: dict) -> dict:
    _, me, turn, active = envelope(raw)
    status = raw.get("status")
    if status not in {"playing", "defeated", "victorious", "finished"}:
        raise PolicyError("invalid_response")
    result = {"ok": True, "player_id": me, "turn": turn, "active_turn": active, "status": status}
    if "status_reason" in raw:
        if raw["status_reason"] not in STATUS_REASONS or status == "playing":
            raise PolicyError("invalid_response")
        result["status_reason"] = raw["status_reason"]
    return result
