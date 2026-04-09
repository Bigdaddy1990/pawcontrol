"""Tests for the lightweight ``config_flow`` entrypoint shim."""

from custom_components.pawcontrol import config_flow, config_flow_main


def test_config_flow_entrypoint_exports_expected_aliases() -> None:
    """Shim should expose the exact config-flow aliases Home Assistant imports."""
    assert config_flow.__all__ == ("ConfigFlow", "PawControlConfigFlow")
    assert config_flow.ConfigFlow is config_flow_main.ConfigFlow
    assert config_flow.PawControlConfigFlow is config_flow_main.PawControlConfigFlow


def test_config_flow_compat_alias_points_to_main_flow() -> None:
    """Compatibility alias should continue pointing at the concrete flow class."""
    assert config_flow.ConfigFlow is config_flow.PawControlConfigFlow
