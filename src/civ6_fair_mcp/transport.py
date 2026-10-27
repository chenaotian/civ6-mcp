"""Bounded, local-only FireTuner transport; this is not an MCP tool.

The Firaxis framing and discovery protocol were checked against Liam Wilkinson's
MIT-licensed civ6-mcp tuner_client.py and connection.py:
https://github.com/lmwilki/civ6-mcp/tree/main/src/civ_mcp
See docs/UPSTREAM_LICENSE.txt. Normal execution keeps a fixed context allowlist;
the explicit fallback path can select a uniquely advertised native Lua state.
Neither path retries commands or forwards unsolicited game logs.
"""

from __future__ import annotations

import asyncio
import ipaddress
import math
import re
import secrets
import struct
from dataclasses import dataclass

from .extensions.popups import POPUP_CONTEXTS


class TransportError(ConnectionError):
    """Opaque connection/protocol failure; a submitted action may have executed."""


_HEADER = struct.Struct("<Ii")
_MAX_FRAME = 1024 * 1024
_MAX_SCRIPT = 128 * 1024
_MAX_TRANSACTION_BYTES = 4 * 1024 * 1024
_MAX_TRANSACTION_FRAMES = 1024
_JSON_PREFIX = "CIV6FAIR_JSON:"
_END = "---END---"
_ERROR = "Game connection unavailable or response invalid."
_CONTEXTS = frozenset({"InGame", "DistrictPlotIconManager", *POPUP_CONTEXTS.values()})
_FALLBACK_CONTEXT = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}\Z", re.ASCII)


def _validate_script(script: str) -> None:
    if not isinstance(script, str) or not script or "\x00" in script:
        raise ValueError("Invalid authored script.")
    try:
        size = len(script.encode("utf-8"))
    except UnicodeError:
        raise ValueError("Invalid authored script.") from None
    if size > _MAX_SCRIPT:
        raise ValueError("Authored script exceeds the size limit.")


def _fallback_roster(payload: str) -> dict[str, tuple[int, str]]:
    """Only native state names, with unique optional .xml aliases.

    An unrelated malformed/duplicate roster entry must not broaden access or
    break normal authored queries. No state name is interpolated into Lua.
    """
    fields = [part for part in re.split(r"[\x00\r\n]", payload) if part]
    candidates: dict[str, list[tuple[int, str]]] = {}
    for index in range(1, len(fields)):
        number, name = fields[index - 1], fields[index]
        if (not number.isascii() or not number.isdigit() or len(number) > 9
                or not _FALLBACK_CONTEXT.fullmatch(name)):
            continue
        value = (int(number), name)
        candidates.setdefault(name, []).append(value)
        if name.endswith(".xml"):
            candidates.setdefault(name[:-4], []).append(value)
    return {name: entries[0] for name, entries in candidates.items() if len(entries) == 1}


@dataclass
class _Budget:
    frames: int = 0
    size: int = 0


