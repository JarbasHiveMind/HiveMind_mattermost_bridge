"""Smoke tests: import the package and construct the bridge offline.

No live Mattermost or HiveMind connection is made. The mattermostdriver
``Driver`` is constructed for real (it does not touch the network until
``login()``), and a pre-built mock HiveMessageBusClient is injected so the
bridge's __init__ never tries to build a NodeIdentity.
"""
from unittest.mock import MagicMock


def test_import_package_and_version():
    import mattermost_bridge
    from mattermost_bridge.version import __version__

    assert isinstance(__version__, str)
    assert __version__
    assert mattermost_bridge.platform.startswith("HiveMindMattermostBridge")
    # public class + back-compat alias
    assert mattermost_bridge.HiveMindMattermostBridge is \
        mattermost_bridge.JarbasMattermostBridge


def test_construct_bridge_without_connecting():
    """Build the bridge with a fake HiveMind client; never connect."""
    from mattermost_bridge import HiveMindMattermostBridge
    from mattermost_bridge.mmost import MMostBot

    fake_client = MagicMock(name="HiveMessageBusClient")
    # real MMostBot: Driver() is lazy, no network until listen()/login()
    bot = MMostBot("bot@example.com", "secret", "chat.example.com",
                   tags=["@bot"])

    bridge = HiveMindMattermostBridge(bot=bot, client=fake_client)

    # bridge wired the bot's handlers to itself
    assert bot.handle_mention == bridge.handle_mmost_message
    assert bot.handle_direct_message == bridge.handle_mmost_message
    assert bridge._started is False
    # no connection attempted on construction
    fake_client.connect.assert_not_called()


def test_inbound_message_forwarded_to_hivemind():
    """An inbound Mattermost message becomes a BUS HiveMessage emit."""
    from hivemind_bus_client import HiveMessage, HiveMessageType
    from mattermost_bridge import HiveMindMattermostBridge

    fake_client = MagicMock(name="HiveMessageBusClient")
    fake_bot = MagicMock(name="MMostBot")

    bridge = HiveMindMattermostBridge(bot=fake_bot, client=fake_client)
    bridge.handle_mmost_message("hello world", "alice", "chan123")

    fake_client.emit.assert_called_once()
    sent = fake_client.emit.call_args[0][0]
    assert isinstance(sent, HiveMessage)
    assert sent.msg_type == HiveMessageType.BUS
    payload = sent.payload
    assert payload.msg_type == "recognizer_loop:utterance"
    assert payload.data["utterances"] == ["hello world"]
    assert payload.context["channel"] == "chan123"
    assert payload.context["user"]["mattermost_username"] == "alice"


def test_start_bounds_handshake_retries():
    """start() must pass a bounded (non-None) handshake_max_retries.

    hivemind-bus-client >= 1.0.13a1 blocks in connect() on the handshake;
    handshake_max_retries=None (the client's own default) retries forever.
    A stalled/unreachable hub must not hang the bridge.
    """
    from mattermost_bridge import HiveMindMattermostBridge, \
        DEFAULT_HANDSHAKE_MAX_RETRIES
    from mattermost_bridge.mmost import MMostBot

    fake_client = MagicMock(name="HiveMessageBusClient")
    bot = MMostBot("bot@example.com", "secret", "chat.example.com",
                   tags=["@bot"])
    bot.listen = MagicMock(name="listen")  # avoid the real blocking loop

    bridge = HiveMindMattermostBridge(bot=bot, client=fake_client)
    bridge.start()

    fake_client.connect.assert_called_once()
    _, kwargs = fake_client.connect.call_args
    assert "handshake_max_retries" in kwargs
    assert kwargs["handshake_max_retries"] is not None
    assert kwargs["handshake_max_retries"] == DEFAULT_HANDSHAKE_MAX_RETRIES


def test_speak_routes_back_to_mattermost():
    """A HiveMind speak message is delivered to the right channel/user."""
    from ovos_bus_client.message import Message
    from mattermost_bridge import HiveMindMattermostBridge

    fake_client = MagicMock(name="HiveMessageBusClient")
    fake_bot = MagicMock(name="MMostBot")

    bridge = HiveMindMattermostBridge(bot=fake_bot, client=fake_client)
    msg = Message("speak", {"utterance": "hi there"},
                  {"channel": "chan123",
                   "user": {"mattermost_username": "alice"}})
    bridge.handle_speak(msg)

    fake_bot.send_message.assert_called_once()
    channel_id, text = fake_bot.send_message.call_args[0]
    assert channel_id == "chan123"
    assert "@alice" in text
    assert "hi there" in text


def test_inbound_messages_get_distinct_per_channel_sessions():
    """Two Mattermost channels must map to two distinct Layer-1 sessions.

    HIVEMIND-BRIDGE-1 §4: a client multiplexing several end-user
    conversations over one connection maps each declared name to its own
    session, never collapsing them into one.
    """
    from mattermost_bridge import HiveMindMattermostBridge

    fake_client = MagicMock(name="HiveMessageBusClient")
    fake_bot = MagicMock(name="MMostBot")

    bridge = HiveMindMattermostBridge(bot=fake_bot, client=fake_client)
    bridge.handle_mmost_message("hi from chan1", "alice", "chan1")
    bridge.handle_mmost_message("hi from chan2", "bob", "chan2")

    calls = fake_client.emit.call_args_list
    assert len(calls) == 2
    sid1 = calls[0][0][0].payload.context["session"]["session_id"]
    sid2 = calls[1][0][0].payload.context["session"]["session_id"]

    assert sid1 == "mattermost-chan1"
    assert sid2 == "mattermost-chan2"
    assert sid1 != sid2
