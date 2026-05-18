"""Tests for HiveMindMattermostBridge.

Same shape as the deltachat / matrix bridge test suites:
- HiveMind side replaced with ``AsyncFakeHiveMessageBus``.
- ``MMostBot`` replaced with a ``_StubBot`` that records sends and
  exposes hooks to simulate inbound chat events from any thread.
"""
from __future__ import annotations

import asyncio
import threading
import unittest
from typing import List, Tuple
from unittest.mock import MagicMock

from hivemind_bus_client.fakebus import AsyncFakeHiveMessageBus
from hivemind_bus_client.message import HiveMessage, HiveMessageType
from ovos_bus_client.message import Message

from mattermost_bridge import HiveMindMattermostBridge


class _StubBot:
    """Stand-in for ``MMostBot``. Records sends; exposes a hook to
    simulate an incoming chat event from any thread. ``listen()`` is a
    long-running blocking call in production — here it just blocks on
    a threading Event until the test asks it to stop."""

    def __init__(self):
        self.handle_mention = None
        self.handle_direct_message = None
        self.sent: List[Tuple[str, str]] = []  # (channel_id, message)
        self._listen_event = threading.Event()
        self.listen_started = threading.Event()

    def listen(self):
        # mirrors what mattermostdriver.init_websocket would do — block
        # forever (until we set _listen_event)
        self.listen_started.set()
        self._listen_event.wait()

    def stop_listening(self):
        self._listen_event.set()

    def send_message(self, channel_id, message, file_paths=None):
        self.sent.append((channel_id, message))

    def fire_mention(self, message: str, sender: str, channel_id: str,
                     *, from_thread: bool = False) -> None:
        cb = self.handle_mention
        assert cb is not None, "bridge.start() not called"
        if from_thread:
            done = threading.Event()
            def _go():
                cb(message, sender, channel_id)
                done.set()
            threading.Thread(target=_go, daemon=True).start()
            done.wait(timeout=2)
        else:
            cb(message, sender, channel_id)

    def fire_direct_message(self, message: str, sender: str, channel_id: str,
                            *, from_thread: bool = False) -> None:
        cb = self.handle_direct_message
        assert cb is not None, "bridge.start() not called"
        if from_thread:
            done = threading.Event()
            def _go():
                cb(message, sender, channel_id)
                done.set()
            threading.Thread(target=_go, daemon=True).start()
            done.wait(timeout=2)
        else:
            cb(message, sender, channel_id)


def _make_bridge() -> HiveMindMattermostBridge:
    return HiveMindMattermostBridge(
        bot=_StubBot(),
        client=AsyncFakeHiveMessageBus(site_id="test-mattermost"),
    )


def _run(coro):
    return asyncio.run(coro)


class TestLifecycle(unittest.TestCase):
    def test_start_idempotent_and_listen_in_executor(self):
        bridge = _make_bridge()

        async def scenario():
            await bridge.start()
            # listen() should have been scheduled on the executor; the
            # stub flips listen_started when it actually runs.
            self.assertTrue(bridge.bot.listen_started.wait(timeout=2))
            self.assertTrue(bridge.client.connected_event.is_set())
            await bridge.start()  # second call is a no-op
            bridge.bot.stop_listening()
            await bridge.stop()

        _run(scenario())

    def test_stop_before_start(self):
        bridge = _make_bridge()
        _run(bridge.stop())  # no-op, no raise


