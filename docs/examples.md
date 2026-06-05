# Examples

## Run the bridge

Configure the call at the bottom of `mattermost_bridge/__main__.py`:

```python
from mattermost_bridge.__main__ import connect_mattermost_to_hivemind

connect_mattermost_to_hivemind(
    mail="bot@example.com",
    pswd="bot-password",
    url="chat.example.com",
    tags=["@bot", "@assistant"],
    host="127.0.0.1",
    port=5678,
    key="your-access-key",
)
```

Then start it:

```bash
python -m mattermost_bridge
```

## A conversation

In a channel the bot belongs to:

```
alice> @bot what time is it?
bot>   @alice , It is half past three.

alice> @bot set a timer for five minutes
bot>   @alice , Timer set for five minutes.
```

A direct message to the bot needs no tag:

```
alice (DM)> what time is it?
bot (DM)>   @alice , It is half past three.
```

## Standalone Mattermost echo bot

`MMostBot` can be used on its own, without HiveMind, to verify Mattermost credentials. See `examples/echobot.py`:

```python
from mattermost_bridge.mmost import MMostBot

class EchoBot(MMostBot):
    def handle_direct_message(self, message, sender, channel_id):
        self.send_message(channel_id, message)

    def handle_mention(self, message, sender, channel_id):
        self.send_message(channel_id, "@" + sender + " " + message)

bot = EchoBot("bot@example.com", "bot-password", "chat.example.com", tags=["@bot"])
bot.listen()
```

If the echo bot replies to your messages, the Mattermost half of the configuration is correct and you can move on to wiring the HiveMind half.
