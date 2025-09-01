"""Test STATE_ONLINE compatibility."""

from custom_components.pawcontrol.coordinator import STATE_ONLINE


def test_state_online_constant():
    """Ensure STATE_ONLINE uses expected value."""
    assert STATE_ONLINE == "online"
