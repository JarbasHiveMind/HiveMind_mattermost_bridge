"""CLI entry point for the HiveMind <-> Mattermost bridge.

HiveMind identity (key/password/host/port) defaults to the values stored by
``hivemind-client set-identity``; flags override them.
"""
import argparse

from ovos_utils.log import LOG

from mattermost_bridge import HiveMindMattermostBridge


def connect_mattermost_to_hivemind(mail, pswd, url, tags=None,
                                   key=None, password=None,
                                   host=None, port=5678,
                                   self_signed=False, lang="en-us"):
    bridge = HiveMindMattermostBridge(
        mail=mail, pswd=pswd, url=url, tags=tags or ["@bot"],
        key=key, password=password, host=host, port=port,
        self_signed=self_signed, lang=lang,
    )
    bridge.start()
    return bridge


def main():
    parser = argparse.ArgumentParser(
        description="Bridge a Mattermost bot account to a HiveMind node")
    # Mattermost
    parser.add_argument("--mail", required=True,
                        help="Mattermost bot account email / login id")
    parser.add_argument("--pswd", required=True,
                        help="Mattermost bot account password")
    parser.add_argument("--url", required=True,
                        help="Mattermost server host (no scheme, e.g. chat.example.com)")
    parser.add_argument("--tag", dest="tags", action="append", default=None,
                        help="tag that triggers the bot (repeatable, default: @bot)")
    # HiveMind
    parser.add_argument("--key", default=None,
                        help="HiveMind access key (default: from identity file)")
    parser.add_argument("--password", default=None,
                        help="HiveMind password (default: from identity file)")
    parser.add_argument("--host", default=None,
                        help="HiveMind host, e.g. ws://127.0.0.1 (default: from identity file)")
    parser.add_argument("--port", type=int, default=5678,
                        help="HiveMind port (default: 5678)")
    parser.add_argument("--self-signed", action="store_true",
                        help="accept self-signed SSL certificates")
    parser.add_argument("--lang", default="en-us", help="utterance language")

    args = parser.parse_args()

    host = args.host
    if host and not host.startswith("ws://") and not host.startswith("wss://"):
        host = "ws://" + host

    connect_mattermost_to_hivemind(
        mail=args.mail, pswd=args.pswd, url=args.url, tags=args.tags,
        key=args.key, password=args.password, host=host, port=args.port,
        self_signed=args.self_signed, lang=args.lang,
    )

    LOG.info("bridge running; press Ctrl-C to stop")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        LOG.info("shutting down")


if __name__ == '__main__':
    main()
