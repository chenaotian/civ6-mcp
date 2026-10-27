"""Serial authorization boundary between MCP and the game connection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import secrets
import time
from typing import Any, Protocol

from .actions import action_context, build_action_query, validate_action
from .engine_activity import combine_engine_activity
from .interaction_feedback import next_steps
from .game_result import TERMINAL_STATUSES
from .session_history import SessionHistory
from .extensions import registries
from .extensions.base import validate
from .policy import PolicyError, envelope, integer, parse_response
from .waiting import ReadBaseline, ReadRequest, prepare_read, remember, wait_for_change


class Transport(Protocol):
    connection_generation: int

    async def execute(self, script: str, context: str = "InGame", *,
                      expected_generation: int | None = None) -> str: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class Observation:
    token: str
    session: str
    player_id: int
    turn: int
    generation: int
    issued_at: float
    mode: str = "turn"
    popup_ids: frozenset[str] = frozenset()


class FairGameService:
    def __init__(self, transport: Transport, token_ttl: float = 120.0):
        self.transport = transport
        self._lock = asyncio.Lock()
        self._observation: Observation | None = None
        self._token_ttl = token_ttl
        self._last_read: ReadBaseline | None = None
        self._history = SessionHistory()
        self._preview_client = secrets.token_hex(16)
        self._preview_generation: int | None = None

    def _preview_identity(self, generation: int) -> str:
        return f"{self._preview_client}:{generation}"

    def _remember(self, request: ReadRequest, raw: dict, public: dict) -> None:
        self._last_read = remember(request, raw, public, self.transport.connection_generation)
        self._history.observe(request, self._last_read, public)

    async def _read_locked(self, request: ReadRequest, *,
                           expected_generation: int | None = None) -> dict:
        """One authored read, shared by public methods and bounded waiting."""
        self._observation = None
        try:
            if request.kind == "inspection" and request.args[0] == "district_preview":
                return await self._read_preview_locked(request, expected_generation=expected_generation)
            if request.kind == "inspection" and request.args[0] == "deal_negotiation":
                return await self._read_deal_negotiation_locked(request, expected_generation=expected_generation)
            script, projector, allowed_mode = prepare_read(request, secrets.token_hex(16))
            raw = parse_response(await self.transport.execute(
                script, expected_generation=expected_generation))
            if raw.get("game_status") in TERMINAL_STATUSES:
                from .status import public_status
                public = public_status({**raw, "status": raw["game_status"]})
                self._remember(request, raw, public)
                return public
            public = projector(raw)
            mode = allowed_mode if allowed_mode and raw.get("decision_mode") == allowed_mode else None
            if request.kind != "status" or public["status"] == "playing":
                public = await self._finish_read(raw, public, decision_mode=mode)
            self._remember(request, raw, public)
            return public
        except Exception:
            if request.kind == "status":
                return await self._unavailable()
            return await self._recover_ui(request, expected_generation=expected_generation)

    async def _read_preview_locked(self, request: ReadRequest, *,
                                   expected_generation: int | None = None) -> dict:
        """Bind fixed-context labels to the ordinary observation/UI envelope."""
        from .extensions.district_preview import CONTEXT, CATEGORY, build_read
        from .inspection_policy import public_inspection
        from .lua_common import wrap
        raw = parse_response(await self.transport.execute(wrap("", secrets.token_hex(16)),
            expected_generation=expected_generation))
        if raw.get("game_status") in TERMINAL_STATUSES:
            from .status import public_status
            public = public_status({**raw, "status": raw["game_status"]})
            self._remember(request, raw, public)
            return public
        identity = envelope(raw)[:3]
        generation = self.transport.connection_generation
        reply = parse_response(await self.transport.execute(
            build_read(secrets.token_hex(16), request.args[1], self._preview_identity(generation)),
            context=CONTEXT, expected_generation=generation))
        if envelope(reply)[:3] != identity:
            raise PolicyError("stale_observation")
        public = public_inspection(reply, CATEGORY)
        raw = {**raw, "active_turn": raw["active_turn"] and reply["active_turn"],
               "engine_activity": combine_engine_activity(raw.get("engine_activity"),
                                                          reply.get("engine_activity"))}
        public["active_turn"] = raw["active_turn"]
        public = await self._finish_read(raw, public)
        self._remember(request, raw, public)
        return public

    async def _read_deal_negotiation_locked(self, request: ReadRequest, *,
                                           expected_generation: int | None = None) -> dict:
        """Read one fixed stock button in its own context, retaining UI guards."""
        from .extensions import build_inspection_query
        from .extensions.deal_equalize import CONTEXT, CATEGORY
        from .inspection_policy import public_inspection
        from .lua_common import wrap
        raw = parse_response(await self.transport.execute(wrap("", secrets.token_hex(16)),
            expected_generation=expected_generation))
        if raw.get("game_status") in TERMINAL_STATUSES:
            from .status import public_status
            public = public_status({**raw, "status": raw["game_status"]})
            self._remember(request, raw, public)
            return public
        identity = envelope(raw)[:3]
        generation = self.transport.connection_generation
        reply = parse_response(await self.transport.execute(
            build_inspection_query(secrets.token_hex(16), CATEGORY, request.args[1]),
            context=CONTEXT, expected_generation=generation))
        if envelope(reply)[:3] != identity or self.transport.connection_generation != generation:
            raise PolicyError("stale_observation")
        public = public_inspection(reply, CATEGORY)
        raw = {**raw, "active_turn": raw["active_turn"] and reply["active_turn"],
               "engine_activity": combine_engine_activity(raw.get("engine_activity"),
                                                          reply.get("engine_activity"))}
        public["active_turn"] = raw["active_turn"]
        mode = "diplomacy" if reply.get("decision_mode") == "diplomacy" else None
        public = await self._finish_read(raw, public, decision_mode=mode)
        self._remember(request, raw, public)
        return public

    def _issue(self, raw: dict, public: dict, *, decision_mode: str | None = None,
               popup_ids: frozenset[str] = frozenset(), force_ui: bool = False) -> dict:
        session, player, turn, active = envelope(raw)
        self._observation = None
        if active or decision_mode:
            observation = Observation(secrets.token_urlsafe(32), session, player, turn,
                                      self.transport.connection_generation, time.monotonic(),
                                      "ui" if force_ui else "turn" if active else decision_mode, popup_ids)
            self._observation = observation
            public["observation_token"] = observation.token
            if observation.mode != "turn":
                public["token_scope"] = observation.mode
        return public

    async def _finish_read(self, raw: dict, public: dict, *, decision_mode: str | None = None) -> dict:
        """Every production observation includes visible modal text and usable buttons.

        Transport capability distinguishes a real game UI from legacy test/embed
        transports; the shipping FireTuner transport always enables this path.
        All context reads share this service lock and the original connection.
        """
        if raw.get("game_status") in TERMINAL_STATUSES:
            from .status import public_status
            self._observation = None
            return public_status({**raw, "status": raw["game_status"]})
        if not getattr(self.transport, "supports_ui_contexts", False):
            return self._issue(raw, public, decision_mode=decision_mode)
        from .extensions.popups import POPUP_CONTEXTS, build_popup_query
        from .ui_policy import public_popup
        identity = envelope(raw)[:3]
        generation = self.transport.connection_generation
        keys = raw.get("popup_keys")
        if type(keys) is not list or len(keys) > 64 or any(type(k) is not str or k not in POPUP_CONTEXTS for k in keys):
            raise PolicyError("invalid_response")
        native_keys = raw.get("native_modal_keys", [])
        if type(native_keys) is not list or len(native_keys) > 64 or any(
                type(k) is not str or k not in POPUP_CONTEXTS for k in native_keys):
            raise PolicyError("invalid_response")
        for field in ("native_modal_present", "unknown_modal_present", "modal_monitor_available"):
            if field in raw and type(raw[field]) is not bool:
                raise PolicyError("invalid_response")
        popups = []
        unavailable_popups = []
        actionable = set()
        active = raw["active_turn"]
        activity_samples = [raw.get("engine_activity")]
        for key in dict.fromkeys(keys):
            try:
                reply = parse_response(await self.transport.execute(
                    build_popup_query(secrets.token_hex(16), key), context=POPUP_CONTEXTS[key],
                    expected_generation=generation))
            except Exception:
                if self.transport.connection_generation != generation:
                    raise
                # A single unsupported/stale UI context must not conceal other
                # successfully observed prompts. Never return its old buttons.
                unavailable_popups.append(key)
                continue
            if envelope(reply)[:3] != identity:
                raise PolicyError("stale_observation")
            active = active and reply["active_turn"]
            activity_samples.append(reply.get("engine_activity"))
            try:
                popup = public_popup(reply, key)
            except PolicyError:
                unavailable_popups.append(key)
                continue
            if popup is not None:
                popups.append(popup)
                if any("action" in button for button in popup["buttons"]):
                    actionable.add(key)
        blockers = raw.get("turn_blockers", [])
        if type(blockers) is not list or len(blockers) > 128 or any(
                type(item) is not str or len(item) > 128 for item in blockers):
            raise PolicyError("invalid_response")
        public["active_turn"] = active
        public["ui"] = {"status": "popup" if popups else "decision" if blockers else "ready" if active else "waiting",
                        "popups": popups, "turn_blockers": blockers,
                        "engine_activity": combine_engine_activity(*activity_samples)}
        if raw.get("ui_monitor_available") is not True:
            public["ui"]["status"] = "unavailable"
        if unavailable_popups:
            public["ui"]["unavailable_popups"] = unavailable_popups
            public["ui"]["status"] = "partial" if popups else "unavailable"
        # A native modal is an input barrier even if its dynamic instance could
        # not be discovered or its context is outside the fixed manifest. Keep
        # any successfully read prompts, but never invent a close callback or
        # grant an underlying gameplay capability through an unread barrier.
        observed_keys = {popup["id"] for popup in popups}
        unread_native = [key for key in dict.fromkeys(native_keys) if key not in observed_keys]
        modal_unavailable = None
        if raw.get("modal_monitor_available") is False:
            modal_unavailable = "native_modal_state_unavailable"
        elif raw.get("unknown_modal_present") is True:
            modal_unavailable = "unknown_native_modal"
        elif unread_native or (raw.get("native_modal_present") is True and not native_keys):
            modal_unavailable = "native_modal_unreadable"
        if modal_unavailable:
            public["ui"]["status"] = "partial" if popups else "unavailable"
            public["ui"]["modal_unavailable_reason"] = modal_unavailable
            if raw.get("unknown_modal_present") is True:
                public["ui"]["unknown_modal_present"] = True
            if unread_native:
                public["ui"]["unavailable_popups"] = list(dict.fromkeys(unavailable_popups + unread_native))
            self._observation = None
            public["ui"]["next_steps"] = next_steps(public["ui"])
            return public
        public["ui"]["next_steps"] = next_steps(public["ui"])
        return self._issue({**raw, "active_turn": active}, public,
                           decision_mode=decision_mode or ("ui" if actionable else None),
                           popup_ids=frozenset(actionable),
                           force_ui=raw.get("native_modal_present") is True
                           or any(p["modal"] and p["interactive"] for p in popups))

    async def _recover_ui(self, request: ReadRequest | None = None, *,
                          expected_generation: int | None = None) -> dict:
        """A failed world query must not conceal a perfectly readable blocking popup."""
        if not getattr(self.transport, "supports_ui_contexts", False):
            return await self._unavailable()
        from .lua_common import wrap
        try:
            raw = parse_response(await self.transport.execute(wrap("", secrets.token_hex(16)),
                expected_generation=expected_generation))
            result = await self._finish_read(raw, {"ok": True, "player_id": raw["player_id"],
                "turn": raw["turn"], "active_turn": raw["active_turn"], "game_state_available": False,
                "state_error": "state_query_unavailable"})
            if request is not None:
                self._remember(request, raw, result)
            return result
        except Exception:
            # A defeated local player is a terminal outcome, not a connection
            # error. This path contains no map/entity reads and grants no token.
            try:
                from .status import build_status_query, public_status
                raw = parse_response(await self.transport.execute(build_status_query(secrets.token_hex(16)),
                    expected_generation=expected_generation))
                result = public_status(raw)
                if result["status"] != "playing":
                    if request is not None:
                        self._remember(request, raw, result)
                    return result
            except Exception:
                pass
            return await self._unavailable()

    async def get_game_status(self) -> dict:
        async with self._lock:
            return await self._read_locked(ReadRequest("status"))

    async def _unavailable(self, code: str = "game_unavailable") -> dict:
        self._observation = None
        self._last_read = None
        self._history.clear()
        try:
            await self.transport.close()
        except Exception:
            pass
        return {"ok": False, "error": code}

    async def get_player_state(self) -> dict:
        async with self._lock:
            return await self._read_locked(ReadRequest("player"))

    async def get_diplomacy(self) -> dict:
        async with self._lock:
            return await self._read_locked(ReadRequest("diplomacy"))

    async def observe_area(self, x: int, y: int, radius: int = 2) -> dict:
        async with self._lock:
            self._observation = None
            try:
                integer(x, 0, 4095)
                integer(y, 0, 4095)
                integer(radius, 0, 8)
            except PolicyError:
                return {"ok": False, "error": "invalid_input"}
            return await self._read_locked(ReadRequest("map", (x, y, radius)))

    async def list_options(self, kind: str, entity_id: int | None = None) -> dict:
        async with self._lock:
            self._observation = None
            if kind not in ("research", "civic", "production"):
                return {"ok": False, "error": "invalid_input"}
            try:
                if kind == "production":
                    integer(entity_id)
                elif entity_id is not None:
                    raise PolicyError("invalid_input")
            except PolicyError:
                return {"ok": False, "error": "invalid_input"}
            return await self._read_locked(ReadRequest("options", (kind, entity_id)))

    async def inspect_game(self, category: str, params: dict | None = None) -> dict:
        async with self._lock:
            self._observation = None
            try:
                _, queries = registries()
                if type(category) is not str or category not in queries:
                    raise ValueError("invalid category")
                params = validate({} if params is None else params, queries[category].fields)
            except (ValueError, TypeError, KeyError):
                return {"ok": False, "error": "invalid_input"}
            return await self._read_locked(ReadRequest("inspection", (category, params)))

    async def wait_for_change(self, timeout_ms: int = 3000) -> dict:
        return await wait_for_change(self, timeout_ms)

    async def get_session_history(self, limit: int = 20) -> dict:
        """Read bounded local memory without a game query or new capability."""
        async with self._lock:
            return self._history.read(self.transport.connection_generation, limit)

    async def run_lua(self, code: str, reason: str, attempted_tools: list[str],
                      context: str = "InGame") -> dict:
        """Explicit last-resort contract, not a sandbox or automatic fairness filter."""
        from .fallback_lua import validate_request, build_preflight, build_script, parse_result

        def invalidate():
            self._observation = None
            self._last_read = None
            self._history.clear()
            self._preview_generation = None

        async with self._lock:
            invalidate()
            base = {"fallback": True, "refresh_required": True,
                    "automatic_fairness_filter": False, "operation_completion": "not_asserted"}
            dispatched = False
            try:
                try:
                    request = validate_request(code, reason, attempted_tools, context)
                except (ValueError, TypeError):
                    return {**base, "ok": False, "error": "invalid_input", "script_executed": False}
                base["receipt"] = {"id": secrets.token_hex(16), "context": request["context"],
                    "code_sha256": request["code_sha256"], "reason": request["reason"],
                    "attempted_tools": request["attempted_tools"], "retention": "response_only",
                    "attempts_verified": False}
                executor = getattr(self.transport, "execute_fallback", None)
                if not callable(executor):
                    return {**base, "ok": False, "error": "fallback_transport_unavailable", "script_executed": False}
                preflight = parse_response(await self.transport.execute(build_preflight(secrets.token_hex(16))))
                if preflight.get("fallback_eligible") is not True:
                    raise PolicyError("unavailable")
                identity = envelope(preflight)
                generation = self.transport.connection_generation
                if type(generation) is not int or generation < 1:
                    raise PolicyError("unavailable")
                script = build_script(request["code"], identity)
                dispatched = True
                output = parse_result(await executor(script, request["context"], expected_generation=generation))
                phase = output["phase"]
                executed = True if phase in {"completed", "runtime_error"} else None if phase == "outcome_unknown" else False
                result = {**base, "ok": phase == "completed", "status": phase,
                          "script_executed": executed, "output": output}
                if phase != "completed":
                    result["error"] = "fallback_" + phase
                return result
            except asyncio.CancelledError:
                try:
                    await self.transport.close()
                except Exception:
                    pass
                raise
            except Exception:
                # No exception, raw Lua, global log, or connection detail is forwarded.
                try:
                    await self.transport.close()
                except Exception:
                    pass
                return {**base, "ok": False,
                        "error": "fallback_outcome_unknown" if dispatched else "fallback_preflight_unavailable",
                        "script_executed": None if dispatched else False}
            finally:
                invalidate()

    async def act(self, observation_token: str, action: dict[str, Any]) -> dict:
        async with self._lock:
            previous, self._observation = self._observation, None
            # Every attempted action consumes the capability, even a malformed attempt.
            if (not isinstance(observation_token, str) or not observation_token.isascii()
                or len(observation_token) > 128
                or previous is None or not secrets.compare_digest(previous.token, observation_token)
                or previous.generation != self.transport.connection_generation
                or time.monotonic() - previous.issued_at > self._token_ttl):
                return {"ok": False, "error": "fresh_observation_required"}
            try:
                validated = validate_action(action)
                popup_for_action = {"choose_artifact": "artifact", "spy_escape": "spy_escape",
                                    "city_fate": "captured_city", "city_loyalty_choice": "disloyal_city"}.get(validated["type"])
                if popup_for_action and popup_for_action in previous.popup_ids:
                    return {"ok": False, "error": "use_visible_popup_action", "popup": popup_for_action,
                            "refresh_required": True}
                spec = registries()[0].get(validated["type"])
                visible_ui_action = (validated["type"] == "popup_action"
                                     and validated.get("popup") in previous.popup_ids)
                if validated["type"] == "popup_action" and not visible_ui_action:
                    return {"ok": False, "error": "fresh_observation_required"}
                if previous.mode != "turn" and not visible_ui_action and (spec is None or spec.turn_mode != previous.mode):
                    return {"ok": False, "error": "fresh_observation_required"}
            except (ValueError, TypeError, KeyError):
                return {"ok": False, "error": "invalid_action"}
            try:
                context = action_context(validated)
                if validated["type"] in {"district_preview_select_city", "district_preview_begin", "district_preview_cancel", "district_preview_exit_current"}:
                    from .extensions.district_preview import CONTEXT, build_action
                    context = CONTEXT
                    script = build_action(secrets.token_hex(16), validated,
                        self._preview_identity(previous.generation), previous.session,
                        previous.player_id, previous.turn)
                    self._preview_generation = previous.generation
                else:
                    script = build_action_query(secrets.token_hex(16), validated,
                        previous.session, previous.player_id, previous.turn)
                raw = parse_response(await self.transport.execute(script, context=context,
                    expected_generation=previous.generation))
                session, player, turn, _ = envelope(raw)
                if session != previous.session or player != previous.player_id or turn != previous.turn:
                    return await self._unavailable("action_outcome_unknown")
                if type(raw.get("accepted")) is not bool:
                    return await self._unavailable("action_outcome_unknown")
                self._history.submitted(previous, validated["type"], raw["accepted"])
                return {"ok": True, "accepted": raw["accepted"],
                        "status": "submitted" if raw["accepted"] else "rejected",
                        "refresh_required": True}
            except Exception:
                # A timeout can occur AFTER the engine applied a request. Never auto retry.
                return await self._unavailable("action_outcome_unknown")

    async def close(self) -> None:
        async with self._lock:
            self._observation = None
            self._last_read = None
            self._history.clear()
            if self._preview_generation == self.transport.connection_generation:
                from .extensions.district_preview import CONTEXT, build_cleanup
                try:
                    await self.transport.execute(build_cleanup(secrets.token_hex(16),
                        self._preview_identity(self._preview_generation)), context=CONTEXT,
                        expected_generation=self._preview_generation)
                except Exception:
                    pass
            self._preview_generation = None
            await self.transport.close()
