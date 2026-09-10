# Setup Walkthrough

From nothing to a working Mattermost chatbot backed by a HiveMind hub.

## How the bridge fits together

The bridge is a HiveMind satellite with two connections:

- **To Mattermost** — it logs into a bot account and listens on the Mattermost websocket for posts.
- **To the HiveMind hub** — it connects as a HiveMind terminal using an access key.

A post that mentions the bot (carries a trigger tag) or a direct message to the bot becomes a `recognizer_loop:utterance` sent to the hub. The originating channel and username travel in the message context, so the hub's `speak` reply is posted back to the right channel.

```
Mattermost channel  ⇄  bridge  ⇄  HiveMind hub  ⇄  OVOS pipeline / skills
```

## Step 1 — Stand up a HiveMind hub

Install and run [hivemind-core](https://github.com/JarbasHiveMind/HiveMind-core):

```bash
pip install hivemind-core
hivemind-core listen
```

The hub listens on port `5678` by default.

## Step 2 — Register the bridge as a client

On the hub machine:

```bash
hivemind-core add-client --name mattermost-bridge \
  --access-key "your-access-key" --password "your-password"
```

Keep the access key. List clients with `hivemind-core list-clients`.

A freshly registered client can connect, but the hub denies every message type until you whitelist it. Skipping this is the most common reason a bridge connects but never replies:

```bash
hivemind-core allow-msg recognizer_loop:utterance mattermost-bridge
hivemind-core allow-msg speak mattermost-bridge
```

## Step 3 — Create a Mattermost bot account

1. On your Mattermost server, create a user account for the bot (or a bot account with login credentials).
2. Note its login email and password.
3. Add the account to the channels it should answer in.

## Step 4 — Install the bridge

```bash
git clone https://github.com/JarbasHiveMind/HiveMind_mattermost_bridge
cd HiveMind_mattermost_bridge
pip install .
```

## Step 5 — Run

Pass your Mattermost login (`--mail`, `--pswd`, `--url`), trigger `--tag`, and HiveMind `--host`/`--port`/`--key`/`--password` as flags:

```bash
hivemind-mattermost-bridge --mail bot@example.com --pswd bot-password \
  --url chat.example.com --tag @bot \
  --host ws://127.0.0.1 --port 5678 \
  --key your-access-key --password your-hivemind-password
```

HiveMind identity flags default to the values stored by `hivemind-client set-identity`.

## Step 6 — Talk to it

In a channel the bot is in, mention it with a trigger tag, or send it a direct message:

```
@bot what is the weather?
```

The bridge forwards the text (with the tag stripped) to the hub and posts the spoken answer back.
