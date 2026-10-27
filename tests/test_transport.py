"""Real asyncio TCP tests for boundaries, cancellation and no action replay."""

import asyncio
import contextlib
import re
import struct
import unittest

from civ6_fair_mcp.transport import FireTunerTransport, TransportError


def frame(payload, tag=3):
    data = payload.encode("utf-8") + b"\x00"
    return struct.pack("<Ii", len(data), tag) + data


async def read_frame(reader):
    size, tag = struct.unpack("<Ii", await reader.readexactly(8))
    return tag, (await reader.readexactly(size))[:-1].decode("utf-8")


def markers(command):
    begin = re.search(r'CIV6FAIR_BEGIN_[0-9a-f]{32}', command).group(0)
    done = re.search(r'CIV6FAIR_DONE_[0-9a-f]{32}', command).group(0)
    return begin, done


def output(text, context="InGame"):
    return frame(f"O\x00{context}: {text}")


def response(command, value='{"ok":true}', *, end=True, done=True):
    start_marker, done_marker = markers(command)
    data = output(start_marker) + output("CIV6FAIR_JSON:" + value)
    if end:
        data += output("---END---")
    if done:
        data += output(done_marker)
    return data


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.servers = []
        self.tasks = set()
        self.clients = []
        self.errors = []
        self.connections = 0
        self.commands = []

    async def asyncTearDown(self):
        for client in self.clients:
            await client.close()
        for server in self.servers:
            server.close()
            await server.wait_closed()
        pending = list(self.tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if self.errors:
            raise self.errors[0]

    async def make_client(self, handle_command, *, timeout=0.5, states=None):
        async def handler(reader, writer):
            self.tasks.add(asyncio.current_task())
            self.connections += 1
            try:
                self.assertEqual(await read_frame(reader), (4, "APP:"))
                writer.write(output("unsolicited hidden world log") + frame("Civilization VI", 4))
                await writer.drain()
                self.assertEqual(await read_frame(reader), (4, "LSQ:"))
                writer.write(frame(states or "2\x00GameCore_Tuner\x0017\x00InGame", 4))
                await writer.drain()
                while True:
                    tag, command = await read_frame(reader)
                    self.assertEqual(tag, 3)
                    self.assertTrue(command.startswith("CMD:17:"))
                    self.commands.append(command)
                    await handle_command(reader, writer, command)
            except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
                pass
            except Exception as exc:
                self.errors.append(exc)
            finally:
                writer.close()
                with contextlib.suppress(ConnectionError):
                    await writer.wait_closed()
                self.tasks.discard(asyncio.current_task())

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        self.servers.append(server)
        port = server.sockets[0].getsockname()[1]
        client = FireTunerTransport(port=port, timeout=timeout)
        self.clients.append(client)
        return client

    async def test_framing_fragmentation_and_global_log_suppression(self):
        async def handler(reader, writer, command):
            begin, done = markers(command)
            data = (
                output('CIV6FAIR_JSON:{"hidden":"stale"}')
                + output("---END---")
                + output(begin)
                + output('CIV6FAIR_JSON:{"hidden":"foreign"}', "GameCore_Tuner")
                + output("SECRET_MAP_DATA")
                + frame("")
                + output('CIV6FAIR_JSON:{"ok":true,"name":"城市"}')
                + output("---END---")
                + output(done)
            )
            # Split inside both headers and multi-byte UTF-8 characters.
            for i in range(0, len(data), 7):
                writer.write(data[i : i + 7])
                await writer.drain()
                await asyncio.sleep(0)

        # This checks framing/UTF-8/log isolation, not a deadline. Many tiny
        # writes take ~0.48 s on Windows loopback, too close to the fixture's
        # 0.5 s default under a full-suite load. Timeout-specific tests below
        # retain their explicit short budgets; production timeouts are unchanged.
        client = await self.make_client(handler, timeout=5.0)
        result = await client.execute('print("authored query")')
        self.assertEqual(result, 'CIV6FAIR_JSON:{"ok":true,"name":"城市"}\n---END---')
        self.assertEqual(client.connection_generation, 1)

    async def test_serializes_concurrent_commands_on_one_connection(self):
        async def handler(reader, writer, command):
            await asyncio.sleep(0.01)
            value = '{"id":1}' if '"first"' in command else '{"id":2}'
            writer.write(response(command, value))
            await writer.drain()

        client = await self.make_client(handler)
        first, second = await asyncio.gather(
            client.execute('print("first")'), client.execute('print("second")')
        )
        self.assertIn('"id":1', first)
        self.assertIn('"id":2', second)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 2)

    async def test_unicode_line_separators_are_preserved_in_json(self):
        value = '{"name":"City\u0085\u2028\u2029Name"}'

        async def handler(reader, writer, command):
            writer.write(response(command, value))
            await writer.drain()

        client = await self.make_client(handler)
        self.assertEqual(
            await client.execute("observation()"),
            "CIV6FAIR_JSON:" + value + "\n---END---",
        )

    async def test_generation_precondition_blocks_connect_and_stale_action(self):
        async def handler(reader, writer, command):
            writer.write(response(command))
            await writer.drain()

        client = await self.make_client(handler)
        with self.assertRaises(TransportError):
            await client.execute("action()", expected_generation=0)
        self.assertEqual(self.connections, 0)
        await client.execute("observation()")
        generation = client.connection_generation
        await client.execute("action()", expected_generation=generation)
        self.assertEqual(len(self.commands), 2)
        await client.close()
        self.assertNotEqual(client.connection_generation, generation)
        with self.assertRaises(TransportError):
            await client.execute("action()", expected_generation=generation)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 2)

    async def test_timeout_after_submission_never_replays(self):
        async def handler(reader, writer, command):
            writer.write(response(command, done="observation()" in command))
            await writer.drain()

        # Establish the observed connection first, just as a real MCP action
        # does. A 60 ms budget including TCP discovery sometimes expired before
        # any submission on Windows and tested the wrong failure boundary.
        client = await self.make_client(handler, timeout=5.0)
        await client.execute("observation()")
        generation = client.connection_generation
        client.timeout = 1.0
        with self.assertRaises(TransportError):
            await client.execute("action()", expected_generation=generation)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 2)
        self.assertEqual(sum("action()" in command for command in self.commands), 1)
        self.assertEqual(client.connection_generation, 2)

    async def test_disconnect_after_submission_never_replays(self):
        async def handler(reader, writer, command):
            writer.close()

        client = await self.make_client(handler)
        with self.assertRaises(TransportError):
            await client.execute("action()")
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 1)

    async def test_opaque_engine_error(self):
        async def handler(reader, writer, command):
            writer.write(frame("ERR: undiscovered enemy capital at 20,30"))
            await writer.drain()

        client = await self.make_client(handler)
        with self.assertRaises(TransportError) as caught:
            await client.execute("observation()")
        self.assertNotIn("enemy", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    async def test_oversized_frame_rejected_before_payload_read(self):
        async def handler(reader, writer, command):
            writer.write(struct.pack("<Ii", 1024 * 1024 + 1, 3))
            await writer.drain()

        client = await self.make_client(handler)
        with self.assertRaises(TransportError):
            await client.execute("observation()")

    async def test_duplicate_json_is_rejected(self):
        async def handler(reader, writer, command):
            begin, done = markers(command)
            writer.write(
                output(begin)
                + output('CIV6FAIR_JSON:{"ok":true}')
                + output('CIV6FAIR_JSON:{"secret":true}')
                + output("---END---")
                + output(done)
            )
            await writer.drain()

        client = await self.make_client(handler)
        with self.assertRaises(TransportError):
            await client.execute("observation()")

    async def test_missing_response_terminator_rejected(self):
        async def handler(reader, writer, command):
            writer.write(response(command, end=False))
            await writer.drain()

        client = await self.make_client(handler)
        with self.assertRaises(TransportError):
            await client.execute("observation()")

    async def test_cancellation_invalidates_connection(self):
        submitted = asyncio.Event()

        async def handler(reader, writer, command):
            submitted.set()

        client = await self.make_client(handler)
        task = asyncio.create_task(client.execute("action()"))
        await asyncio.wait_for(submitted.wait(), timeout=0.5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(client.connection_generation, 2)
        self.assertEqual(len(self.commands), 1)

    async def test_newline_state_discovery(self):
        async def handler(reader, writer, command):
            writer.write(response(command))
            await writer.drain()

        client = await self.make_client(handler, states="2\nGameCore_Tuner\n17\nInGame")
        self.assertIn('"ok":true', await client.execute("observation()"))

    async def test_missing_ingame_context_never_submits_script(self):
        async def handler(reader, writer, command):
            self.fail("Script must not be submitted without InGame")

        client = await self.make_client(handler, states="2\x00GameCore_Tuner")
        with self.assertRaises(TransportError):
            await client.execute("observation()")
        self.assertEqual(self.commands, [])

    async def test_refuses_other_context_and_bad_scripts_without_connecting(self):
        client = FireTunerTransport()
        for code, context in [("query()", "GameCore_Tuner"), ("a\x00b", "InGame"), ("x" * 131073, "InGame")]:
            with self.subTest(code_length=len(code), context=context):
                with self.assertRaises(ValueError):
                    await client.execute(code, context)
        self.assertEqual(client.connection_generation, 0)

    def test_loopback_only_and_constructor_bounds(self):
        for host in ["example.com", "0.0.0.0", "192.168.1.1", "::", "::1%eth0", "127.0.0.1.example.com"]:
            with self.subTest(host=host), self.assertRaises(ValueError):
                FireTunerTransport(host=host)
        self.assertEqual(FireTunerTransport(host="localhost").host, "127.0.0.1")
        self.assertEqual(FireTunerTransport(host="::1").host, "::1")
        for port in [0, -1, 65536, True, "4318"]:
            with self.subTest(port=port), self.assertRaises(ValueError):
                FireTunerTransport(port=port)
        for timeout in [0, -1, float("inf"), float("nan"), True]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                FireTunerTransport(timeout=timeout)


if __name__ == "__main__":
    unittest.main()
