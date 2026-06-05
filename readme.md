# HiveMind Mattermost Bridge

Relay a [Mattermost](https://mattermost.com) bot account to a [HiveMind](https://github.com/JarbasHiveMind/HiveMind-core) hub.

The bridge is a HiveMind **satellite** whose input and output are Mattermost chat instead of a microphone. Mentions and direct messages to the bot become utterances sent to the hub; the hub's spoken reply is posted back to the originating channel. Any HiveMind hub (and the OVOS skills behind it) becomes reachable as a Mattermost chatbot.

```
Mattermost channel  ⇄  HiveMind_mattermost_bridge  ⇄  HiveMind hub  ⇄  OVOS skills
```

![](./mattermost.png)
![](./bridge.png)

## Prerequisites

- A running **HiveMind hub** ([hivemind-core](https://github.com/JarbasHiveMind/HiveMind-core)) reachable over the network, and a **HiveMind access key** for this bridge (`hivemind-core add-client`).
- A **Mattermost server** and a **bot user account** on it (an email/login and password the bridge logs in with). The bot must be a member of the channels it should answer in.
- Python 3.8+.

## Install

This branch has no published package. Install the runtime dependencies and run from a checkout:

```bash
git clone https://github.com/JarbasHiveMind/HiveMind_mattermost_bridge
cd HiveMind_mattermost_bridge
pip install -r requirements.txt
```

Dependencies: `mattermostdriver`, `jarbas_hive_mind>=0.8`, `ovos_utils`.

## Quickstart

**1. Register the bridge on the hub** (where `hivemind-core` is installed):

```bash
hivemind-core add-client --name mattermost-bridge \
  --access-key "your-access-key" --password "your-password"
```

**2. Configure the bridge.** The entry point is `connect_mattermost_to_hivemind(...)` in `mattermost_bridge/__main__.py`. Edit the call at the bottom of that file with your Mattermost login and hub details:

```python
from mattermost_bridge.__main__ import connect_mattermost_to_hivemind

connect_mattermost_to_hivemind(
    mail="bot@example.com",        # Mattermost bot login
    pswd="bot-password",           # Mattermost bot password
    url="chat.example.com",        # Mattermost server host (no scheme)
    tags=["@bot"],                 # trigger tags
    host="127.0.0.1",              # HiveMind hub host
    port=5678,                     # HiveMind hub port
    key="your-access-key",         # HiveMind access key
)
```

**3. Run it:**

```bash
python -m mattermost_bridge
```

**4. Send a message.** In a channel the bot is in, mention it:

```
@bot what time is it?
```

The bridge forwards the message to the hub and posts the hub's reply back to the channel.

## Configuration

`connect_mattermost_to_hivemind(...)` parameters:

| Parameter | Description | Default |
| --- | --- | --- |
| `mail` | Mattermost bot account login (email) | — |
| `pswd` | Mattermost bot account password | — |
| `url` | Mattermost server host (no scheme) | — |
| `tags` | Trigger tags; messages containing one are forwarded | `["@bot"]` |
| `host` | HiveMind hub host | `127.0.0.1` |
| `port` | HiveMind hub port | `5678` |
| `key` | HiveMind access key | `unsafe` |
| `crypto_key` | Optional HiveMind payload crypto key | `None` |

## Troubleshooting

- **Bot never answers** — confirm the bot account is a member of the channel and the message contains a trigger tag; confirm the hub is reachable and the access key is registered (`hivemind-core list-clients`).
- **Mattermost login fails** — check `url` is the bare host (no `https://`) and the bot login/password are correct.
- **No reply posted** — replies are routed by channel and user context; the hub must echo those context keys and produce a `speak` for the answer to land.

## Documentation

See [`docs/`](docs/) for a full setup walkthrough, a configuration reference, and worked examples.
