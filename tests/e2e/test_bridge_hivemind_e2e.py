"""REAL HiveMind-side end-to-end test for the Mattermost bridge.

What this exercises (and what it does NOT)
------------------------------------------
This boots a **real hivemind-core hub** (hivescope's loopback topology — an
actual localhost WebSocket server) and drives the **real**
:class:`mattermost_bridge.HiveMindMattermostBridge` end to end over a real
:class:`~hivemind_bus_client.HiveMessageBusClient`. The full HiveMind code
path — handshake, encryption, BUS-message admission (whitelist-only ACL),
agent-bus injection, and reverse routing of the agent's ``speak`` back to the
originating satellite — is genuinely executed.

Only the **Mattermost side is mocked**: ``mattermostdriver.Driver`` is replaced
so the real :class:`mattermost_bridge.mmost.MMostBot` constructs and parses a
real Mattermost ``posted`` websocket event without touching the network, and
its outbound ``driver.posts.create_post`` is captured. We do NOT mock the
bridge, the bus client, or the hub.

The proven round-trip::

    inbound Mattermost 'posted' event
      -> MMostBot.event_handler (real parse) -> on_mention -> handle_mention
      -> bridge.handle_mmost_message
      -> HiveMessageBusClient.emit(BUS recognizer_loop:utterance)   [real WS]
      -> hivemind-core admits + injects on the agent bus
      -> agent responder emits 'speak' routed back to this satellite
      -> bridge.on_mycroft('speak') -> bridge.handle_speak
      -> MMostBot.send_message -> driver.posts.create_post (captured)

FOLLOW-UP (out of scope here): a FULL Mattermost loop driven through a real
server — a containerized ``mattermost-preview`` instance plus a real bot
token, with the bridge's ``MMostBot.listen()`` websocket actually connected —
is the next step. That needs a self-hosted Mattermost and is tracked as
follow-up work on PR #10. Here the Mattermost transport is mocked at the
``Driver`` boundary while everything HiveMind-side is real.

NEVER importorskip: the Mattermost library is mocked explicitly so the test
fails loudly (not silently skips) if a real dependency is missing.
"""
import json
import time
from unittest.mock import MagicMock, patch

from ovos_bus_client.message import Message

from hivemind_bus_client.client import HiveMessageBusClient
from hivemind_bus_client.identity import NodeIdentity
from hivescope.topology import TopologyBuilder


# Mattermost identifiers used to forge the inbound 'posted' event. The bot's
# own user id must differ from the sender's, or MMostBot ignores its own echo.
BOT_USER_ID = "bot-user-id"
SENDER_USER_ID = "human-user-id"
SENDER_NAME = "alice"
CHANNEL_ID = "chan-xyz"
CHANNEL_NAME = "town-square"  # != bot__sender -> treated as a channel (mention path)


def _extract_host_port(url: str):
    """Extract (host, port) from a loopback url like ws://127.0.0.1:PORT/."""
    parts = url.replace("ws://", "").replace("wss://", "").rstrip("/").split(":")
    return parts[0], int(parts[1])


def _make_hivemind_client(url: str, key: str, password: str,
                          name: str = "mattermost-bridge") -> HiveMessageBusClient:
    """A real HiveMessageBusClient pointed at the loopback hub.

    Mirrors the harness reference (_make_client in
    hivemind-test-harness/tests/test_hivemind_bus_client_e2e.py): a fully
    populated NodeIdentity so connect() has key/password/host/port without
    reading any on-disk identity file.
    """
    host, port = _extract_host_port(url)
    identity = NodeIdentity()
    identity.access_key = key
    identity.password = password
    identity.default_master = f"ws://{host}"
    identity.default_port = port
    identity.name = name
    identity.site_id = "mattermost"
    return HiveMessageBusClient(
        key=key,
        password=password,
        host=f"ws://{host}",
        port=port,
        useragent=name,
        self_signed=False,
        identity=identity,
    )


def _install_agent_responder(master, answer: str = "the weather is sunny"):
    """Register a responder on the hub's agent bus.

    Pattern from hivemind-test-harness/tests/test_cascade.py
    (_setup_agent_responder): a handler on ``master.agent_protocol.bus`` reacts
    to ``recognizer_loop:utterance`` and emits ``speak``.

    Crucial routing detail (see hivemind-core protocol.handle_inject_agent_msg
    and hivescope TestAgentProtocol.handle_internal_mycroft): the satellite only
    receives a bus message whose ``context['destination']`` matches its peer id.
    hivemind-core stamps the injected utterance with
    ``context['source'] = context['peer'] = <satellite peer>``, so we echo the
    inbound context back and set ``destination`` to that peer. We also keep the
    bridge's own ``channel`` / ``user`` context (which rides along on the
    utterance untouched) so bridge.handle_speak can target the right channel.
    """
    bus = master.agent_protocol.bus

    def _responder(msg: Message):
        ctx = dict(msg.context)
        peer = ctx.get("source") or ctx.get("peer")
        ctx["destination"] = peer
        bus.emit(Message("speak", {"utterance": answer}, ctx))

    bus.on("recognizer_loop:utterance", _responder)


