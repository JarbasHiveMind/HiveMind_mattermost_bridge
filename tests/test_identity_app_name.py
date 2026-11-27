"""The bridge connects with its own identity (HIVEMIND-CRYPTO-1 §2)."""
from unittest.mock import MagicMock, patch

import mattermost_bridge
from mattermost_bridge import HiveMindMattermostBridge


def test_the_bridge_builds_its_client_with_its_own_identity():
    identity = MagicMock()
    with patch.object(mattermost_bridge, "NodeIdentity", return_value=identity) as ctor, \
         patch.object(mattermost_bridge, "HiveMessageBusClient") as client:
        HiveMindMattermostBridge(key="k", password="p", bot=MagicMock())
    ctor.assert_called_once_with(app_name="mattermost-bridge")
    assert client.call_args.kwargs["identity"] is identity


def test_a_given_identity_is_used_as_is():
    identity = MagicMock()
    with patch.object(mattermost_bridge, "NodeIdentity") as ctor, \
         patch.object(mattermost_bridge, "HiveMessageBusClient") as client:
        HiveMindMattermostBridge(key="k", password="p", bot=MagicMock(), identity=identity)
    ctor.assert_not_called()
    assert client.call_args.kwargs["identity"] is identity
