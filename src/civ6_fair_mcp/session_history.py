"""Small in-memory observation/submission diary; never a game-state oracle."""
from collections import deque
from copy import deepcopy


class SessionHistory:
    def __init__(self):
        self._entries = deque(maxlen=64)
        self._identity = None
        self._last_turn = None

    def clear(self):
        self._entries.clear()
        self._identity = None
        self._last_turn = None

    def _check(self, session, player, turn, generation):
        identity = (session, player, generation)
        if self._identity != identity or (self._last_turn is not None and turn < self._last_turn):
            self.clear()
        self._identity = identity
        self._last_turn = turn

    def observe(self, request, baseline, public):
        self._check(baseline.session, baseline.player_id, baseline.turn, baseline.generation)
        item = {"kind": "observation", "read": request.kind, "turn": baseline.turn,
                "active_turn": public.get("active_turn")}
        if request.kind == "inspection":
            item["category"] = request.args[0]
        if "status" in public:
            item["status"] = public["status"]
        if public.get("game_state_available") is False:
            item["game_state_available"] = False
        if request.kind == "player" and public.get("game_state_available") is not False:
            for name in ("units", "cities"):
                if name in public:
                    item[f"own_{name}_count"] = len(public[name])
            if "player" in public:
                item["economy"] = {key: public["player"][key] for key in ("gold", "faith", "research", "civic")
                                   if key in public["player"]}
        ui = public.get("ui")
        if isinstance(ui, dict):
            item["ui"] = {key: deepcopy(ui[key]) for key in ("status", "engine_activity", "turn_blockers") if key in ui}
            item["ui"]["popup_ids"] = [p["id"] for p in ui.get("popups", [])]
        if not self._entries or self._entries[-1] != item:
            self._entries.append(item)

    def submitted(self, observation, action_type, accepted):
        self._check(observation.session, observation.player_id, observation.turn, observation.generation)
        self._entries.append({"kind": "action_request", "turn": observation.turn,
            "action_type": action_type, "accepted": accepted,
            "status": "submitted" if accepted else "rejected", "completion": "not_asserted"})

    def read(self, generation, limit):
        if type(limit) is not int or not 1 <= limit <= 64:
            return {"ok": False, "error": "invalid_input"}
        if self._identity is not None and self._identity[2] != generation:
            self.clear()
        return {"ok": True, "scope": "current_observed_session_memory", "capacity": 64,
                "entries": deepcopy(list(self._entries)[-limit:]),
                "freshness": "history_only_take_fresh_observation_before_acting"}