def _posted_event(message: str) -> str:
    """Forge a real Mattermost 'posted' websocket event JSON string.

    Shape matches what MMostBot.event_handler / on_message / on_mention parse:
    a top-level ``event`` plus ``data`` with a JSON-encoded ``post``,
    ``sender_name``, and the post carrying ``channel_id`` / ``user_id``.
    """
    post = {
        "id": "post-id",
        "message": message,
        "channel_id": CHANNEL_ID,
        "user_id": SENDER_USER_ID,
    }
    return json.dumps({
        "event": "posted",
        "data": {
            "post": json.dumps(post),
            "sender_name": SENDER_NAME,
            "channel_name": CHANNEL_NAME,
        },
        "broadcast": {"channel_id": CHANNEL_ID},
    })


def _build_mocked_driver(create_post_calls):
    """A mocked mattermostdriver Driver: no network, captures outbound posts."""
    driver = MagicMock(name="Driver")
    # user_id property -> driver.users.get_user(user_id='me')['id']
    driver.users.get_user.return_value = {"id": BOT_USER_ID,
                                          "username": "bot",
                                          "email": "bot@example.com"}
    # on_message looks up the channel name to decide DM vs mention path
    driver.channels.get_channel.return_value = {"name": CHANNEL_NAME}
    # capture outbound replies
    driver.posts.create_post.side_effect = \
        lambda options: create_post_calls.append(options)
    return driver


def test_round_trip_mattermost_to_hivemind_and_back():
    """Inbound Mattermost message -> real hub -> agent speak -> Mattermost reply."""
    from mattermost_bridge import HiveMindMattermostBridge
    from mattermost_bridge.mmost import MMostBot

    key = "mm-bridge-key"
    # poorman-handshake >=2.0.0a1 gates the symmetric handshake on password
    # entropy (>=40 bits); this must stay comfortably above that floor.
    password = "correct-horse-battery-staple-9f3a1c7e2b8d4055-mm"
    reply_text = "the weather is sunny"

    # --- real hub: loopback hivemind-core + responding agent ---
    builder = TopologyBuilder()
    master = builder.add_master("M0", use_loopback=True)
    # hivemind-core is whitelist-only: grant exactly the type the bridge injects.
    master.register_satellite(
        key, password=password,
        allowed_types=["recognizer_loop:utterance"],
    )
    builder.start_all()

    bridge = None
    create_post_calls = []
    try:
        _install_agent_responder(master, answer=reply_text)

        # --- mocked Mattermost side: real MMostBot, fake Driver (no network) ---
        with patch("mattermost_bridge.mmost.Driver") as DriverCls:
            DriverCls.return_value = _build_mocked_driver(create_post_calls)
            bot = MMostBot("bot@example.com", "secret", "chat.example.com",
                           tags=["@bot"])

            # --- real bridge with a REAL HiveMessageBusClient -> the hub ---
            client = _make_hivemind_client(master.network_protocol.url,
                                           key, password)
            bridge = HiveMindMattermostBridge(bot=bot, client=client)

            # connect() handshakes + wires the speak handler. We avoid
            # bridge.start()'s blocking MMostBot.listen() daemon (we inject the
            # inbound event by hand) but exercise the real connect path:
            client.connect(site_id="mattermost")
            client.wait_for_handshake(timeout=15)
            assert client.handshake_event.is_set(), "handshake did not complete"
            client.on_mycroft("speak", bridge.handle_speak)

            # ensure the encrypted HELLO registered us as a peer on the hub
            for _ in range(50):
                if master.connected_peers():
                    break
                time.sleep(0.1)
            assert master.connected_peers(), "bridge did not register as a peer"

            # --- inbound: drive a REAL Mattermost 'posted' event through the
            # real MMostBot parser. on_mention -> handle_mention ->
            # bridge.handle_mmost_message -> emit on the HiveMind bus. ---
            import asyncio
            asyncio.run(
                bot.event_handler(_posted_event("@bot what is the weather?"))
            )

            # --- round-trip: wait for the agent speak to come back through the
            # hub, reverse-route to us, and land in driver.posts.create_post ---
            for _ in range(100):
                if create_post_calls:
                    break
                time.sleep(0.1)

        assert create_post_calls, (
            "no outbound Mattermost post captured — the speak never round-tripped"
        )
        outbound = create_post_calls[0]
        assert outbound["channel_id"] == CHANNEL_ID
        # bridge.speak() formats as "@<user> , <utterance>"
        assert reply_text in outbound["message"]
        assert SENDER_NAME in outbound["message"]
    finally:
        if bridge is not None:
            try:
                bridge.stop()
            except Exception:
                pass
        builder.stop_all()
