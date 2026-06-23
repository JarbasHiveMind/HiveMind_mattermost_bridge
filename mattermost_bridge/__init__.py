"""HiveMind <-> Mattermost bridge.

Modernized from the legacy ``jarbas_hive_mind`` (pre-rename, Mycroft-era,
Tornado-based ``HiveMindTerminal``) to the modern ``hivemind-bus-client``
:class:`~hivemind_bus_client.HiveMessageBusClient`.

Composition design (replaces the old ``JarbasMattermostBridge`` that
*extended* ``HiveMindTerminal``):

- :class:`mattermost_bridge.mmost.MMostBot` wraps ``mattermostdriver``.
  ``MMostBot.listen()`` is a blocking call driving the driver's own
  websocket loop, so we run it in a daemon thread.
- :class:`HiveMindMattermostBridge` owns a
  :class:`~hivemind_bus_client.HiveMessageBusClient`, registers a ``speak``
  handler to forward HiveMind replies back to Mattermost, and forwards
  inbound Mattermost messages onto the HiveMind bus as
  ``recognizer_loop:utterance``.

The HiveMind ``speak`` handler and the Mattermost callbacks run on threads
owned by their respective libraries; ``MMostBot.send_message`` and
``HiveMessageBusClient.emit`` are both safe to call from those threads.
"""
from typing import List, Optional

from hivemind_bus_client import (
    HiveMessage,
    HiveMessageType,
    HiveMessageBusClient,
)
from ovos_bus_client.message import Message
from ovos_utils import create_daemon
from ovos_utils.log import LOG

from mattermost_bridge.mmost import MMostBot

platform = "HiveMindMattermostBridgeV0.2"


class HiveMindMattermostBridge:
    """Bridge Mattermost direct-messages/mentions to a HiveMind node."""

    def __init__(self,
                 mail: Optional[str] = None,
                 pswd: Optional[str] = None,
                 url: Optional[str] = None,
                 tags: Optional[List[str]] = None,
                 key: Optional[str] = None,
                 password: Optional[str] = None,
                 host: Optional[str] = None,
                 port: int = 5678,
                 self_signed: bool = False,
                 lang: str = "en-us",
                 *,
                 client: Optional[HiveMessageBusClient] = None,
                 bot: Optional[MMostBot] = None):
        self.lang = lang
        self.bot = bot or MMostBot(mail, pswd, url, tags=tags)
        self.bot.handle_mention = self.handle_mmost_message
        self.bot.handle_direct_message = self.handle_mmost_message

        # NOTE: HiveMessageBusClient does NOT open a connection in __init__;
        # call connect() (see start()). This keeps the object constructible
        # offline for tests.
        self.client = client or HiveMessageBusClient(
            key=key,
            password=password,
            host=host,
            port=port,
            useragent=platform,
            self_signed=self_signed,
        )
        self._started = False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Connect to HiveMind and start listening to Mattermost."""
        if self._started:
            return
        self.client.connect(site_id="mattermost")
        self.client.on_mycroft("speak", self.handle_speak)
        self.client.on_mycroft("hive.complete_intent_failure",
                               self.handle_intent_failure)
        LOG.info("== connected to HiveMind")
        # MMostBot.listen() blocks on the driver websocket loop -> daemon it
        create_daemon(self.bot.listen)
        LOG.info("== listening to Mattermost")
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        try:
            self.client.close()
        except Exception:
            LOG.exception("error closing HiveMind client")
        self._started = False

    # ------------------------------------------------------------------
    # Mattermost -> HiveMind
    # ------------------------------------------------------------------

    def handle_mmost_message(self, message: str, sender: str,
                             channel_id: str) -> None:
        """Forward an inbound Mattermost message onto the HiveMind bus."""
        msg = Message(
            "recognizer_loop:utterance",
            {"utterances": [message], "lang": self.lang},
            {
                "source": platform,
                "destination": "HiveMind",
                "platform": platform,
                "channel": channel_id,
                "user": {"mattermost_username": sender},
            },
        )
        self.client.emit(HiveMessage(HiveMessageType.BUS, msg))

    # ------------------------------------------------------------------
    # HiveMind -> Mattermost
    # ------------------------------------------------------------------

    def handle_speak(self, message: Message) -> None:
        channel_id = message.context.get("channel")
        user_data = message.context.get("user")
        if not channel_id or not user_data:
            return
        utterance = message.data.get("utterance")
        if not utterance:
            return
        self.speak(utterance, channel_id, user_data)

    def handle_intent_failure(self, message: Message) -> None:
        channel_id = message.context.get("channel")
        user_data = message.context.get("user")
        if not channel_id or not user_data:
            return
        LOG.error("complete intent failure")
        self.speak("I don't know how to answer that", channel_id, user_data)

    def speak(self, utterance: str, channel_id: str, user_data: dict) -> None:
        user = user_data.get("mattermost_username") or "user"
        text = f"@{user} , {utterance}"
        LOG.debug(f"Sending message to channel {channel_id}: {text}")
        try:
            self.bot.send_message(channel_id, text)
        except Exception:
            LOG.exception(
                f"failed to send mattermost message to channel={channel_id}")


# Backwards-compat alias for the old public name. The old class extended the
# Tornado HiveMindTerminal; anyone relying on those internals will get an
# AttributeError at runtime, which is the honest failure mode.
JarbasMattermostBridge = HiveMindMattermostBridge

__all__ = ["HiveMindMattermostBridge", "JarbasMattermostBridge", "platform"]
