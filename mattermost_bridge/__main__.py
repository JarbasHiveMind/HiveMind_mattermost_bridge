"""CLI entry point — asyncio main with signal-driven shutdown."""
from __future__ import annotations

import asyncio
import signal
from typing import Tuple

import click
from hivemind_bus_client.identity import NodeIdentity
from ovos_utils.log import LOG

from mattermost_bridge import HiveMindMattermostBridge

LOG.set_level("DEBUG")


async def _amain(mail: str, pswd: str, mmurl: str, tags: Tuple[str, ...],
                 key: str, password: str, host: str, port: int) -> None:
    identity = NodeIdentity()
    password = password or identity.password
    key = key or identity.access_key
    host = host or identity.default_master

    if host and not host.startswith("ws://") and not host.startswith("wss://"):
        host = "ws://" + host

    if not key or not password or not host:
        raise RuntimeError(
            "NodeIdentity not set, please pass key/password/host or "
            "call 'hivemind-client set-identity'"
        )

    bridge = HiveMindMattermostBridge(
        mail=mail, pswd=pswd, url=mmurl, tags=list(tags),
        key=key, password=password, host=host, port=port,
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    await bridge.start()
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bridge.stop()


@click.command()
@click.option("--mail", required=True, help="Mattermost bot account email")
@click.option("--pswd", "--password-mm", "pswd", required=True,
              help="Mattermost bot account password")
@click.option("--mmurl", required=True, help="Mattermost server URL (host part, no scheme)")
@click.option("--tag", "tags", multiple=True, default=["@bot"],
              help="Tags that trigger the bot (repeatable). Default: @bot")
@click.option("--key", default="", help="HiveMind access key (default: from identity file)")
@click.option("--password", default="", help="HiveMind password (default: from identity file)")
@click.option("--host", default="", help="HiveMind host (default: from identity file)")
@click.option("--port", default=5678, type=int, help="HiveMind port (default: 5678)")
def launch_bot(mail: str, pswd: str, mmurl: str, tags: Tuple[str, ...],
               key: str, password: str, host: str, port: int) -> None:
    """Run the HiveMind <-> Mattermost bridge."""
    asyncio.run(_amain(mail, pswd, mmurl, tags, key, password, host, port))


if __name__ == "__main__":
    launch_bot()