class FireTunerTransport:
    """Serialize authored scripts over one loopback FireTuner connection.

    ``execute`` returns only the marked JSON response and terminator, never raw
    engine errors or other Lua output. Timeouts, cancellation, malformed frames,
    and incomplete responses discard the connection. No command is replayed.
    ``connection_generation`` changes on connect/disconnect, allowing the service
    to invalidate its action tokens. This low-level API is for trusted server
    code only and must never be registered as a tool.
    """

    supports_ui_contexts = True

    def __init__(
        self, host: str = "127.0.0.1", port: int = 4318, *, timeout: float = 8.0
    ) -> None:
        if not isinstance(host, str):
            raise ValueError("Only loopback FireTuner addresses are allowed.")
        if host.lower() == "localhost":
            host = "127.0.0.1"  # Never resolve a user-supplied DNS name.
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError("Only loopback FireTuner addresses are allowed.") from None
        if not address.is_loopback or "%" in host:
            raise ValueError("Only loopback FireTuner addresses are allowed.")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid FireTuner port.")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or not 0 < timeout <= 120
        ):
            raise ValueError("Invalid FireTuner timeout.")
        self.host = str(address)
        self.port = port
        self.timeout = float(timeout)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._state_index: int | None = None
        self._contexts: dict[str, int] = {}
        self._context_output_names: dict[str, str] = {}
        self._fallback_contexts: dict[str, tuple[int, str]] = {}
        self._generation = 0
        self._lock = asyncio.Lock()

    @property
    def connection_generation(self) -> int:
        return self._generation

    async def execute(
        self,
        script: str,
        context: str = "InGame",
        *,
        expected_generation: int | None = None,
    ) -> str:
        if context not in _CONTEXTS:
            raise ValueError("Only authored gameplay/UI contexts are permitted.")
        _validate_script(script)
        if expected_generation is not None and type(expected_generation) is not int:
            raise ValueError("Invalid expected connection generation.")
        async with self._lock:
            try:
                # An action must reuse the connection its observation came from.
                # Check inside the lock, before connecting or writing anything.
                if expected_generation is not None and (
                    self._writer is None or self._generation != expected_generation
                ):
                    raise TransportError(_ERROR)
                return await asyncio.wait_for(
                    self._execute_locked(script, context), timeout=self.timeout
                )
            except asyncio.CancelledError:
                await self._close_locked()
                raise
            except Exception:
                # Do not leak a host, engine exception, Lua source or log data.
                # Do not reconnect here: the command may already have executed.
                await self._close_locked()
                raise TransportError(_ERROR) from None

    async def execute_fallback(
        self, script: str, context: str = "InGame", *, expected_generation: int
    ) -> str:
        """Run one explicitly requested fallback on an already observed connection.

        The service must establish local-player eligibility before calling this.
        This is a native-context transport path, not a Lua sandbox or a promise
        of player-perspective output. It never reconnects, retries, or modifies
        the context allowlist of ordinary ``execute`` calls.
        """
        if type(context) is not str or not _FALLBACK_CONTEXT.fullmatch(context):
            raise ValueError("Invalid fallback context.")
        _validate_script(script)
        if type(expected_generation) is not int or expected_generation < 1:
            raise ValueError("Invalid expected connection generation.")
        async with self._lock:
            try:
                if (self._writer is None or self._generation != expected_generation
                        or self._reader is None or self._writer.is_closing()
                        or self._reader.at_eof()):
                    raise TransportError(_ERROR)
                return await asyncio.wait_for(
                    self._execute_locked(script, context, fallback=True), timeout=self.timeout
                )
            except asyncio.CancelledError:
                await self._close_locked()
                raise
            except Exception:
                await self._close_locked()
                raise TransportError(_ERROR) from None

    async def close(self) -> None:
        async with self._lock:
            await self._close_locked()

    async def _close_locked(self) -> None:
        writer = self._writer
        if self._reader is not None or writer is not None:
            self._generation += 1
        self._reader = None
        self._writer = None
        self._state_index = None
        self._contexts = {}
        self._context_output_names = {}
        self._fallback_contexts = {}
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
            except (OSError, asyncio.TimeoutError):
                pass

    async def _read(self, budget: _Budget) -> tuple[int, str]:
        if self._reader is None:
            raise TransportError(_ERROR)
        header = await self._reader.readexactly(_HEADER.size)
        size, tag = _HEADER.unpack(header)
        budget.frames += 1
        budget.size += size + _HEADER.size
        if (
            not 1 <= size <= _MAX_FRAME
            or budget.frames > _MAX_TRANSACTION_FRAMES
            or budget.size > _MAX_TRANSACTION_BYTES
        ):
            raise TransportError(_ERROR)
        data = await self._reader.readexactly(size)
        if not data.endswith(b"\x00"):
            raise TransportError(_ERROR)
        return tag, data.rstrip(b"\x00").decode("utf-8", errors="strict")

    async def _send(self, tag: int, payload: str) -> None:
        if self._writer is None:
            raise TransportError(_ERROR)
        data = payload.encode("utf-8") + b"\x00"
        if len(data) > _MAX_FRAME:
            raise TransportError(_ERROR)
        self._writer.write(_HEADER.pack(len(data), tag) + data)
        await self._writer.drain()

    async def _connect(self, budget: _Budget) -> None:
        if self._writer is not None:
            if self._writer.is_closing() or self._reader is None or self._reader.at_eof():
                # Invalidate this call; a later observation may connect afresh.
                raise TransportError(_ERROR)
            return
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        await self._send(4, "APP:")
        while True:
            _, payload = await self._read(budget)
            if payload.startswith("ERR:"):
                raise TransportError(_ERROR)
            if payload and not payload.startswith("O\x00"):
                break
        await self._send(4, "LSQ:")
        while True:
            _, payload = await self._read(budget)
            if payload.startswith("ERR:"):
                raise TransportError(_ERROR)
            if not payload or payload.startswith("O\x00"):
                continue
            fields = [part.strip() for part in re.split(r"[\x00\r\n]", payload) if part.strip()]
            matches = [
                int(fields[i - 1])
                for i in range(1, len(fields))
                if fields[i] == "InGame"
                and fields[i - 1].isascii()
                and fields[i - 1].isdigit()
                and len(fields[i - 1]) <= 9
            ]
            if len(matches) != 1:
                raise TransportError(_ERROR)
            self._state_index = matches[0]
            self._fallback_contexts = _fallback_roster(payload)
            self._contexts = {"InGame": matches[0]}
            self._context_output_names = {"InGame": "InGame"}
            for name in _CONTEXTS - {"InGame"}:
                indices = [(int(fields[i - 1]), fields[i]) for i in range(1, len(fields))
                           if fields[i] in {name, name + ".xml"} and fields[i - 1].isascii()
                           and fields[i - 1].isdigit() and len(fields[i - 1]) <= 9]
                if len(indices) == 1:
                    self._contexts[name], self._context_output_names[name] = indices[0]
            self._generation += 1
            return

    @staticmethod
    def _output(payload: str, context: str = "InGame") -> str | None:
        # Accept output only from the selected state's actual advertised name.
        prefix = f"O\x00{context}: "
        if payload.startswith(prefix):
            return payload[len(prefix) :].rstrip("\r\n")
        return None

    async def _execute_locked(self, script: str, context: str = "InGame", *, fallback: bool = False) -> str:
        budget = _Budget()
        if fallback:
            # Deliberately do not call _connect: a dropped link or changed
            # generation requires a fresh ordinary observation first.
            if self._writer is None or self._reader is None or context not in self._fallback_contexts:
                raise TransportError(_ERROR)
            state_index, output_name = self._fallback_contexts[context]
        else:
            await self._connect(budget)
            if context not in self._contexts:
                raise TransportError(_ERROR)
            state_index, output_name = self._contexts[context], self._context_output_names[context]
        marker = secrets.token_hex(16)
        begin = "CIV6FAIR_BEGIN_" + marker
        done = "CIV6FAIR_DONE_" + marker
        # Private per-request boundaries prevent stale replies from a previous
        # command satisfying this one; the random strings contain only hex.
        framed = f'do\nprint("{begin}")\n{script}\nprint("{done}")\nend'
        await self._send(3, f"CMD:{state_index}:{framed}")
        started = False
        result: str | None = None
        ended = False
        while True:
            _, payload = await self._read(budget)
            if payload.startswith("ERR:"):
                raise TransportError(_ERROR)
            output = self._output(payload, output_name)
            if output == begin:
                if started:
                    raise TransportError(_ERROR)
                started = True
                continue
            if not started or output is None:
                continue
            if output == done:
                if result is None or not ended:
                    raise TransportError(_ERROR)
                return result + "\n" + _END
            if output.startswith(_JSON_PREFIX):
                if result is not None or ended:
                    raise TransportError(_ERROR)
                result = output
            elif output == _END:
                if result is None or ended:
                    raise TransportError(_ERROR)
                ended = True
            # All other output is deliberately discarded, even inside markers.
