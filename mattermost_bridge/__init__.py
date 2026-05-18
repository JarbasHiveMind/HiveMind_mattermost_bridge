"""HiveMind <-> Mattermost bridge (async rewrite).

Composition design (replaces the previous JarbasMattermostBridge that
extended the legacy Tornado-based HiveMindTerminal from jarbas_hive_mind):

- :class:`mattermost_bridge.mmost.MMostBot` wraps ``mattermostdriver``,
  whose ``init_websocket(event_handler)`` is a blocking call that drives
  an internal asyncio loop. We run that in a daemon thread so it does
  not block the bridge's own event loop.
- :class:`AsyncHiveMessageBusClient` is the asyncio-native HiveMind
  client (``hivemind-bus-client[async]>=0.8.0``). Runs on the
  application's event loop.
- :class:`HiveMindMattermostBridge` composes the two. The Mattermost
  callback fires on the mattermostdriver thread; the bridge schedules
  utterance forwarding onto the asyncio loop via
  :func:`asyncio.run_coroutine_threadsafe`. The HiveMind ``speak``
  handler runs on the asyncio receive task and calls
  ``MMostBot.send_message`` directly (the mattermost driver's HTTP path
  is thread-safe via requests).

Breaking
- Drops the ``jarbas_hive_mind`` dependency entirely. Was on the legacy
  pre-``hivemind-bus-client`` package; never updated to track the modern
  HiveMind protocol.
- Drops the Tornado-based ``HiveMindTerminal`` base class.
- Renames the package's public class from ``JarbasMattermostBridge`` to
  ``HiveMindMattermostBridge`` to match the deltachat-bridge and
  matrix-bridge conventions in the same migration wave.
- Configuration is no longer hard-coded in ``__main__.py``; a click CLI
  reads identity from ``hivemind-client set-identity`` (or flags).
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from hivemind_bus_client.async_client import AsyncHiveMessageBusClient
from hivemind_bus_client.identity import NodeIdentity
from ovos_bus_client.message import Message
from ovos_utils.log import LOG

from mattermost_bridge.mmost import MMostBot


class HiveMindMattermostBridge:
    platform = "HiveMindMattermostBridgeV0.2"

    def __init__(self,
                 mail: Optional[str] = None,
                 pswd: Optional[str] = None,
                 url: Optional[str] = None,
                 tags: Optional[List[str]] = None,
                 key: Optional[str] = None,
                 password: Optional[str] = None,
                 host: Optional[str] = None,
                 port: Optional[int] = None,
                 identity: Optional[NodeIdentity] = None,
                 *,
                 client: Optional[AsyncHiveMessageBusClient] = None,
                 bot: Optional[MMostBot] = None):
        self.bot = bot or MMostBot(mail, pswd, url, tags=tags)
        self.client = client or AsyncHiveMessageBusClient(
            key=key,
            password=password,
            host=host,
            port=port,
            useragent=self.platform,
            identity=identity,
        )
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._listen_task: Optional[asyncio.Task] = None
        self._started = False

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._started:
            return
        self._loop = asyncio.get_running_loop()
        # mattermostdriver's init_websocket is sync and blocks. Run it on
        # the loop's default executor (its own thread) so our loop is free.
        self.bot.handle_mention = self._on_mmost_message
        self.bot.handle_direct_message = self._on_mmost_message
        self._listen_task = self._loop.run_in_executor(None, self.bot.listen)
        LOG.info("== connected to Mattermost")

        await self.client.connect(site_id="mattermost")
        self.client.on_mycroft("speak", self._on_speak)
        self.client.on_mycroft("hive.complete_intent_failure",
                               self._on_intent_failure)
        LOG.info("== connected to HiveMind")
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            self.client.remove("speak", self._on_speak)
            self.client.remove("hive.complete_intent_failure",
                               self._on_intent_failure)
        except Exception:
            pass
        try:
            await self.client.close()
        except Exception:
            LOG.exception("error closing HiveMind client")
        # mattermostdriver does not expose a clean stop hook; the daemon
        # thread will exit when the process does. Cancel the executor
        # future so we don't await it on shutdown.
        if self._listen_task is not None and not self._listen_task.done():
            self._listen_task.cancel()
        self._started = False

    # ------------------------------------------------------------------
    # Mattermost -> HiveMind (callback runs on mattermostdriver thread)
    # ------------------------------------------------------------------

    def _on_mmost_message(self, message: str, sender: str, channel_id: str) -> None:
        """Schedule the outbound utterance onto the asyncio loop.

        Fired by ``MMostBot.on_mention`` / ``on_direct_message``, both of
        which run inside the mattermostdriver websocket handler thread.
        """
        if self._loop is None or self._loop.is_closed():
            LOG.warning("got mattermost message before bridge started; dropping")
            return

        utt = Message(
            "recognizer_loop:utterance",
            {"utterances": [message], "lang": "en-us"},
            {
                "source": self.platform,
                "destination": "HiveMind",
                "platform": self.platform,
                "channel": channel_id,
                "user": {"mattermost_username": sender},
            },
        )
        asyncio.run_coroutine_threadsafe(self.client.emit_mycroft(utt),
                                         self._loop)

    # ------------------------------------------------------------------
    # HiveMind -> Mattermost (handlers run on the asyncio receive task)
    # ------------------------------------------------------------------

    def _on_speak(self, message) -> None:
        channel_id = message.context.get("channel")
        user_data = message.context.get("user")
        if not channel_id or not user_data:
            return
        utterance = message.data.get("utterance")
        if not utterance:
            return
        self._send(channel_id, user_data, utterance)

    def _on_intent_failure(self, message) -> None:
        channel_id = message.context.get("channel")
        user_data = message.context.get("user")
        if not channel_id or not user_data:
            return
        LOG.error("complete intent failure")
        self._send(channel_id, user_data, "I don't know how to answer that")

    def _send(self, channel_id: str, user_data: dict, utterance: str) -> None:
        user = user_data.get("mattermost_username") or "user"
        text = f"@{user} , {utterance}"
        LOG.debug(f"Sending message to channel {channel_id}: {text}")
        try:
            self.bot.send_message(channel_id, text)
        except Exception:
            LOG.exception(
                f"failed to send mattermost message to channel={channel_id}"
            )


# Backwards-compat alias for code that imported the old name. The class
# itself was tightly coupled to HiveMindTerminal, so the alias resolves to
# the new bridge — anyone whose code used internal HiveMindTerminal methods
# will get an AttributeError at runtime, which is the honest failure mode.
JarbasMattermostBridge = HiveMindMattermostBridge


__all__ = ["HiveMindMattermostBridge", "JarbasMattermostBridge"]
