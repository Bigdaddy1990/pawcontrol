"""Focused shim tests for ``config_flow.py``."""

from custom_components.pawcontrol import config_flow, config_flow_main


def test_config_flow_exports_match_main_module() -> None:
    """The entrypoint shim should re-export both flow classes exactly."""
    assert config_flow.ConfigFlow is config_flow_main.ConfigFlow
    assert config_flow.PawControlConfigFlow is config_flow_main.PawControlConfigFlow
    assert config_flow.__all__ == ("ConfigFlow", "PawControlConfigFlow")
