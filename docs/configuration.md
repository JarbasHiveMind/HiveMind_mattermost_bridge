# Configuration & Credentials Reference

The bridge needs Mattermost bot credentials and a HiveMind access key, passed as flags to the `hivemind-mattermost-bridge` console script (HiveMind identity flags fall back to `hivemind-client set-identity`).

## Mattermost credentials

| Flag | Meaning |
| --- | --- |
| `--mail` | The bot account's login (email). |
| `--pswd` | The bot account's password. |
| `--url` | The Mattermost server host, without a scheme (for example `chat.example.com`). The driver connects over HTTPS on port 443. |
| `--tag` | Trigger tag (repeatable). A channel post containing any tag is treated as a mention; the tag is stripped before forwarding. Default `@bot`. |

Direct messages to the bot are always forwarded regardless of tags.

## HiveMind credentials

| Flag | Meaning | Default |
| --- | --- | --- |
| `--host` | HiveMind hub host (e.g. `ws://127.0.0.1`). | from identity file |
| `--port` | HiveMind hub port. | `5678` |
| `--key` | HiveMind access key from `hivemind-core add-client`. | from identity file |
| `--password` | HiveMind password. | from identity file |
| `--self-signed` | Accept self-signed SSL certificates. | off |

## Reply routing

When the bridge forwards a message it tags the HiveMind context with:

- `channel` — the Mattermost channel id
- `user.mattermost_username` — the sender's username

The hub echoes these on its `speak` reply, and the bridge uses them to post the answer (prefixed with `@username`) back to the originating channel. A `speak` reply missing the `channel` context is dropped.

## Trigger and dispatch flow

1. The bot's websocket receives a `posted` event.
2. If the post is a direct message to the bot, it is forwarded.
3. Otherwise, if the post contains a trigger tag, it is treated as a mention and forwarded with the tag stripped.
4. Posts from the bot itself are ignored.
