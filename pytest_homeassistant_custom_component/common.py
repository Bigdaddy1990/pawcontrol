"""Common helpers mirrored from pytest-homeassistant-custom-component."""

from tests.helpers.homeassistant_test_stubs import ConfigEntry


class MockConfigEntry(ConfigEntry):
    """Test helper that mirrors the upstream fixture utility class."""
