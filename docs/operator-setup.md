# Operator setup — running the Mattermost bridge

This bridge logs a bot into a **Mattermost server** and relays each tagged
message to/from a HiveMind hub, turning any HiveMind hub (and the OVOS skills
behind it) into a Mattermost chatbot. As an operator you need a **Mattermost
server**, a **bot account** on it, a **team** and **channel** the bot belongs to,
plus a HiveMind hub to point it at.

```
Mattermost user  ⇄  Mattermost server  ⇄  hivemind-mattermost-bridge  ⇄  HiveMind hub  ⇄  OVOS skills
```

## 1. Get the bot a Mattermost account

You need a **Mattermost server** and a **bot login** on it. The bridge logs in
with an email/login + password (a bot account/token works the same way).

### Option A — an existing Mattermost server

On a server you already run (or are a member of), create a dedicated bot account
(email/login + password), add it to the **team**, and make it a member of the
**channel(s)** it should answer in. Note the server host (bare host, no scheme,
e.g. `chat.example.com`).

### Option B — self-host (no external account)

Run Mattermost yourself in a container — the official **`mattermost-preview`**
image is the quickest:

```bash
docker run --name mattermost-preview -d --publish 8065:8065 mattermost/mattermost-preview
```

Open `http://localhost:8065`, create the first (admin) account and a team, then
create a bot via the **System Console → Integrations → Bot Accounts** (or the
API) and add it to a channel. This is the no-external-account path and the basis
for the full-loop follow-up test noted in `tests/e2e/test_bridge_hivemind_e2e.py`
(PR #10).

## 2. Prerequisites

- The bot's **login (email)**, **password**, server **host**, and a **channel**
  the bot is a member of.
- A running **HiveMind hub** (`hivemind-core`) you can reach.
- Python 3.10+. Deps: `hivemind-bus-client`, `mattermostdriver`, `ovos-utils`,
  `ovos-bus-client`.

## 3. Register the bridge on the hub

On the hub, create a client credential for this bridge:

```bash
hivemind-core add-client          # prints an ACCESS KEY and a PASSWORD
```

Note the **access key**, **password**, and the hub **host** / **port** (default
WebSocket port `5678`). The bridge connects as a HiveMind *satellite* with these.

You can pass them as flags (below) or store them once with
`hivemind-client set-identity` and omit the flags.

## 4. Install and run the bridge

```bash
pip install .          # provides the `hivemind-mattermost-bridge` command

hivemind-mattermost-bridge \
  --mail bot@example.com \
  --pswd bot-password \
  --url  chat.example.com \
  --tag  @bot \
  --key      "your-access-key" \
  --password "your-hivemind-password" \
  --host ws://your-hub-host \
  --port 5678
```

Flags (verify with `hivemind-mattermost-bridge --help`):

| Flag | Meaning | Default |
| --- | --- | --- |
| `--mail` | Mattermost bot login (email) (required) | — |
| `--pswd` | Mattermost bot password (required) | — |
| `--url` | Mattermost server host, no scheme (required) | — |
| `--tag` | trigger tag, repeatable | `@bot` |
| `--lang` | utterance language | `en-us` |
| `--key` / `--password` | HiveMind credentials | from identity file |
| `--host` / `--port` | HiveMind hub (`ws://` prefix added if missing) | from identity file / `5678` |
| `--self-signed` | accept self-signed TLS | off |

## 5. Talk to it

In a channel the bot is in, mention it:

```
@bot what time is it?
```

The bridge forwards the message to the hub as a `recognizer_loop:utterance` and
posts the hub's reply back to the originating channel.

## Security notes

- The **Mattermost password** and the **HiveMind password** are secrets — pass
  them via environment variables or a secrets manager, never in shell history or
  a committed file.
- Anyone in a channel the bot is in who knows the trigger tag can reach the hub.
  Restrict access at the hub (client ACLs / `allowed_types`) and limit the bot's
  channel membership.

## Testing (live e2e)

`tests/e2e/test_bridge_hivemind_e2e.py` runs the **real HiveMind round-trip**
unconditionally: it boots a real `hivemind-core` hub over a loopback WebSocket and
drives the production bridge through it; only the Mattermost transport is mocked
(no env vars or Mattermost server needed):

```bash
pytest tests/e2e/test_bridge_hivemind_e2e.py
```

A **full Mattermost-loop** test — a containerized `mattermost-preview` instance
plus a real bot account, driven end to end over the real server — is the next
step, tracked as follow-up work on PR #10.