class TestMattermostToHivemind(unittest.TestCase):
    def test_mention_forwarded_as_utterance(self):
        bridge = _make_bridge()

        async def scenario():
            await bridge.start()
            try:
                bridge.bot.fire_mention(
                    "what time is it", "alice", "channel-1",
                    from_thread=True,
                )
                await asyncio.sleep(0.05)
            finally:
                bridge.bot.stop_listening()
                await bridge.stop()

        _run(scenario())
        self.assertEqual(len(bridge.client.emitted), 1)
        env = bridge.client.emitted[0]
        self.assertEqual(env.msg_type, HiveMessageType.BUS)
        self.assertEqual(env.payload.msg_type, "recognizer_loop:utterance")
        self.assertEqual(env.payload.data["utterances"], ["what time is it"])
        self.assertEqual(env.payload.context["channel"], "channel-1")
        self.assertEqual(env.payload.context["user"]["mattermost_username"], "alice")

    def test_direct_message_forwarded_as_utterance(self):
        bridge = _make_bridge()

        async def scenario():
            await bridge.start()
            try:
                bridge.bot.fire_direct_message(
                    "private", "bob", "channel-dm",
                    from_thread=True,
                )
                await asyncio.sleep(0.05)
            finally:
                bridge.bot.stop_listening()
                await bridge.stop()

        _run(scenario())
        self.assertEqual(len(bridge.client.emitted), 1)
        env = bridge.client.emitted[0]
        self.assertEqual(env.payload.data["utterances"], ["private"])

    def test_callback_before_start_drops_message(self):
        bridge = _make_bridge()
        # neither start() nor the handler wiring has happened
        bridge.bot.handle_mention = bridge._on_mmost_message
        bridge.bot.fire_mention("orphan", "ghost", "c")
        self.assertEqual(bridge.client.emitted, [])


class TestHivemindToMattermost(unittest.TestCase):
    def test_speak_with_channel_and_user_is_sent(self):
        bridge = _make_bridge()

        async def scenario():
            await bridge.start()
            try:
                await bridge.client.emit(Message(
                    "speak",
                    {"utterance": "it is 9am"},
                    {
                        "channel": "channel-1",
                        "user": {"mattermost_username": "alice"},
                    },
                ))
            finally:
                bridge.bot.stop_listening()
                await bridge.stop()

        _run(scenario())
        self.assertEqual(len(bridge.bot.sent), 1)
        channel, text = bridge.bot.sent[0]
        self.assertEqual(channel, "channel-1")
        self.assertEqual(text, "@alice , it is 9am")

    def test_speak_without_channel_is_dropped(self):
        bridge = _make_bridge()

        async def scenario():
            await bridge.start()
            try:
                await bridge.client.emit(Message(
                    "speak",
                    {"utterance": "orphan"},
                    {"user": {"mattermost_username": "alice"}},
                ))
            finally:
                bridge.bot.stop_listening()
                await bridge.stop()

        _run(scenario())
        self.assertEqual(bridge.bot.sent, [])

    def test_intent_failure_routes_back_with_apology(self):
        bridge = _make_bridge()

        async def scenario():
            await bridge.start()
            try:
                await bridge.client.emit(Message(
                    "hive.complete_intent_failure",
                    {},
                    {
                        "channel": "channel-1",
                        "user": {"mattermost_username": "alice"},
                    },
                ))
            finally:
                bridge.bot.stop_listening()
                await bridge.stop()

        _run(scenario())
        self.assertEqual(len(bridge.bot.sent), 1)
        _, text = bridge.bot.sent[0]
        self.assertIn("don't know how to answer", text)

    def test_send_exception_is_logged_not_raised(self):
        bridge = _make_bridge()
        bridge.bot.send_message = MagicMock(side_effect=RuntimeError("boom"))

        async def scenario():
            await bridge.start()
            try:
                await bridge.client.emit(Message(
                    "speak",
                    {"utterance": "x"},
                    {
                        "channel": "c",
                        "user": {"mattermost_username": "u"},
                    },
                ))
            finally:
                bridge.bot.stop_listening()
                await bridge.stop()

        _run(scenario())  # must not raise


class TestRoundTrip(unittest.TestCase):
    def test_mention_in_speak_out(self):
        bridge = _make_bridge()

        async def scenario():
            await bridge.start()
            try:
                bridge.bot.fire_mention(
                    "what time is it", "alice", "channel-1",
                    from_thread=True,
                )
                await asyncio.sleep(0.05)
                self.assertEqual(len(bridge.client.emitted), 1)
                # simulate a HiveMind reply
                await bridge.client.emit(Message(
                    "speak",
                    {"utterance": "it is 9am"},
                    {
                        "channel": "channel-1",
                        "user": {"mattermost_username": "alice"},
                    },
                ))
                self.assertEqual(
                    bridge.bot.sent,
                    [("channel-1", "@alice , it is 9am")],
                )
            finally:
                bridge.bot.stop_listening()
                await bridge.stop()

        _run(scenario())


if __name__ == "__main__":
    unittest.main()
