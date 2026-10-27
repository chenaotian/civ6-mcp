"""Bounded re-observation of an authored read; no actions or raw-state cache."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import time
from typing import Any, TYPE_CHECKING

from .interaction_feedback import changes, snapshot

if TYPE_CHECKING:
    from .service import FairGameService

POLL_SECONDS = 0.25
READ_HEADROOM_SECONDS = 0.05


@dataclass(frozen=True)
class ReadRequest:
    kind: str
    args: tuple = ()


@dataclass(frozen=True)
class ReadBaseline:
    request: ReadRequest
    session: str
    player_id: int
    turn: int
    generation: int
    fingerprint: str
    ui_fingerprint: str
    feedback: dict


def fingerprint(public: Any) -> str:
    """Only call on already projected values; never inspect raw game replies."""
    def stable(value):
        if isinstance(value, list):
            return [stable(item) for item in value]
        if isinstance(value, dict):
            # The visible popup reader rotates response revisions every read.
            # Keep fresh revisions in returned actions, but not in comparison.
            return {key: stable(item) for key, item in value.items()
                    if not (value.get("type") == "popup_action" and key == "revision")}
        return value

    public = stable(public)
    if isinstance(public, dict):
        public = {key: value for key, value in public.items()
                  if key not in {"observation_token", "wait"}}
        # Engine collection order is not a change to an available choice or
        # entity. Preserve order of UI text/buttons and all other lists.
        for key in ("items", "units", "cities", "tiles"):
            value = public.get(key)
            if isinstance(value, list):
                public[key] = sorted(value, key=lambda item: json.dumps(
                    item, sort_keys=True, ensure_ascii=True, allow_nan=False))
    encoded = json.dumps(public, sort_keys=True, ensure_ascii=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def remember(request: ReadRequest, raw: dict, public: dict, generation: int) -> ReadBaseline:
    from .policy import envelope
    session, player, turn, _ = envelope(raw)
    return ReadBaseline(request, session, player, turn, generation,
                        fingerprint(public), fingerprint(public.get("ui")),
                        snapshot(request.kind, public))


def prepare_read(request: ReadRequest, nonce: str):
    """Shared fixed scripts/projectors for ordinary reads and waiting polls."""
    from .actions import build_options_query
    from .diplomacy import build_diplomacy_query
    from .extensions import build_inspection_query
    from .inspection_policy import public_inspection
    from .policy import public_diplomacy, public_map, public_options, public_player
    from .queries import build_map_query, build_player_query
    from .status import build_status_query, public_status

    if request.kind == "player":
        return build_player_query(nonce), public_player, None
    if request.kind == "diplomacy":
        return build_diplomacy_query(nonce), public_diplomacy, None
    if request.kind == "map":
        return build_map_query(nonce, *request.args), public_map, None
    if request.kind == "options":
        kind, entity_id = request.args
        return (build_options_query(nonce, kind, entity_id),
                lambda raw: public_options(raw, kind, entity_id), None)
    if request.kind == "inspection":
        category, params = request.args
        mode = {"pending_decisions": "ui", "world_congress": "congress",
                "diplomacy_actions": "diplomacy", "deal_state": "diplomacy",
                "deal_options": "diplomacy", "war_deal_options": "diplomacy",
                "diplomacy_sessions": "diplomacy"}.get(category)
        return (build_inspection_query(nonce, category, params),
                lambda raw: public_inspection(raw, category, params if category in {
                    "combat_preview", "special_unit_sites", "unit_recommendations",
                    "exploration_frontier", "city_religion", "visible_city_religion",
                    "own_science_victory"} else None), mode)
    if request.kind == "status":
        return build_status_query(nonce), public_status, None
    raise ValueError("invalid internal read")


async def wait_for_change(service: FairGameService, timeout_ms: int = 3000) -> dict:
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 10000:
        return {"ok": False, "error": "invalid_input"}
    started = time.monotonic()
    deadline = started + timeout_ms / 1000
    feedback = None

    def finish(public: dict, reason: str, changed: bool, *, incomplete: bool = False,
               strip_token: bool = False):
        result = dict(public)
        result["wait"] = {"reason": reason, "changed": changed,
                          "elapsed_ms": max(0, round((time.monotonic() - started) * 1000))}
        if feedback is not None and not incomplete and not strip_token:
            result["wait"]["changes"] = feedback
        if incomplete or strip_token:
            result.pop("observation_token", None)
            result.pop("token_scope", None)
        if incomplete:
            result["wait"]["read_incomplete"] = True
        return result

    # Include contention in the deadline. A timed-out lock acquisition cannot
    # invalidate another call's fresh observation.
    try:
        await asyncio.wait_for(service._lock.acquire(), timeout=timeout_ms / 1000)
    except asyncio.TimeoutError:
        return finish({"ok": False, "error": "wait_timeout"}, "timeout", False)
    try:
        baseline = service._last_read
        service._observation = None
        if baseline is None:
            return finish({"ok": False, "error": "observation_required"}, "no_baseline", False)
        if baseline.generation != service.transport.connection_generation:
            service._last_read = None
            return finish({"ok": False, "error": "fresh_observation_required"}, "connection_changed", False)
        latest = None
        phase = "reading"
        read_durations: list[float] = []

        async def poll():
            nonlocal latest, phase, feedback
            while True:
                if read_durations:
                    remaining = deadline - time.monotonic()
                    # Include the whole public observation, including popup
                    # reads. Do not open a final transaction that recent
                    # timings already suggest cannot finish before deadline.
                    minimum = max(read_durations) * 1.5 + READ_HEADROOM_SECONDS
                    if remaining <= minimum:
                        phase = "sleeping"
                        await asyncio.sleep(max(0, remaining))
                        raise asyncio.TimeoutError
                phase = "reading"
                read_started = time.monotonic()
                latest = await service._read_locked(
                    baseline.request, expected_generation=baseline.generation)
                read_durations.append(max(0, time.monotonic() - read_started))
                del read_durations[:-3]
                current = service._last_read
                phase = "completed"
                if not latest.get("ok") or current is None:
                    return finish(latest, "unavailable", False)
                if (current.generation != baseline.generation
                        or service.transport.connection_generation != baseline.generation):
                    service._observation = None
                    service._last_read = None
                    service._history.clear()
                    return finish(latest, "connection_changed", True, strip_token=True)
                if ((current.session, current.player_id) != (baseline.session, baseline.player_id)
                        or current.turn < baseline.turn):
                    service._observation = None
                    service._last_read = None
                    service._history.clear()
                    return finish(latest, "session_changed", True, strip_token=True)
                if current.request == baseline.request:
                    feedback = changes(baseline.feedback, current.feedback)
                if current.turn != baseline.turn:
                    return finish(latest, "turn_changed", True)
                if current.ui_fingerprint != baseline.ui_fingerprint:
                    return finish(latest, "ui_changed", True)
                if current.fingerprint != baseline.fingerprint:
                    return finish(latest, "observation_changed", True)
                # A normal same-state read can replace its token, but tokens
                # alone never end the wait. Never infer action completion.
                phase = "sleeping"
                await asyncio.sleep(POLL_SECONDS)

        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError
            return await asyncio.wait_for(poll(), timeout=remaining)
        except asyncio.TimeoutError:
            interrupted = phase == "reading"
            if not interrupted and service.transport.connection_generation != baseline.generation:
                service._observation = None
                service._last_read = None
                return finish(latest or {"ok": False, "error": "wait_timeout"},
                              "connection_changed", False, strip_token=True)
            if interrupted:
                service._observation = None
                service._last_read = None
            return finish(latest or {"ok": False, "error": "wait_timeout"},
                          "timeout", False, incomplete=interrupted)
        except asyncio.CancelledError:
            service._observation = None
            service._last_read = None
            raise
    finally:
        service._lock.release()
