from ovos_utils import create_daemon
from ovos_utils.messagebus import Message
from jarbas_hive_mind.slave.terminal import HiveMindTerminalProtocol, HiveMindTerminal
from ovos_utils.log import LOG
from mattermost_bridge.mmost import MMostBot
import asyncio


platform = "JarbasMattermostBridgeV0.1"


class JarbasMattermostBridgeProtocol(HiveMindTerminalProtocol):

    def onOpen(self):
        super().onOpen()
        self.factory.connect_to_mmost()


class JarbasMattermostBridge(HiveMindTerminal):
    protocol = JarbasMattermostBridgeProtocol

    def __init__(self, mail, pswd, url, tags=None, *args, **kwargs):
        super(JarbasMattermostBridge, self).__init__(*args, **kwargs)
        self.bot = MMostBot(mail, pswd, url, tags=tags)
        self.bot.handle_mention = self.handle_mmost_message
        self.bot.handle_direct_message = self.handle_mmost_message

    def _mmost_run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.bot.listen()

    def connect_to_mmost(self):
        create_daemon(self._mmost_run)

    def handle_incoming_mycroft(self, message):
        assert isinstance(message, Message)

        channel_id = message.context.get("channel")
        user_data = message.context.get("user")

        if channel_id and user_data:
            if message.msg_type == "speak":
                utterance = message.data["utterance"]
                self.speak(utterance, channel_id, user_data)
            elif message.msg_type == "hive.complete_intent_failure":
                LOG.error("complete intent failure")
                utterance = 'I don\'t know how to answer that'
                self.speak(utterance, channel_id, user_data)

    def speak(self, utterance, channel_id, user_data):
        user = user_data["mattermost_username"]
        utterance = "@{} , ".format(user) + utterance
        LOG.debug("Sending message to channel " + channel_id)
        LOG.debug("Message: " + utterance)
        self.bot.send_message(channel_id, utterance)

    def handle_mmost_message(self, message, sender, channel_id):

        msg = {"data": {"utterances": [message], "lang": "en-us"},
               "type": "recognizer_loop:utterance",
               "context": {
                   "source": self.client.peer,
                   "destination": "hive_mind",
                   "platform": platform,
                   "channel": channel_id,
                   "user": {"mattermost_username": sender}}}

        self.send_to_hivemind_bus(msg)


