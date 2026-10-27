"""Temporary loopback tests for the explicit native Lua fallback path."""

import asyncio
import contextlib
import unittest
from unittest.mock import patch

from civ6_fair_mcp.transport import FireTunerTransport, TransportError
from test_transport import frame, markers, output, read_frame


def state_list(*entries):
    return "\x00".join(str(field) for entry in entries for field in entry)


def state_response(command, context="InGame", value='{"ok":true}', *, done=True):
    begin, finish = markers(command)
    data = (output(begin, context) + output("CIV6FAIR_JSON:" + value, context)
            + output("---END---", context))
    if done:
        data += output(finish, context)
    return data


class FallbackTransportTests(unittest.IsolatedAsyncioTestCase):
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

    async def make_client(self, handle_command=None, *, extra_states=()):
        roster = state_list((17, "InGame"), (2, "GameCore_Tuner"), *extra_states)
        names = {17: "InGame", 2: "GameCore_Tuner", **dict(extra_states)}

        async def handler(reader, writer):
            self.tasks.add(asyncio.current_task())
            self.connections += 1
            try:
                self.assertEqual(await read_frame(reader), (4, "APP:"))
                writer.write(frame("Civilization VI", 4))
                await writer.drain()
                self.assertEqual(await read_frame(reader), (4, "LSQ:"))
                writer.write(frame(roster, 4))
                await writer.drain()
                while True:
                    tag, command = await read_frame(reader)
                    self.assertEqual(tag, 3)
                    self.assertTrue(command.startswith("CMD:"))
                    self.commands.append(command)
                    if handle_command is not None:
                        await handle_command(reader, writer, command)
                    else:
                        index = int(command.split(":", 2)[1])
                        writer.write(state_response(command, names[index]))
                        await writer.drain()
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
        client = FireTunerTransport(port=server.sockets[0].getsockname()[1], timeout=5.0)
        self.clients.append(client)
        return client

    async def observe(self, client):
        await client.execute("observation()")
        return client.connection_generation

    async def test_native_gamecore_and_unknown_ui_state_are_explicit_fallback_only(self):
        client = await self.make_client(extra_states=((29, "NewNativePopup"),))
        generation = await self.observe(client)
        for context, index in (("InGame", 17), ("GameCore_Tuner", 2), ("NewNativePopup", 29)):
            with self.subTest(context=context):
                result = await client.execute_fallback("repair()", context, expected_generation=generation)
                self.assertEqual(result, 'CIV6FAIR_JSON:{"ok":true}\n---END---')
                self.assertTrue(self.commands[-1].startswith(f"CMD:{index}:"))
                if context != "InGame":
                    with self.assertRaises(ValueError):
                        await client.execute("repair()", context)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 4)

    async def test_unknown_state_never_submits_or_reconnects(self):
        client = await self.make_client()
        generation = await self.observe(client)
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", "UnadvertisedPopup", expected_generation=generation)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(client._fallback_contexts, {})

    async def test_fallback_without_observed_connection_does_not_connect(self):
        client = await self.make_client()
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", expected_generation=1)
        self.assertEqual(self.connections, 0)
        self.assertEqual(self.commands, [])

    async def test_stale_generation_on_live_connection_does_not_submit(self):
        client = await self.make_client()
        generation = await self.observe(client)
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", expected_generation=generation + 1)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 1)

    async def test_close_clears_roster_and_old_generation_cannot_reconnect(self):
        client = await self.make_client(extra_states=((29, "NewNativePopup"),))
        generation = await self.observe(client)
        self.assertIn("NewNativePopup", client._fallback_contexts)
        await client.close()
        self.assertEqual(client._fallback_contexts, {})
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", "NewNativePopup", expected_generation=generation)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 1)

    async def test_invalid_names_scripts_and_generations_are_rejected_without_io(self):
        client = await self.make_client()
        for context in (None, 3, "", "A" * 129, "../Popup", "a/b", "a\\b", "a:b",
                        "return os.exit()", "Popup\x00", "Popup\n", " Popup", "弹窗", "9Popup"):
            with self.subTest(context=context), self.assertRaises(ValueError):
                await client.execute_fallback("repair()", context, expected_generation=1)
        for script in (None, "", "a\x00b", "x" * 131073, "\ud800"):
            with self.subTest(script_length=len(script) if script else 0), self.assertRaises(ValueError):
                await client.execute_fallback(script, expected_generation=1)
        for generation in (None, True, False, 0, -1, 1.0, "1"):
            with self.subTest(generation=generation), self.assertRaises(ValueError):
                await client.execute_fallback("repair()", expected_generation=generation)
        with self.assertRaises(TypeError):
            await client.execute_fallback("repair()")
        self.assertEqual(self.connections, 0)
        self.assertEqual(self.commands, [])

    async def test_xml_state_and_unique_short_alias_use_actual_output_name(self):
        client = await self.make_client(extra_states=((29, "NewNativePopup.xml"),))
        generation = await self.observe(client)
        for context in ("NewNativePopup", "NewNativePopup.xml"):
            with self.subTest(context=context):
                result = await client.execute_fallback("repair()", context, expected_generation=generation)
                self.assertIn('"ok":true', result)
                self.assertTrue(self.commands[-1].startswith("CMD:29:"))

    async def test_ambiguous_short_alias_is_unavailable_but_exact_xml_name_works(self):
        client = await self.make_client(extra_states=((29, "NewNativePopup.xml"), (30, "NewNativePopup")))
        generation = await self.observe(client)
        result = await client.execute_fallback("repair()", "NewNativePopup.xml", expected_generation=generation)
        self.assertIn('"ok":true', result)
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", "NewNativePopup", expected_generation=generation)
        self.assertEqual(len(self.commands), 2)

    async def test_duplicate_native_names_are_unavailable(self):
        client = await self.make_client(extra_states=((29, "NewNativePopup"), (30, "NewNativePopup")))
        generation = await self.observe(client)
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", "NewNativePopup", expected_generation=generation)
        self.assertEqual(len(self.commands), 1)

    async def test_invalid_advertised_names_do_not_create_trimmed_aliases(self):
        client = await self.make_client(extra_states=((29, " NewNativePopup "), (30, "a/b"), (31, "A" * 129)))
        generation = await self.observe(client)
        self.assertEqual(set(client._fallback_contexts), {"InGame", "GameCore_Tuner"})
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", "NewNativePopup", expected_generation=generation)
        self.assertEqual(len(self.commands), 1)

    async def test_foreign_context_spoofed_markers_and_unmarked_logs_are_suppressed(self):
        async def handler(reader, writer, command):
            if command.startswith("CMD:17:"):
                writer.write(state_response(command))
            else:
                begin, finish = markers(command)
                writer.write(state_response(command, "InGame", '{"secret":"foreign"}')
                             + output('CIV6FAIR_JSON:{"secret":"stale"}', "NewNativePopup.xml")
                             + output(begin, "NewNativePopup.xml")
                             + output("HIDDEN_GLOBAL_LOG", "NewNativePopup.xml")
                             + output('CIV6FAIR_JSON:{"visible":"继续"}', "NewNativePopup.xml")
                             + output("---END---", "NewNativePopup.xml")
                             + output(finish, "NewNativePopup.xml"))
            await writer.drain()

        client = await self.make_client(handler, extra_states=((29, "NewNativePopup.xml"),))
        generation = await self.observe(client)
        result = await client.execute_fallback("repair()", "NewNativePopup", expected_generation=generation)
        self.assertEqual(result, 'CIV6FAIR_JSON:{"visible":"继续"}\n---END---')

    async def test_timeout_after_submission_never_replays(self):
        async def handler(reader, writer, command):
            writer.write(state_response(command, done="observation()" in command))
            await writer.drain()

        client = await self.make_client(handler)
        generation = await self.observe(client)
        client.timeout = 1.0
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", expected_generation=generation)
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", expected_generation=generation)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 2)
        self.assertEqual(sum("repair()" in command for command in self.commands), 1)
        self.assertEqual(client._fallback_contexts, {})

    async def test_cancellation_after_submission_never_replays(self):
        submitted = asyncio.Event()

        async def handler(reader, writer, command):
            if "observation()" in command:
                writer.write(state_response(command))
                await writer.drain()
            else:
                submitted.set()

        client = await self.make_client(handler)
        generation = await self.observe(client)
        pending = asyncio.create_task(client.execute_fallback("repair()", expected_generation=generation))
        await asyncio.wait_for(submitted.wait(), timeout=5.0)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        with self.assertRaises(TransportError):
            await client.execute_fallback("repair()", expected_generation=generation)
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 2)
        self.assertEqual(client._fallback_contexts, {})

    async def test_transaction_frame_budget_applies_to_fallback(self):
        async def handler(reader, writer, command):
            data = state_response(command)
            if "repair()" in command:
                data = output("unsolicited hidden log") * 5 + data
            writer.write(data)
            await writer.drain()

        client = await self.make_client(handler)
        generation = await self.observe(client)
        with patch("civ6_fair_mcp.transport._MAX_TRANSACTION_FRAMES", 4):
            with self.assertRaises(TransportError) as error:
                await client.execute_fallback("repair()", expected_generation=generation)
        self.assertNotIn("hidden", str(error.exception))
        self.assertEqual(self.connections, 1)
        self.assertEqual(len(self.commands), 2)
